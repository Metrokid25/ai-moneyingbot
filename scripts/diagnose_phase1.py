"""
diagnose_phase1.py
voyage-3-large retrieval CONDITIONAL PASS 원인 진단 — 가설 1/2/3 판정
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
CORP_EMB_PATH = PROJECT_ROOT / "data" / "embeddings_phase1.npy"
CORP_IDS_PATH = PROJECT_ROOT / "data" / "embeddings_phase1_ids.npy"
QUERY_EMB_PATH = PROJECT_ROOT / "data" / "query_embeddings_phase1.npy"
QUERY_META_PATH = PROJECT_ROOT / "data" / "query_metadata_phase1.json"
DB_PATH = PROJECT_ROOT / "data" / "archive.db"
OUT_REPORT = PROJECT_ROOT / "docs" / "rag_phase1_diagnosis.md"

TOP_K = 100

LINGO_KEYWORDS = [
    "자전", "물량", "받아간다", "떨군다", "쌍바닥", "눌림", "매집", "분산",
    "종가베팅", "세력", "끌어올린다", "털고나간다", "받쳐준다", "손바뀜",
    "받아가", "떨궈", "끌어올려", "털고", "받쳐",
]

# Classification thresholds (conservative)
H2_SIM_HIGH = 0.90   # GT ↔ top1 corpus cosine sim > this → 같은 주제 글 경쟁 (H2)
H1_SIM_LOW  = 0.85   # GT ↔ top1 corpus cosine sim < this AND not H3 → 다른 방향 검색 (H1)
# 0.85 ~ 0.90 구간 = 분류 불가 (애매)


def cosine_sim_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a_n = a / np.linalg.norm(a, axis=1, keepdims=True)
    b_n = b / np.linalg.norm(b, axis=1, keepdims=True)
    return a_n @ b_n.T


def get_lingo(text: str) -> list[str]:
    return [kw for kw in LINGO_KEYWORDS if kw in text]


def fetch_text(conn, article_id: int) -> str:
    row = conn.execute(
        "SELECT clean_text FROM articles WHERE article_id=?", (article_id,)
    ).fetchone()
    return (row[0] or "") if row else ""


def excerpt(text: str, n: int = 300) -> str:
    if not text:
        return "(본문 없음)"
    t = text[:n].replace("\n", " ").strip()
    return t + ("..." if len(text) > n else "")


def main():
    print("=== RAG Phase 1 Diagnosis ===\n")

    corp_embs = np.load(CORP_EMB_PATH).astype(np.float32)
    corp_ids = np.load(CORP_IDS_PATH)
    query_embs = np.load(QUERY_EMB_PATH).astype(np.float32)
    metadata = json.loads(QUERY_META_PATH.read_text(encoding="utf-8"))

    id_to_pos = {int(aid): i for i, aid in enumerate(corp_ids)}

    corp_norm = corp_embs / np.linalg.norm(corp_embs, axis=1, keepdims=True)
    query_norm = query_embs / np.linalg.norm(query_embs, axis=1, keepdims=True)
    sim_matrix = query_norm @ corp_norm.T  # (20, 42633)

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)

    records = []
    for qi, meta in enumerate(metadata):
        gt_id = meta["article_id"]
        query_text = meta["query"]
        scores = sim_matrix[qi]

        top100_idx = np.argpartition(scores, -TOP_K)[-TOP_K:]
        top100_idx = top100_idx[np.argsort(scores[top100_idx])[::-1]]
        top5_ids   = [int(corp_ids[i]) for i in top100_idx[:5]]
        top5_scores = [float(scores[i]) for i in top100_idx[:5]]

        gt_pos = id_to_pos.get(gt_id)
        if gt_pos is not None:
            gt_score = float(scores[gt_pos])
            rank_raw = int(np.sum(scores > gt_score)) + 1
            rank = rank_raw if rank_raw <= TOP_K else None
        else:
            gt_score = None
            rank = None

        top1_pos = id_to_pos.get(top5_ids[0]) if top5_ids else None
        if gt_pos is not None and top1_pos is not None and gt_pos != top1_pos:
            gt_to_top1_sim = float(corp_norm[gt_pos] @ corp_norm[top1_pos])
        elif gt_pos is not None and top1_pos is not None and gt_pos == top1_pos:
            gt_to_top1_sim = 1.0  # rank=1 success
        else:
            gt_to_top1_sim = None

        gt_body = fetch_text(conn, gt_id)
        top5_bodies = [fetch_text(conn, tid) for tid in top5_ids]

        lingo_in_query = get_lingo(query_text)
        lingo_in_top5 = [get_lingo(b) for b in top5_bodies]
        lingo_in_any_top5 = any(lingo_in_top5)

        records.append({
            "qi": qi + 1,
            "query": query_text,
            "gt_id": gt_id,
            "gt_body": gt_body,
            "gt_score": gt_score,
            "rank": rank,
            "top5_ids": top5_ids,
            "top5_scores": top5_scores,
            "top5_bodies": top5_bodies,
            "gt_to_top1_sim": gt_to_top1_sim,
            "lingo_in_query": lingo_in_query,
            "lingo_in_any_top5": lingo_in_any_top5,
        })

    conn.close()

    # ── Step 1: Rank Distribution ──────────────────────────────────────
    rank_1_3   = sum(1 for r in records if r["rank"] and r["rank"] <= 3)
    rank_4_10  = sum(1 for r in records if r["rank"] and 4 <= r["rank"] <= 10)
    rank_11_100 = sum(1 for r in records if r["rank"] and 11 <= r["rank"] <= 100)
    rank_gt100 = sum(1 for r in records if r["rank"] is None)

    print("=== Step 1: Rank 분포 ===")
    print(f"rank 1~3   : {rank_1_3}건")
    print(f"rank 4~10  : {rank_4_10}건")
    print(f"rank 11~100: {rank_11_100}건")
    print(f"rank >100  : {rank_gt100}건")
    print()
    for r in records:
        rank_str = str(r["rank"]) if r["rank"] else ">100"
        gts  = f"{r['gt_score']:.4f}" if r["gt_score"] is not None else "N/A"
        g2t  = f"{r['gt_to_top1_sim']:.4f}" if r["gt_to_top1_sim"] is not None else "N/A"
        lq   = r["lingo_in_query"] or "-"
        print(f"  Q{r['qi']:02d} | rank={rank_str:>4} | gt_sim={gts} | gt↔top1={g2t} | lingo_q={lq}")

    # ── Step 2: Hypothesis Classification ──────────────────────────────
    failures = [r for r in records if r["rank"] is None or r["rank"] > 10]

    for r in records:
        r["h1"] = r["h2"] = r["h3"] = False

    for r in failures:
        gt2t = r["gt_to_top1_sim"]

        # H3: query has lingo AND none of top-5 have that lingo
        r["h3"] = bool(r["lingo_in_query"]) and not r["lingo_in_any_top5"]

        # H2: GT and top-1 are very similar in corpus (same-topic competition)
        if gt2t is not None and gt2t > H2_SIM_HIGH:
            r["h2"] = True

        # H1: GT and top-1 are NOT similar → model retrieved wrong-direction docs
        #     only when not H3 (H3 has its own explanation)
        if not r["h3"] and gt2t is not None and gt2t < H1_SIM_LOW:
            r["h1"] = True

    h1_count = sum(1 for r in failures if r["h1"])
    h2_count = sum(1 for r in failures if r["h2"])
    h3_count = sum(1 for r in failures if r["h3"])
    multi = sum(1 for r in failures if (r["h1"] + r["h2"] + r["h3"]) > 1)
    unclassified = sum(1 for r in failures if not r["h1"] and not r["h2"] and not r["h3"])

    print("\n=== Step 2: 가설별 카운트 ===")
    print(f"실패 총계: {len(failures)}건 / 20건")
    print(f"가설 1 (쿼리 추상화 과잉): {h1_count}건")
    print(f"가설 2 (유사 글 과다)    : {h2_count}건")
    print(f"가설 3 (모델 한계)       : {h3_count}건")
    print(f"중복 분류: {multi}건  |  분류 불가: {unclassified}건")
    print()
    for r in failures:
        labels = []
        if r["h1"]: labels.append("H1")
        if r["h2"]: labels.append("H2")
        if r["h3"]: labels.append("H3")
        rank_str = str(r["rank"]) if r["rank"] else ">100"
        g2t = f"{r['gt_to_top1_sim']:.4f}" if r["gt_to_top1_sim"] is not None else "N/A"
        print(f"  Q{r['qi']:02d} rank={rank_str:>4} gt↔top1={g2t} → {', '.join(labels) or '분류불가'}")

    # ── Step 3: Case Selection ─────────────────────────────────────────
    successes = [r for r in records if r["rank"] and r["rank"] <= 10]
    success_case = min(successes, key=lambda r: r["rank"]) if successes else None

    hyp_ranking = sorted(
        [(h1_count, "h1", 1, "쿼리 추상화 과잉"),
         (h2_count, "h2", 2, "유사 글 과다"),
         (h3_count, "h3", 3, "모델 한계")],
        reverse=True
    )

    def pick_failure(hyp_key):
        candidates = [r for r in failures if r[hyp_key]]
        if not candidates:
            return None
        return max(candidates, key=lambda r: r["rank"] if r["rank"] else 200)

    fail_case1 = pick_failure(hyp_ranking[0][1])
    fail_case2 = pick_failure(hyp_ranking[1][1])

    print("\n=== Step 3: 선정 사례 ===")
    if success_case:
        print(f"성공 사례        : Q{success_case['qi']:02d}  id={success_case['gt_id']}  rank={success_case['rank']}")
    if fail_case1:
        r = fail_case1
        print(f"실패 사례 1 (H{hyp_ranking[0][2]}): Q{r['qi']:02d}  id={r['gt_id']}  rank={r['rank'] or '>100'}")
    if fail_case2:
        r = fail_case2
        print(f"실패 사례 2 (H{hyp_ranking[1][2]}): Q{r['qi']:02d}  id={r['gt_id']}  rank={r['rank'] or '>100'}")

    # ── Step 4: Generate Report ────────────────────────────────────────
    dominant_cnt, dominant_key, dominant_num, dominant_name = hyp_ranking[0]

    # Per-query table rows
    table_rows = []
    for r in records:
        rank_str = str(r["rank"]) if r["rank"] else ">100"
        labels = "".join(f"H{n}" for flag, n in [(r["h1"],1),(r["h2"],2),(r["h3"],3)] if flag) or "-"
        lingo_str = ", ".join(r["lingo_in_query"]) if r["lingo_in_query"] else "-"
        g2t_str = f"{r['gt_to_top1_sim']:.3f}" if r["gt_to_top1_sim"] is not None else "-"
        gts_str = f"{r['gt_score']:.4f}" if r["gt_score"] is not None else "-"
        table_rows.append(
            f"| {r['qi']:02d} | {r['query']} | {r['gt_id']} | {rank_str} "
            f"| {gts_str} | {g2t_str} | {lingo_str} | {labels} |"
        )

    def case_section(title: str, r, analysis: str) -> str:
        if r is None:
            return f"### {title}\n\n(해당 사례 없음)\n"
        rank_str = str(r["rank"]) if r["rank"] else ">100"
        top1_id = r["top5_ids"][0] if r["top5_ids"] else "N/A"
        top1_score = r["top5_scores"][0] if r["top5_scores"] else 0.0
        gt_score_str = f"{r['gt_score']:.4f}" if r["gt_score"] is not None else "N/A"
        g2t_str = f"{r['gt_to_top1_sim']:.4f}" if r["gt_to_top1_sim"] is not None else "N/A"
        return (
            f"### {title}\n\n"
            f"- **Query**: {r['query']}\n"
            f"- **Ground Truth** (id={r['gt_id']}, rank={rank_str}, "
            f"score={gt_score_str}, body_len={len(r['gt_body'])})\n\n"
            f"> {excerpt(r['gt_body'])}\n\n"
            f"- **Top-1** (id={top1_id}, score={top1_score:.4f}, GT↔Top1 sim={g2t_str})\n\n"
            f"> {excerpt(r['top5_bodies'][0] if r['top5_bodies'] else '')}\n\n"
            f"- **Analysis**: {analysis}\n"
        )

    def make_analysis(r, hyp_num: int) -> str:
        if r is None:
            return ""
        rank_str = str(r["rank"]) if r["rank"] else ">100"
        top1_id = r["top5_ids"][0] if r["top5_ids"] else "N/A"
        top1_score = r["top5_scores"][0] if r["top5_scores"] else 0.0
        g2t = r["gt_to_top1_sim"]
        g2t_str = f"{g2t:.4f}" if g2t is not None else "N/A"
        if hyp_num == 1:
            return (
                f"GT(id={r['gt_id']})와 Top-1(id={top1_id})의 문서 간 유사도={g2t_str}로 "
                f"H1_SIM_LOW({H1_SIM_LOW}) 미만. 모델이 쿼리 '{r['query']}'를 처리할 때 "
                f"GT와 의미적으로 다른 방향의 문서를 상위에 올린 패턴. "
                f"GT score={r['gt_score']:.4f} vs Top-1 score={top1_score:.4f}. "
                f"쿼리 추상화 수준이 GT 본문과의 의미 거리를 벌린 것으로 판단."
            )
        elif hyp_num == 2:
            return (
                f"GT(id={r['gt_id']})와 Top-1(id={top1_id})의 문서 간 유사도={g2t_str}로 "
                f"H2_SIM_HIGH({H2_SIM_HIGH}) 초과. 두 문서가 같은 주제를 다루는 유사 글임을 의미. "
                f"9년치 42,633건 코퍼스에서 동일 주제 글이 경쟁하여 GT가 rank {rank_str}로 밀린 전형적 H2 패턴."
            )
        else:
            lingo = r["lingo_in_query"]
            return (
                f"쿼리에 lingo 키워드 {lingo}가 포함됐으나 top-5 결과 문서 중 해당 lingo 없음. "
                f"voyage-3-large가 한국 주식 특수 표현의 의미를 임베딩 공간에서 제대로 분리하지 못한 패턴."
            )

    sc_analysis = ""
    if success_case:
        top1_id = success_case["top5_ids"][0] if success_case["top5_ids"] else "N/A"
        sc_analysis = (
            f"쿼리 '{success_case['query']}'가 GT(id={success_case['gt_id']})와 "
            f"높은 유사도(score={success_case['gt_score']:.4f})로 rank {success_case['rank']} 검색. "
            f"합성 쿼리가 본문의 핵심 의미를 충분히 담아 모델이 올바른 방향으로 검색."
        )

    verdict_reason = {
        1: (f"실패 {len(failures)}건 중 {h1_count}건에서 GT↔top1 문서 유사도가 {H1_SIM_LOW} 미만. "
            f"모델이 쿼리를 GT와 다른 방향으로 해석한 케이스가 가장 많음. "
            f"합성 쿼리의 추상화가 원본 본문 표현과 의미 거리를 만든 것으로 판단."),
        2: (f"실패 {len(failures)}건 중 {h2_count}건에서 GT↔top1 문서 유사도가 {H2_SIM_HIGH} 초과. "
            f"9년치 동일 주제 글이 코퍼스 내 중복·경쟁 구조를 형성하여 recall을 희석."),
        3: (f"실패 {len(failures)}건 중 {h3_count}건에서 쿼리 lingo가 top-5 결과에 미반영. "
            f"모델의 한국 주식 특수 표현 처리 한계가 주요 실패 원인."),
    }

    next_step = {
        1: "합성 쿼리 재생성: 본문 핵심 문장을 직접 발췌하거나 덜 추상화된 표현으로 쿼리 작성. 이후 동일 파이프라인으로 재평가.",
        2: "평가 방식 완화: top-10 내 GT와 의미적으로 유사한 글(GT↔result sim > 0.88) 1건이라도 있으면 통과로 재정의. 또는 코퍼스 dedup(클러스터링 대표 문서만) 후 재평가.",
        3: "다른 모델 비교: KURE-v1 또는 BGE-M3로 동일 쿼리 retrieval 재평가. lingo-aware fine-tuning 또는 lingo 동의어 확장(쿼리 rewriting) 검토.",
    }

    report = f"""# RAG Phase 1 Diagnosis

