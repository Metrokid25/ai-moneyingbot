"""
embed_queries_phase1.py
rag_samples.json의 synthetic_query 20개 → voyage-3-large query 임베딩 생성
출력: data/query_embeddings_phase1.npy, data/query_metadata_phase1.json
"""
import json
import os
from pathlib import Path

import numpy as np
import voyageai

PROJECT_ROOT = Path(__file__).parent.parent
SAMPLES_PATH = PROJECT_ROOT / "data" / "rag_samples.json"
OUT_EMBEDDINGS = PROJECT_ROOT / "data" / "query_embeddings_phase1.npy"
OUT_METADATA = PROJECT_ROOT / "data" / "query_metadata_phase1.json"

MODEL = "voyage-3-large"


def main():
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        raise RuntimeError("VOYAGE_API_KEY environment variable not set")

    print("=== Step C: 쿼리 임베딩 생성 ===")

    samples = json.loads(SAMPLES_PATH.read_text(encoding="utf-8"))
    print(f"로드된 샘플 수: {len(samples)}")

    for s in samples:
        if "synthetic_query" not in s:
            raise ValueError(f"article_id={s['article_id']}에 synthetic_query 필드 없음")

    queries = [s["synthetic_query"] for s in samples]
    metadata = [
        {"query": s["synthetic_query"], "article_id": s["article_id"]}
        for s in samples
    ]

    print("쿼리 목록:")
    for i, m in enumerate(metadata):
        print(f"  {i+1:02d}. id={m['article_id']}  {m['query']}")

    vo = voyageai.Client()
    result = vo.embed(texts=queries, model=MODEL, input_type="query")
    embeddings = result.embeddings
    print(f"\n쿼리 임베딩 완료: total_tokens={result.total_tokens}")

    emb_array = np.array(embeddings, dtype=np.float32)
    np.save(OUT_EMBEDDINGS, emb_array)
    OUT_METADATA.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"저장: {OUT_EMBEDDINGS}  shape={emb_array.shape}")
    print(f"저장: {OUT_METADATA}")


if __name__ == "__main__":
    main()
