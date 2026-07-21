import os
import sys
import json
import time
from typing import Dict

# Ensure backend root is in sys.path so app can be imported when running as a script directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.rag.config import rag_config
try:
    from Eval.RetrivalEval import RAGEvaluator, print_evaluation_report
except ModuleNotFoundError:
    from RetrivalEval import RAGEvaluator, print_evaluation_report
from app.services.rag.query_processor.processor import QueryProcessor
from app.services.rag.retriever.retrieval import RetrievalPipeline
import asyncio

user_id = 1


def load_evaluation_dataset(filepath: str) -> Dict:
    """Load evaluation dataset from JSON"""
    with open(filepath, "r") as f:
        return json.load(f)

async def get_retrieved_ids(query, query_processor, retriever):

    processed = await query_processor.process(query, history=[])
    sources = await retriever.retrieve(
        processed_query=processed,
        user_id=user_id,
    )
    return [str(item.id) for item in sources]

async def start_eval():
    # Load evaluation dataset using robust path relative to this script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_path = os.path.join(
        current_dir, "testing_data", "golden_dataset_125_questions.json"
    )
    dataset = load_evaluation_dataset(dataset_path)
    evaluator = RAGEvaluator(k_values=[1, 3, 5, 8])
    retriever = RetrievalPipeline(rag_config)
    query_processor = QueryProcessor(rag_config)

    retrieved_results = []

    total_queries = len(dataset["queries"])
    for idx, query in enumerate(dataset["queries"]):
        start_time = time.perf_counter()
        retrieved_ids = await get_retrieved_ids(
            query["query_text"], query_processor, retriever
        )
        processing_time = time.perf_counter() - start_time
        
        query_result = {
            "query_id": query["query_id"],
            "retrieved_ids": retrieved_ids,
            "relevant_documents": query["relevant_documents"],
            "domain": query["domain"],
            "difficulty": query["difficulty"],
            "processing_time": processing_time,
        }
        retrieved_results.append(query_result)

    results = evaluator.evaluate_batch(retrieved_results)

    return results


# # start retrival pipeline
# if __name__ == "__main__":
#     results = asyncio.run(start_eval())
#     print_evaluation_report(results)

