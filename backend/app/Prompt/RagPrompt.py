"""Prompt templates for the RAG conversation pipeline.

These templates are consumed by ``PromptBuilder`` to assemble the final
LLM prompt with context, history, summary, and the user query.
"""

CONVERSATION_SUMMARY_PROMPT = """Summarise the following conversation concisely, capturing key points and decisions. Incorporate the previous summary if available.

## Previous Summary
{summary}

## Conversation History
{history}

## Summary
Provide a concise summary of the conversation above, integrating it with the previous summary."""