**Run Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Model**: voyage-3-large
**Corpus**: 42,633건
**Queries**: 20개 (합성 쿼리)

**분류 임계값**
- H2: GT↔Top1 코퍼스 유사도 > {H2_SIM_HIGH} (같은 주제 문서 경쟁)
- H1: GT↔Top1 코퍼스 유사도 < {H1_SIM_LOW} AND NOT H3 (다른 방향 검색)
- H3: 쿼리에 lingo 존재 AND top-5 본문에 해당 lingo 없음
- 분류 불가: {H1_SIM_LOW} ≤ GT↔Top1 유사도 ≤ {H2_SIM_HIGH} AND NOT H3

---

## Aggregate Distribution

- rank 1~3   : {rank_1_3}건
- rank 4~10  : {rank_4_10}건
- rank 11~100: {rank_11_100}건
- rank >100  : {rank_gt100}건
- **실패 (rank >10 or >100)**: {len(failures)}건 / 20건

## Per-Query Detail

| # | Query | GT ID | Rank | GT Score | GT↔Top1 Sim | Lingo in Q | Hyp |
|---|-------|-------|------|----------|-------------|------------|-----|
{chr(10).join(table_rows)}

## Hypothesis Evidence Scores

- **가설 1 (쿼리 추상화 과잉)**: {h1_count}건 / {len(failures)}건 실패
- **가설 2 (유사 글 과다)**    : {h2_count}건 / {len(failures)}건 실패
- **가설 3 (모델 한계)**       : {h3_count}건 / {len(failures)}건 실패
- 중복 분류: {multi}건 / 분류 불가: {unclassified}건

