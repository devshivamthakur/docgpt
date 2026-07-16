"""Prompt templates for document parsing (images and tables).

This module provides prompt templates and message builders used by
the document processing pipeline to generate captions for images
and tables extracted from uploaded documents.
"""

import logging
from typing import Any

from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

# Maximum size (in bytes) for base64-encoded image data sent to the LLM.
# Images larger than this are filtered out to avoid exceeding the
# model's context window. Roughly corresponds to ~15 MB raw image.
MAX_IMAGE_SIZE_BYTES: int = 20_000_000

# ── Prompt Templates ───────────────────────────────────────────────────

table_caption_prompt = (
    "You are a document analysis assistant. Generate a concise, "
    "natural-language description of the following table that captures "
    "its structure, key columns, rows, and important data points.\n\n"
    "Focus on:\n"
    "- The overall purpose of the table\n"
    "- Column names and their meanings\n"
    "- Notable values, trends, or patterns\n"
    "- Any relationships between data points\n\n"
    "Table data:\n{table_description}\n\n"
    "Description:"
)

_IMAGE_CAPTION_TEXT = (
    "Describe this image in detail for document indexing purposes. "
    "Include all visible text, charts, diagrams, tables, and visual "
    "elements. Be thorough and precise so the description can be "
    "used for semantic search."
)


# ── Public Helpers ─────────────────────────────────────────────────────


def build_image_caption_messages(
    images: list[dict[str, Any]],
) -> tuple[list[HumanMessage], list[dict[str, Any]]]:
    """Build multimodal ``HumanMessage`` objects for image captioning.

    Each image is converted to a data-URI and wrapped in a
    ``HumanMessage`` with a text prompt. Oversized images are
    filtered out and logged, and invalid images are skipped
    gracefully.

    Args:
        images: List of dicts with ``page_index``, ``image_index``,
            and ``image_base64`` keys.

    Returns:
        A tuple of ``(messages, valid_images)`` where ``messages``
        is a list of ``HumanMessage`` objects and ``valid_images``
        is the filtered list of image dicts that passed size and
        integrity checks.
    """
    messages: list[HumanMessage] = []
    valid_images: list[dict[str, Any]] = []

    for img in images:
        try:
            b64_data: str = img["image_base64"]

            # ── Size check ────────────────────────────────────────
            if len(b64_data) > MAX_IMAGE_SIZE_BYTES:
                logger.warning(
                    "Skipping oversized image p%d/i%d (%d bytes)",
                    img.get("page_index", "?"),
                    img.get("image_index", "?"),
                    len(b64_data),
                )
                continue

            # ── Integrity check ───────────────────────────────────
            mime_type = _detect_mime_type(b64_data)
            if mime_type is None:
                logger.warning(
                    "Skipping image p%d/i%d — unrecognisable format",
                    img.get("page_index", "?"),
                    img.get("image_index", "?"),
                )
                continue

            message = HumanMessage(
                content=[
                    {"type": "text", "text": _IMAGE_CAPTION_TEXT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64_data}"},
                    },
                ],
            )
            messages.append(message)
            valid_images.append(img)

        except KeyError as e:
            logger.warning(
                "Skipping image — missing key %s: %s", e, img.get("image_index", "?")
            )
        except Exception as e:
            logger.warning(
                "Skipping image p%d/i%d: %s",
                img.get("page_index", "?"),
                img.get("image_index", "?"),
                e,
            )

    return messages, valid_images


# ── Internal Helpers ───────────────────────────────────────────────────


def _detect_mime_type(b64_data: str) -> str | None:
    """Detect the MIME type of a base64-encoded image from its header.

    Examines the first few characters of the base64 string (which
    correspond to the file magic bytes) to determine the image format.
    """
    # Strip whitespace just in case
    header = b64_data[:12].strip()

    # PNG: starts with iVBORw0KGgo (magic \x89PNG\r\n\x1a\n)
    if header.startswith("iVBORw0KGgo"):
        return "image/png"

    # JPEG: starts with /9j/ (magic \xff\xd8\xff)
    if header.startswith("/9j/"):
        return "image/jpeg"

    # GIF87a: R0lGODdh or GIF89a: R0lGODlh
    if header.startswith("R0lGOD"):
        return "image/gif"

    # WebP: UklGR (magic RIFF....WEBP)
    if header.startswith("UklGR"):
        return "image/webp"

    # BMP: Qk (magic BM)
    if header.startswith("Qk"):
        return "image/bmp"

    # TIFF: SUkqAA (magic II* or MM\x00*)
    if header.startswith("SUkqAA") or header.startswith("TU9AKA"):
        return "image/tiff"

    logger.warning("Unrecognised image header: %r", header)
    return None
