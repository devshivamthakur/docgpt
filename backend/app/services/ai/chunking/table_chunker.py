"""Table caption generation via LLM.

Extracts tabular data from parsed documents and generates natural-language
captions using an LLM so the semantic meaning of tables can be indexed
and searched.
"""

import logging

from langchain_core.language_models.chat_models import BaseChatModel

from app.services.ai.schemas import ChunkType, DocumentChunk

logger = logging.getLogger(__name__)

# Maximum string length for a table representation sent to the LLM.
# Roughly ~12.5k tokens (at ~4 chars/token), well within most model
# context limits.
MAX_TABLE_STRING_CHARS = 50_000


class TableChunker:
    """Generates captions for tables using an LLM.

    Large tables are truncated before being sent to the model to avoid
    exceeding the context window. Failed tables are logged and skipped
    so one problematic table doesn't block the entire pipeline.
    """

    def __init__(self, llm: BaseChatModel) -> None:
        self.llm = llm

    def chunk(
        self,
        tables: list[dict],
        config: dict | None = None,
    ) -> list[DocumentChunk]:
        """Generate captions for *tables* and return them as chunks.

        Args:
            tables: List of dicts with ``page_index``, ``table_index``,
                and ``table_df`` (a pandas DataFrame) keys.
            config: Optional LangChain config dict for observability
                (e.g. Langfuse tracing).

        Returns:
            A list of ``DocumentChunk`` instances of type ``TABLE``.
        """
        documents: list[DocumentChunk] = []
        if not tables:
            return documents

        try:
            logger.info("Generating captions for %d tables", len(tables))

            from app.Prompt.DocumentParsingPrompt import table_caption_prompt

            # Build prompts with truncation protection
            valid_tables: list[dict] = []
            prompts: list[str] = []

            for t in tables:
                try:
                    df_str = t["table_df"].to_string()
                    safe_str = self._truncate(df_str)
                    if len(df_str) > MAX_TABLE_STRING_CHARS:
                        logger.warning(
                            "Table at p%d/t%d truncated (%d chars)",
                            t["page_index"],
                            t["table_index"],
                            len(df_str),
                        )
                    prompts.append(
                        table_caption_prompt.format(table_description=safe_str)
                    )
                    valid_tables.append(t)
                except Exception as e:
                    logger.warning(
                        "Skipping table p%d/t%d: %s",
                        t.get("page_index", "?"),
                        t.get("table_index", "?"),
                        e,
                    )

            if not valid_tables:
                return documents

            captions = self.llm.batch(prompts, config=config)
            for t, caption in zip(valid_tables, captions):
                documents.append(
                    DocumentChunk(
                        page_index=t["page_index"],
                        chunk_index=t["table_index"],
                        content=caption.content
                        if hasattr(caption, "content")
                        else caption,
                        type=ChunkType.TABLE,
                        metadata={"table_index": t["table_index"]},
                    )
                )

            logger.info("Generated %d table chunks", len(documents))
            return documents
        except Exception:
            logger.exception("Failed to chunk table content")
            raise

    @staticmethod
    def _truncate(df_string: str, max_chars: int = MAX_TABLE_STRING_CHARS) -> str:
        """Truncate a DataFrame string to stay within token limits.

        Shows the first 30 rows, last 10 rows, and a shape summary.
        """
        if len(df_string) <= max_chars:
            return df_string

        lines = df_string.split("\n")
        header = lines[:1]
        body = lines[1:]
        head = body[:30]
        tail = body[-10:] if len(body) > 10 else []

        truncated = (
            "\n".join(header + head)
            + f"\n\n... ({len(body) - 40} rows omitted) ...\n\n"
            + "\n".join(header + tail)
            + f"\n\n[Shape: {len(body)} rows]"
        )
        if len(truncated) > max_chars:
            truncated = truncated[:max_chars] + "\n\n[Truncated]"
        return truncated
