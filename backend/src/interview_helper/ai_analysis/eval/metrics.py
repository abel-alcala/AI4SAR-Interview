from typing import override
from deepeval.metrics.g_eval import Rubric
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from deepeval.metrics import BaseMetric, GEval

from deepeval.models import AzureOpenAIModel


def get_metric_list(model: AzureOpenAIModel) -> list[BaseMetric]:
    return [
        relevance_metric(model),
        direct_followup_metric(model),
        non_redundancy_metric(model),
        QuestionQuantity(),
        interviewer_adoption_metric(model),
    ]


def relevance_metric(model: AzureOpenAIModel):
    return GEval(
        name="Question Relevance",
        evaluation_steps=[
            "Read the provided transcript and carefully consider the topic of the conversation.",
            "Read the follow-up question(s) generated and determine if they focus on at least one of these areas: "
            + "mobility/ability to travel, ability to survive, ability to communicate, "
            + "ability/willingness to respond, likes/dislikes, what attracts the person's attention, "
            + "past and recent behaviors, or life history.",
            "Heavily penalize any question that does not target one of these areas.",
        ],
        threshold=0.8,
        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
        model=model,
        rubric=[
            Rubric(score_range=(0, 2), expected_outcome="Not relevant at all."),
            Rubric(score_range=(3, 6), expected_outcome="Some are relevant."),
            Rubric(score_range=(7, 9), expected_outcome="Most are relevant."),
            Rubric(
                score_range=(10, 10), expected_outcome="All questions are relevant."
            ),
        ],
    )


def direct_followup_metric(model: AzureOpenAIModel):
    return GEval(
        name="Direct Follow-Up",
        evaluation_steps=[
            "Compare the follow-up question(s) to the provided transcript/context.",
            "Determine if the questions are direct follow-ups that build on details explicitly present "
            + "rather than introducing unrelated topics.",
            "Heavily penalize questions that are generic or unrelated to the transcript details.",
        ],
        threshold=0.8,
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
        ],
        model=model,
        rubric=[
            Rubric(
                score_range=(0, 2),
                expected_outcome="Not all questions are direct follow-ups.",
            ),
            Rubric(score_range=(3, 6), expected_outcome="Questions kind of follow up."),
            Rubric(
                score_range=(10, 10),
                expected_outcome="All questions are direct follow-ups to the conversation.",
            ),
        ],
    )


def non_redundancy_metric(model: AzureOpenAIModel):
    return GEval(
        name="Non-Redundancy",
        evaluation_steps=[
            "Review the transcript/context and check whether the proposed question(s) are already answered "
            + "or trivially implied in the transcript.",
            "Penalize redundancy — questions that restate or repeat information already clear in context.",
        ],
        threshold=0.8,
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
        ],
        model=model,
        rubric=[
            Rubric(
                score_range=(0, 2), expected_outcome="Most questions are redundant."
            ),
            Rubric(
                score_range=(3, 6), expected_outcome="Some questions are redundant."
            ),
            Rubric(score_range=(7, 9), expected_outcome="Most questions are novel."),
            Rubric(score_range=(10, 10), expected_outcome="All questions are novel."),
        ],
    )


class QuestionQuantity(BaseMetric):
    def __init__(self, threshold: float = 0.5):
        self.threshold: float = threshold

    @override
    def measure(self, test_case: LLMTestCase):
        # Count number of lines in test_case.actual_output
        assert test_case.actual_output, "Actual output is empty"
        num_questions = len(
            [line for line in test_case.actual_output.split("\n") if line.strip()]
        )
        # 5+ = 0, 3-4 = 0.5, 1-2 = 1.0
        number_of_questions_str = f"Number of questions generated: {num_questions}."

        self.score: float | None = 1.0
        self.reason: str | None = ""

        if num_questions >= 5:
            self.score = 0.0
            self.reason = (
                number_of_questions_str + "\n\n>= 5 questions generated.\nScore: 0.0"
            )
        elif num_questions >= 3:
            self.score = 0.5
            self.reason = (
                number_of_questions_str + "\n\n3-4 questions generated.\nScore: 0.5"
            )
        else:
            self.score = 1.0
            self.reason = (
                number_of_questions_str + "\n\n1-2 questions generated.\nScore: 1.0"
            )

        self.success: bool | None = self.score >= self.threshold
        return self.score

    @override
    async def a_measure(self, test_case: LLMTestCase):
        return self.measure(test_case)

    @override
    def is_successful(self) -> bool:
        assert self.success is not None, "Score has not been measured yet"
        return self.success

    @property
    @override
    def __name__(self) -> str:  # pyright: ignore[reportIncompatibleMethodOverride]
        return "Question Quantity Metric"


def interviewer_adoption_metric(model: AzureOpenAIModel):
    return GEval(
        name="Interviewer Adoption Likelihood",
        evaluation_steps=[
            "Read the follow-up question(s) and judge how likely an interviewer would actually use them.",
            "Consider clarity, actionability, specificity, tone, and feasibility under time pressure.",
            "Penalize vague, unprofessional, or impractical questions.",
            "Reward concise, useful, and realistic follow-ups that naturally extend the conversation.",
        ],
        threshold=0.8,
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT],
        model=model,
        rubric=[
            Rubric(
                score_range=(0, 2),
                expected_outcome="Very unlikely to be used by an interviewer.",
            ),
            Rubric(
                score_range=(3, 6),
                expected_outcome="Somewhat likely to be used by an interviewer.",
            ),
            Rubric(
                score_range=(7, 9),
                expected_outcome="Likely to be used by an interviewer.",
            ),
            Rubric(
                score_range=(10, 10),
                expected_outcome="Very likely to be used by an interviewer.",
            ),
        ],
    )
