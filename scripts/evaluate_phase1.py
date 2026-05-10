"""
evaluate_phase1.py
voyage-3-large 임베딩 기반 retrieval 평가 (recall@1/5/10, MRR)
"""
import json
from datetime import datetime
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
CORP_EMB_PATH = PROJECT_ROOT / "data" / "embeddings_phase1.npy"
CORP_IDS_PATH = PROJECT_ROOT / "data" / "embeddings_phase1_ids.npy"
QUERY_EMB_PATH = PROJECT_ROOT / "data" / "query_embeddings_phase1.npy"
QUERY_META_PATH = PROJECT_ROOT / "data" / "query_metadata_phase1.json"
EVAL_DOC_PATH = PROJECT_ROOT / "docs" / "rag_phase1_eval.md"
FAILED_PATH = PROJECT_ROOT / "data" / "embeddings_phase1_failed.json"

TOP_K = 100


def cosine_similarity_matrix(query_embs: np.ndarray, doc_embs: np.ndarray) -> np.ndarray:
    """normalize 후 dot product → cosine similarity. shape: (Q, D)"""
    q_norm = query_embs / np.linalg.norm(query_embs, axis=1, keepdims=True)
    d_norm = doc_embs / np.linalg.norm(doc_embs, axis=1, keepdims=True)
    return q_norm @ d_norm.T


def main():
    print("=== Step D: Retrieval 평가 ===")

    corp_embs = np.load(CORP_EMB_PATH)
    corp_ids = np.load(CORP_IDS_PATH)
    query_embs = np.load(QUERY_EMB_PATH)
    metadata = json.loads(QUERY_META_PATH.read_text(encoding="utf-8"))

    n_corpus = len(corp_ids)
    n_queries = len(metadata)
    print(f"코퍼스 크기: {n_corpus:,}  쿼리 수: {n_queries}")
    print(f"코퍼스 임베딩 shape: {corp_embs.shape}")
    print(f"쿼리 임베딩 shape: {query_embs.shape}")

    sim_matrix = cosine_similarity_matrix(query_embs, corp_embs)

    id_to_pos = {int(aid): i for i, aid in enumerate(corp_ids)}

    results = []
    for qi, meta in enumerate(metadata):
        gt_id = meta["article_id"]
        scores = sim_matrix[qi]

        top_k_idx = np.argpartition(scores, -TOP_K)[-TOP_K:]
        top_k_idx = top_k_idx[np.argsort(scores[top_k_idx])[::-1]]

        top_k_ids = [int(corp_ids[i]) for i in top_k_idx]
        top_k_scores = [float(scores[i]) for i in top_k_idx]

        rank = None
        if gt_id in id_to_pos:
            gt_pos = id_to_pos[gt_id]
            gt_score = float(scores[gt_pos])
            rank_raw = int(np.sum(scores > gt_score)) + 1
            rank = rank_raw if rank_raw <= TOP_K else None

        results.append({
            "query": meta["query"],
            "gt_id": gt_id,
            "top1_id": top_k_ids[0],
            "top1_score": top_k_scores[0],
            "rank": rank,
            "top5_ids": top_k_ids[:5],
            "top10_ids": top_k_ids[:10],
        })

    recall_1 = sum(1 for r in results if r["rank"] == 1) / n_queries
    recall_5 = sum(1 for r in results if r["rank"] is not None and r["rank"] <= 5) / n_queries
    recall_10 = sum(1 for r in results if r["rank"] is not None and r["rank"] <= 10) / n_queries
    mrr = sum((1.0 / r["rank"]) if r["rank"] is not None else 0.0 for r in results) / n_queries

    print(f"\n=== 집계 지표 ===")
    print(f"recall@1  : {recall_1:.4f} ({recall_1*100:.1f}%)")
    print(f"recall@5  : {recall_5:.4f} ({recall_5*100:.1f}%)")
    print(f"recall@10 : {recall_10:.4f} ({recall_10*100:.1f}%)")
    print(f"MRR       : {mrr:.4f}")

    if recall_10 >= 0.70:
        verdict = "PASS (voyage-3-large 한국어 도메인 작동 확인)"
    elif recall_10 >= 0.50:
        verdict = "CONDITIONAL PASS (청킹 전략으로 보완 가능)"
    else:
        verdict = "FAIL (모델 재검토 필요)"
    print(f"\n판정: {verdict}")

    # 비용 추정 읽기
    cost_str = "unknown"
    try:
        import re
        existing = EVAL_DOC_PATH.read_text(encoding="utf-8")
        m = re.search(r"Embedding Cost.*?\$([0-9.]+)", existing)
        if m:
            cost_str = "$" + m.group(1)
    except Exception:
        pass

    run_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    per_query_rows = []
    for i, r in enumerate(results):
        rank_str = str(r["rank"]) if r["rank"] is not None else ">100"
        per_query_rows.append(
            f"| {i+1:02d} | {r['query']} | {r['gt_id']} | {r['top1_id']} | {r['top1_score']:.4f} | {rank_str} |"
        )

    eval_section = f"""
## Evaluation Results (v2 — 키워드 포함 쿼리)

**Model**: voyage-3-large (1024 dim)
**Run Date**: {run_time}
**Corpus Size**: {n_corpus:,}건
**Embedding Cost**: {cost_str}

### Aggregate Metrics
- recall@1: {recall_1:.4f} ({recall_1*100:.1f}%)
- recall@5: {recall_5:.4f} ({recall_5*100:.1f}%)
- recall@10: {recall_10:.4f} ({recall_10*100:.1f}%)
- MRR: {mrr:.4f}

**판정**: {verdict}

### Per-Query Results

| # | Query | Ground Truth ID | Top-1 ID | Top-1 Score | Rank of GT |
|---|-------|-----------------|----------|-------------|------------|
{chr(10).join(per_query_rows)}
"""

    existing_md = EVAL_DOC_PATH.read_text(encoding="utf-8")
    updated_md = existing_md.rstrip() + "\n" + eval_section
    EVAL_DOC_PATH.write_text(updated_md, encoding="utf-8")
    print(f"\ndocs/rag_phase1_eval.md 업데이트 완료")


if __name__ == "__main__":
    main()
