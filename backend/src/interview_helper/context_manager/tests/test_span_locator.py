"""
Tests for the span locator functionality.
"""

from interview_helper.context_manager.span_locator import (
    find_span_in_transcripts,
    normalize_text,
    find_span_position_in_chunk,
)
from interview_helper.context_manager.types import TranscriptId
from interview_helper.context_manager.database import TranscriptChunk
from ulid import ULID


def test_normalize_text():
    """Test text normalization."""
    assert normalize_text("  Hello   World  ") == "hello world"
    assert normalize_text("HELLO world") == "hello world"
    assert normalize_text("") == ""


def test_find_span_exact_match():
    """Test finding an exact span match within a single chunk."""
    chunks: list[TranscriptChunk] = [
        {
            "transcription_id": TranscriptId(ULID()),
            "text_output": "I saw him at the park yesterday.",
            "speaker": "Speaker 1",
        },
        {
            "transcription_id": TranscriptId(ULID()),
            "text_output": "He was playing with his dog.",
            "speaker": "Speaker 1",
        },
    ]

    result = find_span_in_transcripts("at the park", chunks)
    assert result == chunks[0]["transcription_id"]


def test_find_span_fuzzy_match():
    """Test finding a fuzzy match (with minor differences)."""
    chunks: list[TranscriptChunk] = [
        {
            "transcription_id": TranscriptId(ULID()),
            "text_output": "He likes to look at the geese and the ducks.",
            "speaker": "Speaker 1",
        },
    ]

    # Try with slightly different text
    result = find_span_in_transcripts("he likes to look at the geese", chunks)
    assert result == chunks[0]["transcription_id"]


def test_find_span_across_chunks():
    """Test finding a span that crosses chunk boundaries."""
    chunk1_id = TranscriptId(ULID())
    chunk2_id = TranscriptId(ULID())

    chunks: list[TranscriptChunk] = [
        {
            "transcription_id": chunk1_id,
            "text_output": "He walked to the",
            "speaker": "Speaker 1",
        },
        {
            "transcription_id": chunk2_id,
            "text_output": "park yesterday.",
            "speaker": "Speaker 1",
        },
    ]

    # This span crosses both chunks
    result = find_span_in_transcripts("to the park", chunks)
    # Should return the first chunk where the span starts
    assert result == chunk1_id


def test_find_span_no_match():
    """Test when no match is found."""
    chunks: list[TranscriptChunk] = [
        {
            "transcription_id": TranscriptId(ULID()),
            "text_output": "I went to the store.",
            "speaker": "Speaker 1",
        },
    ]

    # Very different text - should still return first chunk as fallback
    result = find_span_in_transcripts(
        "completely different text", transcripts=chunks, similarity_threshold=0.95
    )
    assert result is None


def test_find_span_empty_inputs():
    """Test edge cases with empty inputs."""
    chunks: list[TranscriptChunk] = [
        {
            "transcription_id": TranscriptId(ULID()),
            "text_output": "Some text",
            "speaker": "Speaker 1",
        },
    ]

    # Empty span
    assert find_span_in_transcripts("", chunks) is None

    # Empty chunks
    assert find_span_in_transcripts("some text", []) is None


def test_find_span_position_exact():
    """Test finding exact position of span in chunk."""
    chunk_text = "I saw him at the park yesterday."

    result = find_span_position_in_chunk("at the park", chunk_text)
    assert result is not None
    start, end = result

    # Normalize and check
    normalized = normalize_text(chunk_text)
    assert "at the park" in normalized[start:end]


def test_find_span_position_no_match():
    """Test when position is not found."""
    chunk_text = "I went to the store."

    result = find_span_position_in_chunk("at the park", chunk_text)
    assert result is None
