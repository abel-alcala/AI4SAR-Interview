"""
Utilities for finding and localizing text spans within transcripts.

This module provides functions to locate specific text spans (like AI-generated
grounding quotes) within a collection of transcript chunks, handling cases where
the span might cross chunk boundaries or contain minor differences due to
transcription variations.
"""

from difflib import SequenceMatcher
from interview_helper.context_manager.types import TranscriptId
from interview_helper.context_manager.database import TranscriptChunk


def normalize_text(text: str) -> str:
    """
    Normalize text for comparison by lowercasing and removing extra whitespace.

    Args:
        text: The text to normalize

    Returns:
        Normalized text string
    """
    return " ".join(text.lower().split())


def find_span_in_transcripts(
    span: str, transcripts: list[TranscriptChunk], similarity_threshold: float = 0.85
) -> TranscriptId | None:
    """
    Find the transcript chunk that contains or best matches the given span.

    This function handles several cases:
    1. Exact substring match within a single chunk
    2. Fuzzy match within a single chunk (for transcription variations)
    3. Span that crosses chunk boundaries (returns the first chunk)

    Args:
        span: The text span to locate (e.g., grounding quote from AI)
        transcripts: List of transcript chunks to search through
        similarity_threshold: Minimum similarity ratio (0-1) for fuzzy matching

    Returns:
        TranscriptId of the chunk where the span starts, or None if not found
    """
    if not span or not transcripts:
        return None

    normalized_span = normalize_text(span)
    span_words = normalized_span.split()

    # If span is very short, we need higher confidence
    if len(span_words) < 3:
        similarity_threshold = max(similarity_threshold, 0.95)

    best_match_id: TranscriptId | None = None
    best_similarity = 0.0

    # First pass: Look for exact substring matches
    for chunk in transcripts:
        normalized_chunk = normalize_text(chunk["text_output"])

        if normalized_span in normalized_chunk:
            return chunk["transcription_id"]

    # Second pass: Fuzzy matching within individual chunks
    for chunk in transcripts:
        normalized_chunk = normalize_text(chunk["text_output"])

        # Use SequenceMatcher for similarity
        similarity = SequenceMatcher(None, normalized_span, normalized_chunk).ratio()

        if similarity > best_similarity:
            best_similarity = similarity
            best_match_id = chunk["transcription_id"]

    # Third pass: Check if span crosses chunk boundaries
    # by building a sliding window across chunks
    for i in range(len(transcripts)):
        # Build a combined text from this chunk and the next few
        combined_chunks: list[str] = []
        combined_ids: list[TranscriptId] = []

        for j in range(i, min(i + 3, len(transcripts))):  # Check up to 3 chunks
            combined_chunks.append(transcripts[j]["text_output"])
            combined_ids.append(transcripts[j]["transcription_id"])

        combined_text = " ".join(combined_chunks)
        normalized_combined = normalize_text(combined_text)

        if normalized_span in normalized_combined:
            # Return the first chunk ID where the span starts
            return combined_ids[0]

        # Also check fuzzy match across boundaries
        similarity = SequenceMatcher(None, normalized_span, normalized_combined).ratio()

        if similarity > best_similarity:
            best_similarity = similarity
            best_match_id = combined_ids[0]

    # Return best match if it meets threshold
    if best_similarity >= similarity_threshold:
        return best_match_id

    # If no good match found, return the first chunk as fallback
    # (span might be a summary or paraphrase rather than exact quote)
    return None


def find_span_position_in_chunk(span: str, chunk_text: str) -> tuple[int, int] | None:
    """
    Find the start and end character positions of a span within a chunk.

    This is useful for highlighting the exact position in the frontend.

    Args:
        span: The text span to locate
        chunk_text: The text of the chunk to search in

    Returns:
        Tuple of (start_pos, end_pos) character indices, or None if not found
    """
    normalized_span = normalize_text(span)
    normalized_chunk = normalize_text(chunk_text)

    # Try exact match first
    start_pos = normalized_chunk.find(normalized_span)
    if start_pos != -1:
        return (start_pos, start_pos + len(normalized_span))

    # For fuzzy matching, we'd need more sophisticated logic
    # For now, return None if exact match fails
    return None
