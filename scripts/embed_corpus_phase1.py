"""
embed_corpus_phase1.py
전체 코퍼스(BODY_COLLECTED + clean_text 존재) → voyage-3-large 임베딩 생성
출력: data/embeddings_phase1.npy, data/embeddings_phase1_ids.npy
"""
import json
import os
import sqlite3
import time
from pathlib import Path

import numpy as np
import voyageai
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "archive.db"
OUT_EMBEDDINGS = PROJECT_ROOT / "data" / "embeddings_phase1.npy"
OUT_IDS = PROJECT_ROOT / "data" / "embeddings_phase1_ids.npy"
OUT_FAILED = PROJECT_ROOT / "data" / "embeddings_phase1_failed.json"

BATCH_SIZE = 128
MODEL = "voyage-3-large"
PRICE_PER_M = 0.18  # USD per million tokens


def fetch_corpus() -> list[tuple[int, str]]:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    rows = conn.execute(
        """
        SELECT article_id, clean_text
        FROM articles
        WHERE status = 'BODY_COLLECTED'
          AND clean_text IS NOT NULL
          AND length(clean_text) > 0
        ORDER BY article_id
        """
    ).fetchall()
    conn.close()
    return rows


def embed_with_retry(
    vo: voyageai.Client,
    texts: list[str],
    max_retries: int = 3,
) -> tuple[list[list[float]], int]:
    delay = 1
    for attempt in range(max_retries):
        try:
            result = vo.embed(texts=texts, model=MODEL, input_type="document")
            return result.embeddings, result.total_tokens
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"\n  [WARN] embed attempt {attempt+1} failed: {e}. retrying in {delay}s...")
                time.sleep(delay)
                delay *= 2
            else:
                raise


def main():
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        raise RuntimeError("VOYAGE_API_KEY environment variable not set")

    print("=== Step B: 코퍼스 임베딩 생성 ===")
    print(f"DB: {DB_PATH}")

    rows = fetch_corpus()
    n_total = len(rows)
    ids = [r[0] for r in rows]
    texts = [r[1] for r in rows]

    # 비용 추정 (rough: 평균 500 토큰 가정)
    avg_tokens_est = 500
    est_total_tokens = n_total * avg_tokens_est
    est_cost = est_total_tokens / 1_000_000 * PRICE_PER_M
    print(f"추출된 코퍼스: {n_total:,}건")
    print(f"예상 토큰 수: ~{est_total_tokens:,} (평균 {avg_tokens_est} tok/doc 가정)")
    print(f"예상 비용: ~${est_cost:.4f}")

    vo = voyageai.Client()

    all_embeddings: list[list[float]] = []
    all_ids: list[int] = []
    failed_ids: list[int] = []
    total_tokens = 0

    batches = [
        (ids[i : i + BATCH_SIZE], texts[i : i + BATCH_SIZE])
        for i in range(0, n_total, BATCH_SIZE)
    ]

    with tqdm(total=n_total, desc="임베딩", unit="doc") as pbar:
        for batch_ids, batch_texts in batches:
            try:
                embeddings, tokens = embed_with_retry(vo, batch_texts)
                all_embeddings.extend(embeddings)
                all_ids.extend(batch_ids)
                total_tokens += tokens
            except Exception as e:
                print(f"\n  [ERROR] batch starting id={batch_ids[0]} failed after retries: {e}")
                failed_ids.extend(batch_ids)

            pbar.update(len(batch_ids))
            time.sleep(0.1)

    actual_cost = total_tokens / 1_000_000 * PRICE_PER_M
    print(f"\n실제 토큰 수: {total_tokens:,}")
    print(f"실제 비용: ${actual_cost:.4f}")
    print(f"실패 건수: {len(failed_ids)}")

    emb_array = np.array(all_embeddings, dtype=np.float32)
    ids_array = np.array(all_ids, dtype=np.int64)

    np.save(OUT_EMBEDDINGS, emb_array)
    np.save(OUT_IDS, ids_array)
    print(f"저장: {OUT_EMBEDDINGS}  shape={emb_array.shape}")
    print(f"저장: {OUT_IDS}  shape={ids_array.shape}")

    if failed_ids:
        OUT_FAILED.write_text(json.dumps(failed_ids, ensure_ascii=False), encoding="utf-8")
        print(f"실패 목록: {OUT_FAILED}")


if __name__ == "__main__":
    main()
