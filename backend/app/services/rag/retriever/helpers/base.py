"""Abstract base class for retrieval helper tools.

All retrieval helpers in this package (QdrantSearch, Reranker, cache
classes) follow a common ``run()`` pattern.  This module defines the
:class:`RetrievalHelper` protocol that each helper implements.

These classes are **not** LangChain tools — they are internal async
helpers used by the :class:`~app.services.rag.retriever.retrieval.RetrievalAgent`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class RetrievalHelper(ABC):
    """Abstract base class for internal retrieval helpers.

    Subclasses must implement :meth:`run` with a signature appropriate
    to their specific role in the retrieval pipeline.
    """

    @abstractmethod
    async def run(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the retrieval-helper operation.

        Parameters and return types are defined by each subclass.
        """
        ...
