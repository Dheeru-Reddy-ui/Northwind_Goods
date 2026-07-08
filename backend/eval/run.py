"""Regression runner.

    python -m eval.run                 # production vs naive scorecard, stored
    python -m eval.run --mode production
    python -m eval.run --baseline      # diff against the previous stored run
    python -m eval.run --limit 10      # quick smoke run

Runs the golden set through the agent (re-seeding the store before each ticket),
scores every resolution with the judge, computes RAGAS-style metrics on policy
answers, aggregates by category, prints a scorecard, and writes the run to the
eval_runs table so runs are comparable over time.
"""
from __future__ import annotations

import argparse
import statistics
from collections import defaultdict
from pathlib import Path

import yaml
from sqlalchemy import select

from app.db.database import SessionLocal, init_db
from app.db.models import Conversation, EvalRun
from app.store.seed import seed
from app.agent.graph import run_agent, reset_session
from eval.baseline import run_naive
from eval.judge import DIMENSIONS, judge_ticket
from eval.rag_eval import rag_metrics

TICKETS_PATH = Path(__file__).with_name("golden_tickets.yaml")


def load_tickets() -> list[dict]:
    return yaml.safe_load(TICKETS_PATH.read_text(encoding="utf-8"))


def _run_ticket(db, ticket: dict, mode: str) -> dict:
    seed(db)  # fresh store state so refund/cancel tickets are deterministic
    sid = f"eval-{mode}-{ticket['id']}"
    reset_session(sid)
    result = {"reply": "", "outcome": "open", "tool_calls_made": []}
    for msg in ticket["messages"]:
        if mode == "production":
            result = run_agent(db, sid, msg, source="simulation")
        else:
            result = run_naive(db, sid, msg)
    return result


def evaluate(mode_list: list[str], limit: int | None) -> dict:
    tickets = load_tickets()
    if limit:
        tickets = tickets[:limit]
    init_db()
    db = SessionLocal()

    # per mode -> per category -> list of dimension dicts
    agg: dict[str, dict[str, list[dict]]] = {m: defaultdict(list) for m in mode_list}
    rag_rows: list[dict] = []

    for ticket in tickets:
        for mode in mode_list:
            result = _run_ticket(db, ticket, mode)
            scores = judge_ticket(ticket, result)
            agg[mode][ticket["category"]].append(scores)

            if mode == "production" and result.get("conversation_id"):
                conv = db.get(Conversation, result["conversation_id"])
                if conv:
                    conv.judge_score = round(scores["overall"] * 5, 2)
                    conv.judge_detail = scores
                    db.commit()

            if mode == "production" and ticket["category"] in ("policy_qa",):
                rm = rag_metrics(ticket["messages"][-1], result,
                                 ticket.get("expect", {}).get("expected_source"))
                rag_rows.append(rm)

    scorecards = {m: _scorecard(agg[m]) for m in mode_list}
    rag_summary = _mean_dicts(rag_rows) if rag_rows else {}

    # persist the production run
    if "production" in scorecards:
        run = EvalRun(mode="production", total=len(tickets),
                      metrics={"by_category": scorecards["production"]["by_category"],
                               "overall": scorecards["production"]["overall"],
                               "ragas": rag_summary})
        db.add(run)
        db.commit()

    db.close()
    return {"scorecards": scorecards, "ragas": rag_summary, "n": len(tickets)}


def _scorecard(cat_map: dict[str, list[dict]]) -> dict:
    by_category = {}
    all_scores: list[dict] = []
    for cat, rows in cat_map.items():
        by_category[cat] = {"n": len(rows), **_mean_dims(rows)}
        all_scores += rows
    return {"by_category": by_category, "overall": {"n": len(all_scores), **_mean_dims(all_scores)}}


def _mean_dims(rows: list[dict]) -> dict:
    return {d: round(statistics.mean(r[d] for r in rows), 3) for d in (*DIMENSIONS, "overall")}


def _mean_dicts(rows: list[dict]) -> dict:
    keys = rows[0].keys()
    return {k: round(statistics.mean(r[k] for r in rows), 3) for k in keys}


# --------------------------------------------------------------------------
# Printing
# --------------------------------------------------------------------------
def print_report(res: dict, mode_list: list[str]) -> None:
    prod = res["scorecards"].get("production")
    print(f"\n{'=' * 74}\n  NORTHWIND SUPPORT AI — EVALUATION SCORECARD  ({res['n']} tickets)\n{'=' * 74}")
    if prod:
        print("\n  Production agent — by category")
        print(f"  {'category':<20}{'n':>3}  {'resolve':>8}{'policy':>8}{'ground':>8}{'tone':>7}{'overall':>9}")
        print(f"  {'-' * 70}")
        for cat, m in sorted(prod["by_category"].items()):
            print(f"  {cat:<20}{m['n']:>3}  {m['resolution_success']:>8.2f}{m['policy_adherence']:>8.2f}"
                  f"{m['groundedness']:>8.2f}{m['tone']:>7.2f}{m['overall']:>9.2f}")
        o = prod["overall"]
        print(f"  {'-' * 70}")
        print(f"  {'OVERALL':<20}{o['n']:>3}  {o['resolution_success']:>8.2f}{o['policy_adherence']:>8.2f}"
              f"{o['groundedness']:>8.2f}{o['tone']:>7.2f}{o['overall']:>9.2f}")

    if res["ragas"]:
        r = res["ragas"]
        print(f"\n  RAGAS (policy answers): faithfulness={r['faithfulness']:.2f}  "
              f"answer_relevance={r['answer_relevance']:.2f}  context_precision={r['context_precision']:.2f}")

    if "naive" in res["scorecards"]:
        naive = res["scorecards"]["naive"]["overall"]
        p = prod["overall"]
        print(f"\n  Production vs naive baseline (overall)")
        print(f"  {'metric':<22}{'production':>12}{'naive':>10}{'delta':>9}")
        print(f"  {'-' * 52}")
        for d in ("resolution_success", "policy_adherence", "groundedness", "overall"):
            print(f"  {d:<22}{p[d]:>12.2f}{naive[d]:>10.2f}{p[d] - naive[d]:>+9.2f}")
    print(f"\n{'=' * 74}\n")


def diff_baseline() -> None:
    db = SessionLocal()
    runs = db.scalars(select(EvalRun).where(EvalRun.mode == "production")
                      .order_by(EvalRun.created_at.desc()).limit(2)).all()
    db.close()
    if len(runs) < 2:
        print("Need at least two stored runs to diff.")
        return
    cur, prev = runs[0].metrics["overall"], runs[1].metrics["overall"]
    print("\n  Regression diff vs previous run (overall)")
    print(f"  {'metric':<22}{'current':>10}{'previous':>10}{'delta':>9}")
    for d in (*DIMENSIONS, "overall"):
        print(f"  {d:<22}{cur[d]:>10.2f}{prev[d]:>10.2f}{cur[d] - prev[d]:>+9.2f}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["production", "naive", "both"], default="both")
    ap.add_argument("--baseline", action="store_true", help="diff against previous stored run")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    mode_list = ["production", "naive"] if args.mode == "both" else [args.mode]
    res = evaluate(mode_list, args.limit)
    print_report(res, mode_list)
    if args.baseline:
        diff_baseline()


if __name__ == "__main__":
    main()