## Verdict

**가장 점수 높은 가설: 가설 {dominant_num} — {dominant_name}** ({dominant_cnt}건 / {len(failures)}건 실패)

근거: {verdict_reason[dominant_num]}

---

## Case Studies

{case_section('Success Case', success_case, sc_analysis)}
{case_section(f'Failure Case 1 (가설 {hyp_ranking[0][2]} — {hyp_ranking[0][3]} 증거)', fail_case1, make_analysis(fail_case1, hyp_ranking[0][2]))}
{case_section(f'Failure Case 2 (가설 {hyp_ranking[1][2]} — {hyp_ranking[1][3]} 증거)', fail_case2, make_analysis(fail_case2, hyp_ranking[1][2]))}

---

## Recommended Next Step

- **가설 1 →** 쿼리 재생성 (덜 추상화된 버전, 본문 핵심 문장 직접 발췌)
- **가설 2 →** 평가 방식 변경 (top-10 내 의미 유사 글 1건 이상이면 통과) 또는 코퍼스 dedup
- **가설 3 →** 다른 모델 비교 (KURE-v1, BGE-M3); lingo 쿼리 rewriting 검토

**가장 높은 가설(가설 {dominant_num})에 따른 권장 다음 단계**: {next_step[dominant_num]}
"""

    OUT_REPORT.write_text(report, encoding="utf-8")
    file_size = OUT_REPORT.stat().st_size
    word_count = len(report.split())
    print(f"\n=== Step 4: 보고서 생성 ===")
    print(f"파일: {OUT_REPORT}")
    print(f"크기: {file_size:,} bytes  |  단어 수: {word_count:,}")
    print(f"\n최종 판정: 가설 {dominant_num} ({dominant_name}) - {dominant_cnt}건 / {len(failures)}건 실패")


if __name__ == "__main__":
    main()
