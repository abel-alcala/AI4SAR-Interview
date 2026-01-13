from collections.abc import Sequence
from langchain_core.callbacks import BaseCallbackHandler
from interview_helper.config import Settings
from interview_helper.context_manager.database import (
    PersistentDatabase,
    get_all_transcripts,
)
from interview_helper.context_manager.types import AIJob, AIQuestion, AIResult
from langchain_openai import AzureChatOpenAI
from langchain.agents import create_agent
from pydantic import BaseModel
from textwrap import dedent
import logging
from langchain.agents.structured_output import ProviderStrategy

"""Simple interview analyzer with LLM."""

logger = logging.getLogger(__name__)


class Question(BaseModel):
    question: str
    grounding_span: str


class Analysis(BaseModel):
    questions: list[Question]


class SimpleAnalyzer:
    """Simple LLM-based interview analyzer."""

    SYSTEM_PROMPT: str = dedent("""\
        ROLE: Interview Follow-Up Generator for SAR Profiles

        You will receive a chunk of transcript from an in-depth profile interview for a Search and Rescue operation.

        Your ONLY job: propose UP TO the top 3 direct follow-up questions that are explicitly grounded in the CURRENT transcript chunk.

        Rules (follow strictly):
        1) Grounding: For EACH question, include a short verbatim quote (<= 25 words) from the transcript that the question is responding to. If you can't quote it, don't ask it.
        2) Recency: Prefer the most recent utterances when choosing what to follow up on.
        3) Scope: One question per line of inquiry. No compound questions. No “and/or”.
        4) Relevance: Do NOT ask anything already answered or implied in the chunk.
        5) SAR Focus: Favor details that clarify:
            - Mindset & intent
            - Mobility / ability to travel
            - Ability to survive (shelter, water, food, meds)
            - Ability to communicate (devices, battery, signal)
            - Ability or willingness to respond to outreach
            - Attention hooks (likes/dislikes; what draws them)
            - Past and recent behaviors / life history relevant to finding them
        6) Wording: Be brief, plain, and operational—what a real interviewer would ask **next**.
        7) Output: ONE to THREE questions, each with:
            - question (string)
            - grounding_span (short verbatim quote from the transcript)
    """)

    def __init__(self, config: Settings, db: PersistentDatabase):
        llm = AzureChatOpenAI(
            azure_endpoint=config.azure_api_endpoint,
            api_key=config.azure_api_key,
            api_version=config.azure_api_version,
            azure_deployment=config.azure_deployment,
        )

        self.llm = create_agent(  # pyright: ignore[reportUnannotatedClassAttribute, reportUnknownMemberType]
            llm,
            response_format=ProviderStrategy(Analysis),
            system_prompt=self.SYSTEM_PROMPT,
        )

        self.db: PersistentDatabase = db

    async def analyze(
        self, job: AIJob, callbacks: Sequence[BaseCallbackHandler] | None = None
    ) -> AIResult:
        """Analyze a chunk and return suggestions.

        Args:
            chunk_text: The formatted transcript chunk
            previous_context: Summary of previous chunks

        Returns:
            Analysis and suggestions from the LLM
        """

        logger.info("Running Simple AI Analyzer")

        interview_transcript = " ".join(get_all_transcripts(self.db, job.project_id))

        prompt = dedent(f"""\
            Current interview:
            {interview_transcript}

            Analyze this and identify any important questions that should have been asked but weren't.\
        """)

        response = await self.llm.ainvoke(  # pyright: ignore[reportUnknownMemberType]
            {"messages": [{"role": "user", "content": prompt}]},
            {"callbacks": list(callbacks) if callbacks is not None else None},
        )

        analysis: Analysis = response["structured_response"]  # pyright: ignore[reportAny]

        questions = [
            AIQuestion(question=q.question, grounding_span=q.grounding_span)
            for q in analysis.questions
        ]

        return AIResult(questions=questions)


class FakeAnalyzer:
    """Fake analyzer that doesn't do any actual analysis."""

    SYSTEM_PROMPT = dedent("""\
        You are a helpful assistant tasked with helping an in-depth profile interview for a search-and-rescue operation.

        Your primary goals are to help the interviewer uncover pertinent details about:
        - Mindset and intent
        - Mobility and ability to travel
        - Ability to survive
        - Ability to communicate
        - Ability or willingness to respond
        - Likes and dislikes, and what attracts the person's attention
        - Past and recent behaviors and life history

        The person who is answering questions is directing the interview and you are there to assist if you spot anything that might have been MISESED.
    """)

    def __init__(self, config: Settings, db: PersistentDatabase):
        self.db = db

    async def analyze(
        self, job: AIJob, callbacks: Sequence[BaseCallbackHandler] | None = None
    ) -> AIResult:
        _ = callbacks  # We don't use callbacks
        transcripts = " ".join(get_all_transcripts(self.db, job.project_id))
        # Use a short grounding span from the transcript for the dummy question
        grounding_span = (transcripts.splitlines()[0] if transcripts else "")[:200]
        question_text = (
            "(FakeAnalyze) I don't know what to ask? Can you provide more details?"
        )
        return AIResult(
            questions=[
                AIQuestion(question=question_text, grounding_span=grounding_span)
            ]
        )
