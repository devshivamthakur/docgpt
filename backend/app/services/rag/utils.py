"""Utility helpers for the RAG pipeline."""

from __future__ import annotations

from typing import Any


def extract_chunk_content(chunk_content: Any) -> str:
    """Extract text content from various chunk formats.

    Handles:
    • Simple strings
    • List of dicts (Gemini format: ``[{"text": "..."}, {"text": "..."}]``)
    • ``None`` / empty values
    • Nested or unexpected structures (fallback to ``str()``)

    Args:
        chunk_content: The ``content`` attribute from an LLM stream chunk.

    Returns:
        Extracted text string (may be empty).
    """
    if chunk_content is None:
        return ""

    if isinstance(chunk_content, str):
        return chunk_content

    if isinstance(chunk_content, list):
        texts: list[str] = []
        for item in chunk_content:
            if isinstance(item, dict):
                # Gemini style: [{"text": "Hello"}, {"text": " world"}]
                if "text" in item:
                    val = item["text"]
                    if val is not None:
                        texts.append(str(val))
                # Also handle an "type" + "text" pattern sometimes seen
                elif "type" in item and "text" in item:
                    val = item["text"]
                    if val is not None:
                        texts.append(str(val))
            elif isinstance(item, str):
                texts.append(item)
        return "".join(texts)

    # Fallback — last resort
    return str(chunk_content)
