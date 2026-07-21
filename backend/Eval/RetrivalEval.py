#!/usr/bin/env python3
"""
DocGPT RAG Evaluation Script
Evaluates Precision@k, Recall@k, MRR, and NDCG for document retrieval
"""

import json
import numpy as np
from typing import List, Dict, Set, Tuple
from dataclasses import dataclass
from collections import defaultdict


@dataclass
class EvaluationMetrics:
    """Container for evaluation metrics"""

    precision: Dict[int, float]  # precision@k
    recall: Dict[int, float]  # recall@k
    relevant_retrieved: int
    total_relevant: int


class RAGEvaluator:
    """Evaluates RAG system performance"""

    def __init__(self, k_values: List[int] = None):
        """Initialize evaluator with k values for metrics"""
        self.k_values = k_values or [1, 3, 5, 8]

    def calculate_precision_at_k(
        self, retrieved_ids: List[str], relevant_ids: Set[str], k: int
    ) -> float:
        """Calculate Precision@k

        Precision@k = (# relevant docs in top-k) / k
        """
        if k == 0:
            return 0.0

        top_k = retrieved_ids[:k]
        relevant_in_top_k = len([doc_id for doc_id in top_k if doc_id in relevant_ids])
        return relevant_in_top_k / k

    def calculate_recall_at_k(
        self, retrieved_ids: List[str], relevant_ids: Set[str], k: int
    ) -> float:
        """Calculate Recall@k

        Recall@k = (# relevant docs in top-k) / (total # relevant docs)
        """
        if len(relevant_ids) == 0:
            return 0.0

        top_k = retrieved_ids[:k]
        relevant_in_top_k = len([doc_id for doc_id in top_k if doc_id in relevant_ids])
        return relevant_in_top_k / len(relevant_ids)

    def evaluate_query(
        self, retrieved_ids: List[str], relevant_data: Dict
    ) -> EvaluationMetrics:
        """Evaluate a single query

        Args:
            retrieved_ids: List of retrieved document IDs in order
            relevant_data: Dict containing 'relevant_documents' list with doc_id and relevance_score

        Returns:
            EvaluationMetrics object with computed metrics
        """
        # Extract relevant doc IDs and their scores
        relevant_ids = set()
        relevance_scores = {}

        for rel_doc in relevant_data.get("relevant_documents", []):
            doc_id = rel_doc["doc_id"]
            relevant_ids.add(doc_id)
            relevance_scores[doc_id] = rel_doc.get("relevance_score", 1)

        # Calculate metrics for each k
        precision = {}
        recall = {}

        for k in self.k_values:
            precision[k] = self.calculate_precision_at_k(retrieved_ids, relevant_ids, k)
            recall[k] = self.calculate_recall_at_k(retrieved_ids, relevant_ids, k)

        # Count stats
        top_10 = set(retrieved_ids[:8])
        relevant_retrieved = len(top_10 & relevant_ids)
        total_relevant = len(relevant_ids)

        return EvaluationMetrics(
            precision=precision,
            recall=recall,
            relevant_retrieved=relevant_retrieved,
            total_relevant=total_relevant,
        )

    def evaluate_batch(self, queries_with_results: List[Dict]) -> Dict:
        """Evaluate multiple queries and aggregate results

        Args:
            queries_with_results: List of dicts with 'query_id', 'retrieved_ids', 'relevant_documents'

        Returns:
            Dictionary with aggregated metrics by k value and domain
        """
        results = {}
        domain_results = defaultdict(lambda: defaultdict(list))
        difficulty_results = defaultdict(lambda: defaultdict(list))

        for query_result in queries_with_results:
            query_id = query_result["query_id"]
            retrieved_ids = query_result["retrieved_ids"]
            relevant_data = query_result
            processing_time = query_result.get("processing_time", 0.0)

            metrics = self.evaluate_query(retrieved_ids, relevant_data)

            results[query_id] = {
                "precision": metrics.precision,
                "recall": metrics.recall,
                "relevant_retrieved": metrics.relevant_retrieved,
                "total_relevant": metrics.total_relevant,
                "domain": query_result.get("domain", "unknown"),
                "difficulty": query_result.get("difficulty", "unknown"),
                "processing_time": processing_time,
            }

            # Aggregate by domain and difficulty
            domain = query_result.get("domain", "unknown")
            difficulty = query_result.get("difficulty", "unknown")

            domain_results[domain]["processing_time"].append(processing_time)
            difficulty_results[difficulty]["processing_time"].append(processing_time)

            for k in self.k_values:
                domain_results[domain][f"precision@{k}"].append(metrics.precision[k])
                domain_results[domain][f"recall@{k}"].append(metrics.recall[k])

                difficulty_results[difficulty][f"precision@{k}"].append(
                    metrics.precision[k]
                )
                difficulty_results[difficulty][f"recall@{k}"].append(metrics.recall[k])

        # Calculate aggregates
        aggregate_results = {
            "by_query": results,
            "by_domain": {},
            "by_difficulty": {},
            "overall": {},
        }

        # Domain aggregates
        for domain, metrics_dict in domain_results.items():
            aggregate_results["by_domain"][domain] = {
                k: float(np.mean(v)) if v else 0.0 for k, v in metrics_dict.items()
            }

        # Difficulty aggregates
        for difficulty, metrics_dict in difficulty_results.items():
            aggregate_results["by_difficulty"][difficulty] = {
                k: float(np.mean(v)) if v else 0.0 for k, v in metrics_dict.items()
            }

        # Overall aggregates
        all_precisions = {k: [] for k in self.k_values}
        all_recalls = {k: [] for k in self.k_values}
        all_processing_times = []

        for query_metrics in results.values():
            for k in self.k_values:
                all_precisions[k].append(query_metrics["precision"][k])
                all_recalls[k].append(query_metrics["recall"][k])
            all_processing_times.append(query_metrics.get("processing_time", 0.0))

        aggregate_results["overall"] = {
            **{f"precision@{k}": float(np.mean(v)) for k, v in all_precisions.items()},
            **{f"recall@{k}": float(np.mean(v)) for k, v in all_recalls.items()},
            "avg_processing_time": float(np.mean(all_processing_times)) if all_processing_times else 0.0,
            "min_processing_time": float(np.min(all_processing_times)) if all_processing_times else 0.0,
            "max_processing_time": float(np.max(all_processing_times)) if all_processing_times else 0.0,
            "total_queries": len(results),
        }

        return aggregate_results


