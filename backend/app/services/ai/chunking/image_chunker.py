"""Image caption generation via multimodal LLM.

Generates natural-language descriptions for images extracted from
documents so that visual content becomes searchable through semantic
embedding.
"""

import logging

from langchain_core.language_models.chat_models import BaseChatModel

from app.services.ai.schemas import ChunkType, DocumentChunk

logger = logging.getLogger(__name__)


class ImageChunker:
    """Generates captions for images using a multimodal LLM.

    Images are sent as base64-encoded data URIs inside OpenAI-compatible
    content blocks. Oversized images are filtered by the prompt builder
    to avoid exceeding the model's context window.
    """

    def __init__(self, llm: BaseChatModel) -> None:
        self.llm = llm

    def chunk(
        self,
        images: list[dict],
        config: dict | None = None,
    ) -> list[DocumentChunk]:
        """Generate captions for *images* and return them as chunks.

        Args:
            images: List of dicts with ``page_index``, ``image_index``,
                and ``image_base64`` keys.
            config: Optional LangChain config dict for observability
                (e.g. Langfuse tracing).

        Returns:
            A list of ``DocumentChunk`` instances of type ``IMAGE``.
        """
        documents: list[DocumentChunk] = []
        if not images:
            return documents

        try:
            logger.info("Generating captions for %d images", len(images))

            from app.Prompt.DocumentParsingPrompt import build_image_caption_messages

            # Build multimodal HumanMessages — oversized images are
            # filtered internally by build_image_caption_messages
            messages, valid_images = build_image_caption_messages(images)

            if not valid_images:
                logger.info("No valid images to process after size checks")
                return documents

            # batch() expects list[list[BaseMessage]]
            captions = self.llm.batch([[m] for m in messages], config=config)

            for img, caption in zip(valid_images, captions):
                documents.append(
                    DocumentChunk(
                        page_index=img["page_index"],
                        chunk_index=img["image_index"],
                        content=caption.content
                        if hasattr(caption, "content")
                        else caption,
                        type=ChunkType.IMAGE,
                        metadata={"image_index": img["image_index"]},
                    )
                )

            logger.info("Generated %d image chunks", len(documents))
            return documents
        except Exception:
            logger.exception("Failed to chunk image content")
            raise
