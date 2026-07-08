"""Terminal chat client for quick agent testing.

Usage:  python -m app.agent.cli
Type a message; the agent responds and prints the tools it called. 'exit' quits.
"""
from __future__ import annotations

import uuid

from app.agent.graph import run_agent
from app.db.database import SessionLocal, init_db


def main() -> None:
    init_db()
    session_id = f"cli-{uuid.uuid4().hex[:8]}"
    print("Northwind Support AI — terminal chat. Type 'exit' to quit.\n")
    db = SessionLocal()
    try:
        while True:
            try:
                msg = input("you › ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not msg or msg.lower() in ("exit", "quit"):
                break
            result = run_agent(db, session_id, msg)
            for tc in result["tool_calls_made"]:
                out = tc["output"]
                brief = out.get("status") or out.get("error") or ("ok" if out else "")
                print(f"   ↳ tool {tc['tool']}({_brief_input(tc['input'])}) → {brief}")
            print(f"\nagent › {result['reply']}")
            print(f"        [{result['outcome']} · ${result['cost_usd']:.4f} · {result['duration_ms']}ms]\n")
    finally:
        db.close()


def _brief_input(inp: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in list(inp.items())[:2])


if __name__ == "__main__":
    main()
