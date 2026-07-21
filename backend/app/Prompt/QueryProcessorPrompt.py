"""Prompt templates for query rewriting and understanding in the query processor."""


def build_query_rewrite_prompt(history_str: str, raw_query: str) -> str:
    """Build prompt to rewrite a follow-up query based on conversation history."""
    return f"""Given the following conversation history and a follow-up user query, rewrite the user query to be a standalone, search-optimized query.
The standalone query should contain all necessary context (like entity names, topics, or documents being discussed) so it can be used for search.
If the query is already standalone and does not need context from the history, return the original query exactly.
Do not add any preamble, explanation, or conversational filler. Only return the final rewritten query.

Conversation History:
{history_str}

Follow-up Query: {raw_query}

Standalone Query:"""
