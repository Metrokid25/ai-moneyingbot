"""Build the 24-question RAG gold set for rulebook v2.

Every question is tied to one or more article_id/chunk_id pairs already present
in the production manifest.  The set tests retrieval, not trading performance.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES = PROJECT_ROOT / "output" / "pdf" / "굿머닝_매매원칙_검증판_v2_rules.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "tests" / "fixtures" / "rag_rulebook_gold_v2.jsonl"
RULEBOOK_COMMIT = "edfee4754b3a40fe53e494b43ed2f9a4e6d7aea9"
MANIFEST_SNAPSHOT = "miniPC RAG manifest observed 2026-08-03 KST"


QUESTION_SPECS: list[dict[str, Any]] = [
    {"rule_id":"GM-R01","kind":"core","question":"시장 원인을 예측하기 어려운 변동성 장세에서 선생님이 가장 먼저 하라고 한 위험 대응은 무엇인가?","chunks":["173480:0"],"roles":["primary_new"],"keywords":["비중관리","리스크","회피"]},
    {"rule_id":"GM-R01","kind":"caveat","question":"변동성 장세에서 장 마감 보유비중 20% 발언과, 변동성이 커져도 수익 기회가 사라지는 것은 아니라는 예외를 함께 설명해줘.","chunks":["7938:0","18157:0"],"roles":["primary","caveat"],"keywords":["20%","변동성","투자수익"]},
    {"rule_id":"GM-R02","kind":"core","question":"개별 종목보다 종합주가지수와 시장 레짐을 먼저 보아야 한다고 한 이유는 무엇인가?","chunks":["53601:0","7938:0"],"roles":["primary","support"],"keywords":["종합주가지수","개별종목","변동성"]},
    {"rule_id":"GM-R02","kind":"caveat","question":"지수가 박스권일 때 동시호가나 시초가를 따라잡기보다 어떤 진입을 기다리라고 했는가?","chunks":["129709:0"],"roles":["primary"],"keywords":["박스권","동시호가","눌림"]},
    {"rule_id":"GM-R03","kind":"core","question":"선생님이 말한 계획된 분할매수의 최소 횟수와 선발대 비중은 어느 정도인가?","chunks":["24948:0","53601:0"],"roles":["primary"],"keywords":["최소 2번","선발대","20% 미만"]},
    {"rule_id":"GM-R03","kind":"caveat","question":"가격이 오르내릴 때마다 당일 포트를 전부 채우는 행동이 왜 분할매수가 아닌가?","chunks":["53601:0"],"roles":["prohibition"],"keywords":["당일","포트","분할매수"]},
    {"rule_id":"GM-R04","kind":"core","question":"떨어지는 주식을 바로 사지 않고 진바닥과 상승 반전을 확인한 뒤 무릎에서 사라는 가르침은 무엇인가?","chunks":["29102:0","33780:0"],"roles":["primary","support"],"keywords":["진바닥","상승","무릎"]},
    {"rule_id":"GM-R04","kind":"caveat","question":"보수적인 투자자가 바닥 반전을 확인할 때 전고점 돌파를 어떤 방식으로 사용할 수 있는가?","chunks":["64804:0"],"roles":["caveat"],"keywords":["보수적","전고점","종가기준","돌파"]},
    {"rule_id":"GM-R05","kind":"core","question":"급등 뒤 눌림에서 작은 음봉 한두 개와 저점 확인을 어떻게 분할매수 자리로 해석했는가?","chunks":["78948:0","89519:0"],"roles":["primary"],"keywords":["급등","눌림","작은 음봉","분할매수"]},
    {"rule_id":"GM-R05","kind":"caveat","question":"강세 출발 종목을 바로 따라잡지 말고 오후장에 무엇을 기다리라고 했는가?","chunks":["80367:0"],"roles":["support"],"keywords":["따라잡기","오후장","눌림"]},
    {"rule_id":"GM-R06","kind":"core","question":"상승 종목을 뒤늦게 따라잡았다면 보유가 아니라 어떤 개념으로 대응하라고 했는가?","chunks":["118470:0"],"roles":["primary"],"keywords":["상승종목","보유","트레이딩"]},
    {"rule_id":"GM-R06","kind":"caveat","question":"급등 추격을 피해야 한다는 금지와 장중 눌림을 기다리라는 대안을 함께 찾아줘.","chunks":["33780:0","129709:0"],"roles":["prohibition","context"],"keywords":["급등","따라잡기","장중 눌림"]},
    {"rule_id":"GM-R07","kind":"core","question":"수급이 좋아 단기 차익을 노리는 매매에서 손절선을 짧게 잡아야 한다고 한 이유는 무엇인가?","chunks":["91752:0"],"roles":["primary"],"keywords":["수급","차익","손절선","짧게"]},
    {"rule_id":"GM-R07","kind":"caveat","question":"초보자 손절폭에 관해 5%를 넘지 말라는 글과 3~4%가 좋다는 글을 함께 찾아 비교해줘.","chunks":["43209:0","89531:0"],"roles":["support","range_conflict"],"keywords":["초보자","5%","3~4%","손절"]},
    {"rule_id":"GM-R08","kind":"core","question":"장대양봉 다음 날 전일 상승분의 허리가 꺾이면 어떻게 대응하라고 했는가?","chunks":["40599:0"],"roles":["primary"],"keywords":["장대양봉","허리","매도"]},
    {"rule_id":"GM-R08","kind":"caveat","question":"장대양봉의 허리를 상승분 30% 지점으로 설명한 내용과 익일 10% 넘게 하락할 때의 대응은 무엇인가?","chunks":["40599:0"],"roles":["definition","threshold"],"keywords":["30%","-10%","전량 매도"]},
    {"rule_id":"GM-R09","kind":"core","question":"수익이 어느 정도 났을 때 물량 약 30%를 먼저 매도하라는 분할 익절 방법은 무엇인가?","chunks":["26566:0"],"roles":["primary"],"keywords":["수익","30%","먼저 매도"]},
    {"rule_id":"GM-R09","kind":"caveat","question":"일부 수익실현 뒤 바닥이나 다음 날 음봉을 확인하면 매도한 물량을 어떻게 다시 채울 수 있는가?","chunks":["26566:0","53122:0"],"roles":["reentry","range_context"],"keywords":["수익실현","바닥","음봉","다시"]},
    {"rule_id":"GM-R10","kind":"core","question":"상승 추세 종목에서 고점을 확인하고 추세가 꺾였을 때 어깨에서 판다는 뜻은 무엇인가?","chunks":["43209:0","33823:0"],"roles":["primary","example"],"keywords":["고점","추세","어깨","수익실현"]},
    {"rule_id":"GM-R10","kind":"caveat","question":"고점 뒤 움직임이 숨고르기인지 가격조정인지 구분하기 어려운 이유를 선생님은 어떻게 설명했는가?","chunks":["32314:0"],"roles":["caveat"],"keywords":["숨고르기","가격조정","실전경험"]},
    {"rule_id":"GM-R11","kind":"core","question":"상한가 다음 날 거래량이 전날의 1.3배를 넘으면 어느 정도 수익실현하라고 했는가?","chunks":["27421:0"],"roles":["primary"],"keywords":["상한가","거래량","1.3배","반"]},
    {"rule_id":"GM-R11","kind":"caveat","question":"모든 거래량 증가를 같은 신호로 보면 안 되는 이유와 급등 뒤 거래량 증가 때의 대응을 함께 찾아줘.","chunks":["38039:0","13584:0"],"roles":["caveat","support"],"keywords":["거래량 증가","동일","폭등","수익실현"]},
    {"rule_id":"GM-R12","kind":"core","question":"10호가창에서 매도물량보다 매수물량이 많아졌을 때 선생님은 가격 방향을 어떻게 해석했는가?","chunks":["26566:0"],"roles":["primary"],"keywords":["10호가","매도물량","매수물량","하락"]},
    {"rule_id":"GM-R12","kind":"caveat","question":"10호가 수급 타이밍 방법은 어떤 파동 장세에서 유효하고, 종합주가지수가 흘러내릴 때는 왜 쓰면 안 되는가?","chunks":["26566:0"],"roles":["context","prohibition"],"keywords":["파동","종합주가지수","흘러내리고"]},
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def build_gold(rules_path: Path) -> list[dict[str, Any]]:
    rules = {row["rule_id"]: row for row in read_jsonl(rules_path)}
    rows: list[dict[str, Any]] = []
    counters: Counter[str] = Counter()
    for spec in QUESTION_SPECS:
        rule_id = spec["rule_id"]
        counters[rule_id] += 1
        rule = rules[rule_id]
        chunks = list(spec["chunks"])
        article_ids = sorted({int(chunk_id.split(":", 1)[0]) for chunk_id in chunks})
        source_ids = {int(source["article_id"]) for source in rule["sources"]}
        if not set(article_ids) <= source_ids:
            raise ValueError(f"{rule_id}: gold source is not in the rulebook evidence")
        rows.append(
            {
                "id": f"rulebook-v2-{rule_id.lower()}-{counters[rule_id]:02d}",
                "rule_id": rule_id,
                "rule_name": rule["name"],
                "question_kind": spec["kind"],
                "question": spec["question"],
                "category": "trading_rulebook",
                "expected_topics": [rule["name"]],
                "expected_keywords": spec["keywords"],
                "expected_article_ids": article_ids,
                "expected_chunk_ids": chunks,
                "expected_evidence_roles": spec["roles"],
                "expected_date_range": {"start": None, "end": None},
                "source_rulebook_commit": RULEBOOK_COMMIT,
                "manifest_snapshot": MANIFEST_SNAPSHOT,
                "notes": "Rulebook v2 evidence-grounded retrieval question; not a trading-performance label.",
            }
        )
    return rows


def validate_gold(rows: list[dict[str, Any]]) -> dict[str, int]:
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate gold question id")
    counts = Counter(row["rule_id"] for row in rows)
    expected = {f"GM-R{i:02d}": 2 for i in range(1, 13)}
    if dict(counts) != expected:
        raise ValueError(f"expected two questions per rule, got {dict(counts)}")
    for row in rows:
        if not row["question"].strip() or not row["expected_chunk_ids"]:
            raise ValueError(f"{row['id']}: empty question or expected chunks")
        derived = sorted({int(chunk_id.split(":", 1)[0]) for chunk_id in row["expected_chunk_ids"]})
        if derived != row["expected_article_ids"]:
            raise ValueError(f"{row['id']}: article/chunk mismatch")
    return {
        "question_count": len(rows),
        "rule_count": len(counts),
        "unique_article_count": len({aid for row in rows for aid in row["expected_article_ids"]}),
        "unique_chunk_count": len({cid for row in rows for cid in row["expected_chunk_ids"]}),
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = build_gold(args.rules.resolve())
    summary = validate_gold(rows)
    if not args.check_only:
        write_jsonl(args.out.resolve(), rows)
    print("validation=passed")
    for key, value in summary.items():
        print(f"{key}={value}")
    print(f"output={'(check-only)' if args.check_only else args.out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
