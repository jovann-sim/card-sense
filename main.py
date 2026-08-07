from __future__ import annotations

import argparse
import json
from pathlib import Path

from finance_agents import FinanceOrchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the finance agent orchestrator.")
    parser.add_argument(
        "request",
        nargs="?",
        default="Recommend a budget.",
        help="User request to route through the agent graph.",
    )
    parser.add_argument(
        "--statement-dir",
        default="statements",
        help="Directory to scan for bank statement CSV files.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the workflow result as JSON.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    orchestrator = FinanceOrchestrator()
    result = orchestrator.run(args.request, statement_dir=Path(args.statement_dir))

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(result.render())


if __name__ == "__main__":
    main()