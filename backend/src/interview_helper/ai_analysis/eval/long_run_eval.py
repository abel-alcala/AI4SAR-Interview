from deepeval.evaluate.types import EvaluationResult
from deepeval import evaluate
from deepeval.test_case import LLMTestCase

import csv

# TODO: Example test cases (replace with your own)
test_cases = [
    LLMTestCase(
        input="Write a haiku about winter.",
        actual_output="Snow whispers softly...\n(etc)",
        expected_output="A haiku about winter.",
    )
]


# TODO: use common metrics
metrics = [
    MyCustomMetricA(...),
    MyCustomMetricB(...),
]


# TODO: Load data and chunk into X second pieces (see settings).
chunks = []


results: list[EvaluationResult] = []
for i in range(100):
    # TODO: For each Chunk, LOAD into DB

    # TODO: Perform analysis on each chunk.

    r: EvaluationResult = evaluate(
        test_cases=test_cases,
        metrics=metrics,
    )

    # Append into test cases
    results.append(r)


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

with open("long_result.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
