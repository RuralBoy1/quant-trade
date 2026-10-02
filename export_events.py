"""运行策略并把逐事件日志导出成 CSV / Excel，供人工检查或与 Pine 日志对比。

    python export_events.py --strategy turtle
    python export_events.py --strategy turtle --verbose   # 顺便把日志打到控制台
"""

from __future__ import annotations

import argparse
from pathlib import Path

import strategies
from backtest.engine import add_common_args, run_backtest
from backtest.reporting import write_events


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导出策略事件日志")
    parser.add_argument("--strategy", default="turtle", choices=sorted(strategies.REGISTRY))
    parser.add_argument("--outdir", default="datas/logs")
    parser.add_argument("--verbose", action="store_true", help="同时把日志打到控制台")
    add_common_args(parser)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    spec = strategies.get(args.strategy)

    run = run_backtest(
        spec.strategy,
        spec.sizer,
        data_path=args.data or spec.data,
        cash=args.cash,
        commission=args.commission,
        slippage=args.slippage,
        strategy_kwargs={"verbose": args.verbose},
    )

    events = run.strategy.events.to_dataframe()
    csv_path, xlsx_path = write_events(events, Path(args.outdir), f"{spec.name}_events")

    print(f"events={len(events)}")
    print(f"final_equity={run.cerebro.broker.getvalue():.8f}")
    if events.empty:
        print("（该策略没有产生任何事件）")
    else:
        print(events["event"].value_counts().to_string())
    print(f"csv={csv_path.resolve()}")
    print(f"xlsx={xlsx_path.resolve()}")


if __name__ == "__main__":
    main()