def print_evaluation_report(results: Dict):
    """Print formatted evaluation report"""
    print("\n" + "=" * 80)
    print("DOCGPT RAG EVALUATION REPORT")
    print("=" * 80 + "\n")

    # Overall metrics
    print("OVERALL METRICS")
    print("-" * 40)
    overall = results["overall"]
    print(f"Total Queries: {overall['total_queries']}")
    if "avg_processing_time" in overall:
        print(f"Average Processing Time: {overall['avg_processing_time']:.4f}s")
        print(f"Min/Max Processing Time: {overall['min_processing_time']:.4f}s / {overall['max_processing_time']:.4f}s")
    
    print(f"\nPrecision:")
    for k in [1, 3, 5, 8]:
        key = f"precision@{k}"
        if key in overall:
            print(f"  @{k}: {overall[key]:.4f}")

    print(f"\nRecall:")
    for k in [1, 3, 5, 8]:
        key = f"recall@{k}"
        if key in overall:
            print(f"  @{k}: {overall[key]:.4f}")

    # By domain
    if results["by_domain"]:
        print("\nBY DOMAIN")
        print("-" * 40)
        for domain, metrics in results["by_domain"].items():
            print(f"\n{domain.upper()}:")
            print(f"  Precision@5: {metrics.get('precision@5', 0):.4f}")
            print(f"  Recall@5: {metrics.get('recall@5', 0):.4f}")
            if "processing_time" in metrics:
                print(f"  Avg Processing Time: {metrics.get('processing_time', 0):.4f}s")

    # By difficulty
    if results["by_difficulty"]:
        print("\n\nBY DIFFICULTY")
        print("-" * 40)
        for difficulty, metrics in results["by_difficulty"].items():
            print(f"\n{difficulty.upper()}:")
            print(f"  Precision@5: {metrics.get('precision@5', 0):.4f}")
            print(f"  Recall@5: {metrics.get('recall@5', 0):.4f}")
            if "processing_time" in metrics:
                print(f"  Avg Processing Time: {metrics.get('processing_time', 0):.4f}s")

    print("\n" + "=" * 80)


# if __name__ == "__main__":
#     # Load evaluation dataset
#     dataset = load_evaluation_dataset("docgpt_eval_dataset.json")

#     # Example: Simulate retrieval results (in production, these come from your Qdrant index)
#     # For now, we'll show how to use the evaluator

#     print("DocGPT Evaluation Framework Ready!")
#     print("\nUsage Example:")
#     print("=" * 60)
#     print("""
# evaluator = RAGEvaluator(k_values=[1, 3, 5, 10])

# # For each query, retrieve documents from Qdrant and add retrieved_ids
# retrieved_results = []
# for query in dataset['queries']:
#     # Mock retrieval (replace with actual Qdrant search)
#     retrieved_ids = ['doc_id_1', 'doc_id_2', ...]  # From Qdrant

#     query_result = {
#         'query_id': query['query_id'],
#         'retrieved_ids': retrieved_ids,
#         'relevant_documents': query['relevant_documents'],
#         'domain': query['domain'],
#         'difficulty': query['difficulty']
#     }
#     retrieved_results.append(query_result)

# # Evaluate all queries
# results = evaluator.evaluate_batch(retrieved_results)
# print_evaluation_report(results)
#     """)
#     print("=" * 60)
