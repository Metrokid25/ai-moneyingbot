"""Build the RAG -> Trading Bot research-only contract for A-grade rules.

The output is a JSONL handoff artifact.  It contains mentor-grounded evidence
and a preregistered experiment shape, but no Trading Bot state, market data,
orders, signals, or claim of profitability.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES = (
    PROJECT_ROOT / "output" / "pdf" / "굿머닝_매매원칙_검증판_v2_rules.jsonl"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "artifacts"
    / "trading_research"
    / "a_grade_rules_research_contract_v1.jsonl"
)
SOURCE_RULEBOOK_COMMIT = "edfee4754b3a40fe53e494b43ed2f9a4e6d7aea9"
TARGET_RULE_IDS = ("GM-R01", "GM-R03", "GM-R06", "GM-R07")

BOUNDARY = {
    "producer": "RAG Bot",
    "consumer": "Trading Bot researcher",
    "cross_key": "article_id",
    "transport": "JSONL",
    "archive_access": "RAG source evidence only; Archive DB remains read-only",
    "trading_access": "RAG Bot must not read or write Trading Bot-owned data",
    "automatic_application": False,
    "live_trading_authorized": False,
}

COMMON_PROTOCOL = {
    "purpose": "falsify or retain a research hypothesis; not optimize a live strategy",
    "required_sequence": [
        "freeze data snapshot and code commit",
        "freeze baseline, parameter grid, metrics, and tolerances before execution",
        "run chronological walk-forward evaluation",
        "select at most one candidate without viewing the sealed holdout",
        "run the selected candidate once on the sealed holdout",
        "repeat with base-cost and stress-cost assumptions",
        "return the result through the declared JSONL result schema",
    ],
    "data_integrity_gates": [
        "point-in-time inputs only",
        "corporate actions and delistings handled without survivor bias",
        "signal timestamp precedes the executable price timestamp",
        "identical universe, entry signals, and evaluation windows for paired comparisons",
        "missing required granularity produces not_evaluable, never a silent fallback",
    ],
    "evaluation": {
        "split": "chronological expanding or rolling walk-forward plus a sealed final holdout",
        "minimum_walk_forward_folds": 5,
        "sample_policy": (
            "preregister a rule-specific minimum effective-event count; if it is not met, "
            "return insufficient_sample and do not issue pass"
        ),
        "cost_scenarios": [
            "base: Trading Bot's versioned fee, tax, spread, and slippage assumptions",
            "stress: preregistered worse spread and slippage assumptions",
        ],
        "mandatory_metrics": [
            "CAGR",
            "MDD",
            "Sharpe",
            "turnover",
            "win_rate",
            "profit_factor",
            "average_holding_period",
            "trade_or_effective_event_count",
            "tail_loss_95pct",
        ],
        "decision_policy": [
            "any leakage or integrity-gate failure => invalid_experiment",
            "unavailable required data or too few events => not_evaluable or insufficient_sample",
            "advance only when the preregistered primary objective passes on the sealed holdout",
            "advance only when preregistered guardrails pass under base and stress costs",
            "a retained hypothesis remains research-only until separate owner approval",
        ],
    },
}

RESULT_SCHEMA = {
    "schema_name": "trading_rule_research_result",
    "schema_version": 1,
    "required_fields": [
        "contract_id",
        "rule_id",
        "experiment_id",
        "trading_bot_git_commit",
        "data_snapshot_id",
        "data_period",
        "data_granularity",
        "universe_definition",
        "baseline_id",
        "candidate_id",
        "parameters",
        "cost_assumptions",
        "walk_forward_folds",
        "sealed_holdout_metrics",
        "effective_event_count",
        "integrity_gate_results",
        "decision",
        "decision_reason",
        "reproduction_command",
    ],
    "decision_enum": [
        "retain_for_further_research",
        "reject",
        "insufficient_sample",
        "not_evaluable",
        "invalid_experiment",
    ],
    "forbidden_fields": [
        "live_order",
        "broker_order_id",
        "production_signal",
        "auto_apply",
    ],
}


EXPERIMENTS: dict[str, dict[str, Any]] = {
    "GM-R01": {
        "research_question": (
            "Does a point-in-time risk-off exposure cap reduce drawdown or tail loss without an "
            "unacceptable loss of return versus the identical strategy without the overlay?"
        ),
        "unit_of_analysis": "market session and portfolio exposure transition",
        "required_inputs": [
            "daily index OHLCV",
            "point-in-time market breadth",
            "portfolio exposure reconstructed by Trading Bot",
        ],
        "baseline": "same strategy and entries with no GM-R01 exposure overlay",
        "candidate_grid": {
            "volatility_trigger": ["rolling percentile 75", "rolling percentile 85", "rolling percentile 90"],
            "decliner_ratio_trigger": [0.60, 0.70, 0.80],
            "risk_off_exposure_cap": [0.20, 0.40, 0.60],
            "release_confirmation_sessions": [2, 3, 5],
        },
        "primary_objective": "MDD and tail_loss_95pct reduction versus paired baseline",
        "guardrails": ["CAGR degradation tolerance preregistered", "turnover and cost increase preregistered"],
        "special_checks": [
            "rolling percentiles use only information available before each decision",
            "compare fixed 20% cap with staged caps; do not treat 20% as a universal constant",
        ],
    },
    "GM-R03": {
        "research_question": (
            "Does preregistered staged entry improve drawdown or execution quality versus one-shot "
            "entry when the entry signal and total target exposure are held constant?"
        ),
        "unit_of_analysis": "eligible entry setup and completed position campaign",
        "required_inputs": ["OHLCV at strategy granularity", "entry setup state", "fills", "position cost basis"],
        "baseline": "one-shot entry at the first executable price with identical target exposure",
        "candidate_grid": {
            "entry_slice_count": [2, 3],
            "scout_fraction_of_target": [0.10, 0.20],
            "minimum_add_interval_bars": [1, 2, 3],
            "add_permission": ["setup_still_valid", "setup_valid_and_confirmation_signal"],
        },
        "primary_objective": "MDD or adverse excursion reduction versus paired one-shot baseline",
        "guardrails": ["missed-upside tolerance preregistered", "turnover and total target exposure unchanged"],
        "special_checks": [
            "no add after setup invalidation",
            "same-day repeated fills cannot silently exhaust target exposure",
            "report unfilled and partially filled campaigns",
        ],
    },
    "GM-R06": {
        "research_question": (
            "For entries objectively tagged as chase entries, does a shorter holding limit and tighter "
            "risk budget improve risk-adjusted outcomes versus converting them into ordinary holdings?"
        ),
        "unit_of_analysis": "chase-tagged entry and its exit campaign",
        "required_inputs": ["intraday OHLCV", "gap", "entry timestamp", "fills", "entry-reason tag"],
        "baseline": "same chase-tagged entries managed by the ordinary holding policy",
        "candidate_grid": {
            "gap_trigger_pct": [2.0, 3.0, 5.0],
            "distance_from_reference_atr": [1.0, 1.5, 2.0],
            "maximum_holding_bars": [6, 12, 24],
            "loss_budget_multiplier_vs_ordinary": [0.50, 0.75],
        },
        "primary_objective": "tail loss and overnight gap-risk reduction for chase-tagged entries",
        "guardrails": ["net expectancy tolerance preregistered", "classification coverage and ambiguity reported"],
        "special_checks": [
            "missing intraday data => not_evaluable",
            "the tag must be assigned at entry time, never retrospectively",
            "a later trend thesis must be recorded as a new independent setup, not relabeling",
        ],
    },
    "GM-R07": {
        "research_question": (
            "Do stop policies conditioned on an objective strategy-family tag outperform a single "
            "universal stop while controlling turnover, gap-through loss, and tail risk?"
        ),
        "unit_of_analysis": "entry tagged at decision time and its stop/exit outcome",
        "required_inputs": ["OHLCV", "fills", "entry-time strategy-family tag", "point-in-time ATR"],
        "baseline": "same entries under one preregistered universal stop policy",
        "candidate_grid": {
            "strategy_family": ["MOMENTUM", "FUNDAMENTAL"],
            "fixed_stop_pct": [3.0, 4.0, 5.0, 10.0],
            "atr_stop_multiple": [1.0, 1.5, 2.0, 2.5],
            "gap_through_policy": ["next_executable_price"],
        },
        "primary_objective": "MDD and tail-loss reduction without worse net expectancy than the universal-stop baseline",
        "guardrails": ["stop frequency and turnover tolerance preregistered", "each tag evaluated separately"],
        "special_checks": [
            "unknown or post-hoc strategy tag => not_evaluable",
            "stops execute at the next feasible price; no fill at an unavailable stop price",
            "3-5% and 10% are separate hypotheses, not one merged mentor constant",
        ],
    },
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_no}: expected a JSON object")
            rows.append(row)
    return rows


def build_contracts(rules_path: Path) -> list[dict[str, Any]]:
    rules = {str(row.get("rule_id")): row for row in read_jsonl(rules_path)}
    missing = [rule_id for rule_id in TARGET_RULE_IDS if rule_id not in rules]
    if missing:
        raise ValueError(f"missing target rule(s): {', '.join(missing)}")

    contracts: list[dict[str, Any]] = []
    for rule_id in TARGET_RULE_IDS:
        rule = rules[rule_id]
        if rule.get("automation_grade") != "A":
            raise ValueError(f"{rule_id}: expected automation_grade A")
        if rule.get("status") != "research_hypothesis_unvalidated":
            raise ValueError(f"{rule_id}: expected unvalidated research status")

        experiment = EXPERIMENTS[rule_id]
        contracts.append(
            {
                "schema_name": "rag_trading_research_contract",
                "schema_version": 1,
                "contract_id": f"TRC-{rule_id}-v1",
                "rule_id": rule_id,
                "rule_name": rule["name"],
                "contract_status": "research_only_needs_trading_bot_validation",
                "source_rulebook": {
                    "version": "굿머닝_매매원칙_검증판_v2",
                    "git_commit": SOURCE_RULEBOOK_COMMIT,
                    "rule_status": rule["status"],
                    "automation_grade": rule["automation_grade"],
                    "evidence_grade": rule["evidence_grade"],
                },
                "mentor_claim": rule["mentor_claim"],
                "operational_hypothesis": rule["operational_hypothesis"],
                "known_exceptions": rule["exceptions"],
                "evidence": rule["sources"],
                "ownership_boundary": BOUNDARY,
                "experiment": experiment,
                "common_protocol": COMMON_PROTOCOL,
                "result_return_contract": RESULT_SCHEMA,
            }
        )
    return contracts


def validate_contracts(rows: list[dict[str, Any]]) -> dict[str, int]:
    if [row.get("rule_id") for row in rows] != list(TARGET_RULE_IDS):
        raise ValueError("contract order or target rule set is invalid")

    article_ids: set[int] = set()
    for row in rows:
        boundary = row["ownership_boundary"]
        if boundary["automatic_application"] or boundary["live_trading_authorized"]:
            raise ValueError(f"{row['rule_id']}: automatic or live application must be false")
        if row["contract_status"] != "research_only_needs_trading_bot_validation":
            raise ValueError(f"{row['rule_id']}: invalid contract status")
        evidence = row.get("evidence") or []
        if not evidence:
            raise ValueError(f"{row['rule_id']}: evidence is empty")
        for source in evidence:
            article_id = source.get("article_id")
            quote = str(source.get("quote") or "").strip()
            if not isinstance(article_id, int) or article_id <= 0 or not quote:
                raise ValueError(f"{row['rule_id']}: invalid evidence record")
            article_ids.add(article_id)
    return {"contract_count": len(rows), "unique_article_count": len(article_ids)}


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
    rows = build_contracts(args.rules.resolve())
    summary = validate_contracts(rows)
    if not args.check_only:
        write_jsonl(args.out.resolve(), rows)
    print("validation=passed")
    print(f"contract_count={summary['contract_count']}")
    print(f"unique_article_count={summary['unique_article_count']}")
    print(f"output={'(check-only)' if args.check_only else args.out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
