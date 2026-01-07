from deepeval import assert_test
from deepeval.test_case import LLMTestCase

from deepeval.models import AzureOpenAIModel
from ulid import ULID

from interview_helper.ai_analysis.ai_analysis import SimpleAnalyzer
from interview_helper.ai_analysis.eval.metrics import get_metric_list
from interview_helper.context_manager.database import (
    PersistentDatabase,
    add_transcription,
)
from interview_helper.context_manager.types import AIJob, ProjectId, SessionId, UserId
from interview_helper.config import Settings

import pytest

pytestmark = pytest.mark.anyio


@pytest.fixture
def model():
    settings = Settings()  # pyright: ignore[reportCallIssue]
    return AzureOpenAIModel(
        model_name=settings.azure_eval_deployment,
        deployment_name=settings.azure_eval_deployment,
        azure_openai_api_key=settings.azure_api_key.get_secret_value(),
        openai_api_version=settings.azure_api_version,
        azure_endpoint=settings.azure_api_endpoint,
    )


# --------------------------------------------------------------------
# Unified test using all metrics
# --------------------------------------------------------------------


@pytest.mark.llm
async def test_question_quality(model: AzureOpenAIModel):
    with open("test_samples/transcript1.txt", "r") as f:
        transcript = f.read()

    config = Settings()  # pyright: ignore[reportCallIssue]
    db = PersistentDatabase.new_in_memory()

    user = UserId(ULID())
    session = SessionId(ULID())
    project = ProjectId(ULID())

    # chunk transcript by 10 lines
    transcript_chunks = [
        "\n".join(transcript.split("\n")[i : i + 10])
        for i in range(0, len(transcript.split("\n")), 10)
    ][:10]  # Get first 10 chunks only (100 lines)

    for chunk in transcript_chunks:
        _ = add_transcription(db, user, session, project, chunk)

    ai_analyzer = SimpleAnalyzer(config, db)
    follow_up_questions = await ai_analyzer.analyze(AIJob(project), [])
    question_text = "\n".join([q.question for q in follow_up_questions.questions])

    test_case = LLMTestCase(
        input="\n".join(transcript_chunks),
        actual_output=question_text,
        name="Question Quality Test",
    )

    metrics = get_metric_list(model)

    assert_test(test_case, metrics)
