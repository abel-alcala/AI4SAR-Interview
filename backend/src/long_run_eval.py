from deepeval.evaluate.configs import CacheConfig, DisplayConfig
from deepeval.evaluate.types import EvaluationResult
from deepeval import evaluate
from deepeval.metrics import BaseMetric
from deepeval.models import AzureOpenAIModel
from deepeval.test_case import LLMTestCase

import os
import csv
import argparse
import time
import json
from typing import Any

import anyio
from tqdm import tqdm
from ulid import ULID
import sqlalchemy as sa

from interview_helper.ai_analysis.ai_analysis import SimpleAnalyzer
from interview_helper.ai_analysis.eval.metrics import get_metric_list
from interview_helper.config import Settings
from interview_helper.context_manager.database import (
    PersistentDatabase,
    add_ai_analysis,
    add_transcription,
)
from interview_helper.context_manager.types import AIJob, ProjectId, SessionId, UserId


config = Settings()  # pyright: ignore[reportCallIssue]

parser = argparse.ArgumentParser()
_ = parser.add_argument("-f", "--file", help="Input file path", required=True, type=str)
_ = parser.add_argument(
    "-c", "--chunk-limit", help="Chunk limit", required=False, type=int, default=None
)
args = parser.parse_args()

file: str = args.file  # pyright: ignore[reportAny]
chunk_limit: int | None = args.chunk_limit  # pyright: ignore[reportAny]

# Load file
with open(file, "r", encoding="utf-8") as f:
    transcript = json.load(f)  # pyright: ignore[reportAny]


def extract_phrases(data: dict[str, Any]) -> list[tuple[str, float]]:  # pyright: ignore[reportExplicitAny]
    """
    Extract (phrase, start_seconds) from recognizedPhrases
    using offsetMilliseconds.
    """
    result: list[tuple[str, float]] = []

    for phrase in data["recognizedPhrases"]:  # pyright: ignore[reportAny]
        start_seconds: float = phrase["offsetMilliseconds"] / 1000.0  # pyright: ignore[reportAny]

        best = phrase["nBest"][0]  # pyright: ignore[reportAny]
        text: str = best.get("display") or best.get("lexical")  # pyright: ignore[reportAny]

        result.append((text, start_seconds))

    return result


phrases = extract_phrases(transcript)  # pyright: ignore[reportAny]

print(f"Loaded transcript with {len(phrases)} lines.")


chunks: list[list[str]] = []
last_time = 0.0
current_chunk: list[str] = []
for text, start in phrases:
    current_chunk.append(text)
    if start - last_time >= config.process_transcript_every_secs:
        chunks.append(current_chunk)
        current_chunk = []
        last_time = start

    if chunk_limit is not None and len(chunks) >= chunk_limit:
        break

if current_chunk and (chunk_limit is None or len(chunks) < chunk_limit):
    chunks.append(current_chunk)

print(f"Total chunks: {len(chunks)}, each ~{config.process_transcript_every_secs}s.")

# Calculate average words per chunk
# Each str in the chunk is a phrase
total_words = sum(len(phrase.split()) for chunk in chunks for phrase in chunk)
avg_words_per_chunk = total_words / len(chunks) if chunks else 0

print(f"Each chunk about ~{avg_words_per_chunk:.1f} words")

y_n = input("Proceed with analysis? (y/n): ")
if y_n.lower() != "y":
    print("Aborting.")
    exit(0)

if not phrases:
    print("No phrases found in transcript.")
    exit(1)

model = AzureOpenAIModel(
    model_name=config.azure_eval_deployment,
    deployment_name=config.azure_eval_deployment,
    azure_openai_api_key=config.azure_api_key.get_secret_value(),
    openai_api_version=config.azure_api_version,
    azure_endpoint=config.azure_api_endpoint,
)

metrics = get_metric_list(model)

time_id = int(time.time())


async def run_analysis(
    chunks: list[list[str]], settings: Settings, metric_list: list[BaseMetric]
) -> list[EvaluationResult]:
    # Setup in-memory database and details
    engine = sa.create_engine(
        f"sqlite+pysqlite:///long_run_test-{time_id}.sqlite3", echo=False
    )
    db = PersistentDatabase(engine)
    db._run_migrations_for_testing()  # pyright: ignore[reportPrivateUsage]

    user = UserId(ULID())
    session = SessionId(ULID())
    project = ProjectId(ULID())

    # Setup DeepEval to not Upload to Cloud
    _ = os.environ.pop("CONFIDENT_API_KEY", None)
    _ = os.environ.setdefault("CI", "1")

    display_config = DisplayConfig(
        verbose_mode=False,  # overrides metric.verbose_mode (when not None)
        show_indicator=False,  # disables the per-metric progress indicator
        print_results=False,  # disables printing of results
    )

    cache_config = CacheConfig(write_cache=False)  # avoid disk writes for cache

    ai_analyzer = SimpleAnalyzer(settings, db)

    results: list[EvaluationResult] = []
    for chunk in tqdm(
        chunks, f"Analyzing {settings.process_transcript_every_secs}s chunks..."
    ):
        for line in chunk:
            _ = add_transcription(db, user, session, project, line, None)

        analysis_results = await ai_analyzer.analyze(AIJob(project), [])
        if analysis_results is None:
            print("No analysis results returned, skipping this chunk.")
            continue

        question_text = "\n".join([q.question for q in analysis_results.questions])

        # Add to db
        for result in analysis_results.questions:
            _ = add_ai_analysis(
                db,
                project_id=project,
                text=result.question,
                category_code=result.category_code,
                span=result.grounding_span,
                transcript_span_id=None,
                transcript_context_start=analysis_results.transcript_context_start,
                transcript_context_end=analysis_results.transcript_context_end,
                summary=analysis_results.summary,
            )

        test_case = LLMTestCase(
            input="\n".join(chunk),
            actual_output=question_text,
            name="Question Quality Test",
        )

        r: EvaluationResult = evaluate(
            test_cases=[test_case],
            metrics=metric_list,
            display_config=display_config,
            cache_config=cache_config,
        )

        # Append into test cases
        results.append(r)

    return results


results = anyio.run(run_analysis, chunks, config, metrics)

rows: list[dict[str, str | float | int]] = []

for run_idx, eval_result in enumerate(results):
    for test_idx, test_result in enumerate(eval_result.test_results):
        row: dict[str, str | float | int] = {
            "run_index": run_idx,
            "test_index": test_idx,
            "input": str(test_result.input),
            "actual_output": str(test_result.actual_output),
            "expected_output": str(test_result.expected_output),
        }

        data = test_result.metrics_data
        assert data, "No metrics data found in test result"

        for metric in data:
            assert metric is not None, "Metric data is None"
            assert metric.name is not None, "Metric name is None"
            assert metric.score is not None, "Metric score is None"

            row[f"{metric.name}_score"] = metric.score
            row[f"{metric.name}_success"] = metric.success
            row[f"{metric.name}_reason"] = str(metric.reason)

        rows.append(row)

if not rows:
    exit(0)

fieldnames = sorted(
    {key for row in rows for key in row.keys()},
    key=lambda x: (
        not x.endswith("_score") and not x.endswith("_success"),
        x,
    ),
)

with open(f"long_result-{time_id}.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
