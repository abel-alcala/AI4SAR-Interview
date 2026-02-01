from collections.abc import Sequence
from dataclasses import dataclass
from langfuse.langchain.CallbackHandler import LangchainCallbackHandler
from langchain_core.callbacks import BaseCallbackHandler
from ulid import ULID
from interview_helper.config import Settings
from interview_helper.context_manager.database import (
    PersistentDatabase,
    full_text_search_ai_analysis,
    full_text_search_transcriptions,
    get_all_transcripts_since_last_analysis,
    get_most_recent_summary,
)
from interview_helper.context_manager.types import (
    AIJob,
    AIQuestion,
    AIResult,
    ProjectId,
    TranscriptId,
)
from langchain_openai import AzureChatOpenAI
from langchain.tools import ToolRuntime, tool  # pyright: ignore[reportUnknownVariableType]
from langchain.agents import create_agent  # pyright: ignore[reportUnknownVariableType]
from pydantic import BaseModel
from textwrap import dedent
import logging
from langchain.agents.structured_output import ProviderStrategy
from langfuse.langchain import CallbackHandler
from langfuse import Langfuse


"""Simple interview analyzer with LLM."""

logger = logging.getLogger(__name__)


class Question(BaseModel):
    question: str
    grounding_span: str


class Analysis(BaseModel):
    questions: list[Question]
    summary: str


@dataclass(frozen=True)
class ProjectContext:
    project_id: ProjectId


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
           As well as a brief summary of the entire situation so far, based on your knowledge.

        ALWAYS use the provided TOOLS to check for duplicates or 
        gather more context from the transcript history before finalizing your questions.

    """)

    def __init__(self, config: Settings, db: PersistentDatabase):
        llm = AzureChatOpenAI(
            azure_endpoint=config.azure_api_endpoint,
            api_key=config.azure_api_key,
            api_version=config.azure_api_version,
            azure_deployment=config.azure_deployment,
        )

        if (
            config.LANGFUSE_SECRET_KEY is not None
            and config.LANGFUSE_PUBLIC_KEY is not None
            and config.LANGFUSE_BASE_URL is not None
        ):
            _ = Langfuse(
                public_key=config.LANGFUSE_PUBLIC_KEY,
                secret_key=config.LANGFUSE_SECRET_KEY.get_secret_value(),
                base_url=config.LANGFUSE_BASE_URL,
            )

            self.langfuse_handler: LangchainCallbackHandler = CallbackHandler()

        @tool
        def search_transcript(
            fts5_query_phrases: list[str],
            runtime: ToolRuntime[ProjectContext],  # pyright: ignore[reportUnknownParameterType]
        ) -> str:
            """Search the transcript for relevant quotes.

            Args:
                fts5_query_phrases:
                    Search for phrases in fts5_query_phrases (combined with OR)
                    Do not use any punctuation in the search
                    Use SQLite FTS5 syntax.
            Returns:
                A string containing up to 5 most relevant quotes from the transcript.
            """
            project_id = runtime.context.project_id
            results = full_text_search_transcriptions(
                db, project_id, fts5_query_phrases
            )

            if len(results) == 0:
                return "No relevant information found."
            elif len(results) > 5:
                return (
                    "\n".join(results[:5])
                    + f"\n\n ...and {len(results) - 5} more results found."
                )
            elif len(results) <= 5:
                return "\n".join(results)

            assert False, "Unreachable code in search_transcript tool."

        @tool
        def search_previouslly_asked_questions(
            fts5_query_phrases: list[str],
            runtime: ToolRuntime[ProjectContext],  # pyright: ignore[reportUnknownParameterType]
        ) -> str:
            """Search previously asked questions to check for duplicates.

            Args:
                fts5_query_phrases:
                    Search for phrases in fts5_query_phrases (combined with OR)
                    Do not use any punctuation in the search
                    Use SQLite FTS5 syntax.
            Returns:
                A string containing up to 5 most relevant previously asked questions.
            """
            project_id = runtime.context.project_id
            results = full_text_search_ai_analysis(db, project_id, fts5_query_phrases)

            if len(results) == 0:
                return "No relevant information found."
            elif len(results) > 5:
                return (
                    "\n".join(results[:5])
                    + f"\n\n ...and {len(results) - 5} more results found."
                )
            elif len(results) <= 5:
                return "\n".join(results)

            assert False, "Unreachable code in search_previouslly_asked_questions tool."

        self.llm = create_agent(  # pyright: ignore[reportUnannotatedClassAttribute]
            llm,
            response_format=ProviderStrategy(Analysis),
            tools=[search_transcript, search_previouslly_asked_questions],
            context_schema=ProjectContext,
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

        # Get all transcripts since
        summary = (
            get_most_recent_summary(self.db, job.project_id) or "Start of interview."
        )
        transcripts = get_all_transcripts_since_last_analysis(self.db, job.project_id)
        interview_transcript = " ".join(
            [transcript["text_output"] for transcript in transcripts]
        )

        prompt = dedent(f"""\

            Summary of previous interview context:
            {summary}

            Current chunk of interview transcript:
            {interview_transcript}

            Analyze this and identify any important questions that should have been asked but weren't.
            
            Please use the tools in order to detect any duplicates or gain further context by searching the history.\
        """)

        response = await self.llm.ainvoke(  # pyright: ignore[reportUnknownMemberType]
            {"messages": [{"role": "user", "content": prompt}]},
            {
                "callbacks": list(callbacks) + [self.langfuse_handler]
                if callbacks is not None
                else [self.langfuse_handler]
            },
            context=ProjectContext(project_id=job.project_id),
        )

        analysis: Analysis = response["structured_response"]  # pyright: ignore[reportAny]

        questions = [
            AIQuestion(question=q.question, grounding_span=q.grounding_span)
            for q in analysis.questions
        ]

        return AIResult(
            questions=questions,
            transcript_context_start=transcripts[0]["transcription_id"],
            transcript_context_end=transcripts[-1]["transcription_id"],
            summary=analysis.summary,
        )


class FakeAnalyzer:
    """Fake analyzer that doesn't do any actual analysis."""

    def __init__(self, config: Settings, db: PersistentDatabase):
        _ = config
        _ = db

    async def analyze(
        self, job: AIJob, callbacks: Sequence[BaseCallbackHandler] | None = None
    ) -> AIResult:
        _ = callbacks  # We don't use callbacks
        _ = job
        return AIResult(
            questions=[],
            transcript_context_start=TranscriptId(ULID()),
            transcript_context_end=TranscriptId(ULID()),
            summary="No analysis performed.",
        )
