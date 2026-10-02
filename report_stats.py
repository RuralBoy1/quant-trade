"""跑回测并输出风险收益统计，与买入持有做对照。

回答的是「这个策略值不值得跑」，而不是「实现有没有写对」。
后者用 export_events.py 导出的事件日志。

    python report_stats.py --strategy turtle
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

import strategies
from backtest.engine import add_common_args, run_backtest
from backtest.metrics import summarize
from backtest.reporting import write_stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="策略风险收益统计")
    parser.add_argument("--strategy", default="turtle", choices=sorted(strategies.REGISTRY))
    parser.add_argument("--outdir", default="datas/logs")
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
        with_equity_curve=True,
    )
    if run.equity is None:
        raise SystemExit("没有取到权益曲线")

    curve = run.equity
    equity = curve["权益"]

    # 买入持有：期初同样扣一次手续费买入，之后不动，保证和策略可比
    close = run.data["close"].reindex(curve.index)
    buyhold = args.cash * (1 - args.commission) * close / close.iloc[0]

    rows = {
        "策略": summarize(equity),
        "买入持有": summarize(buyhold),
    }
    rows["策略"]["持仓时间占比"] = f"{float((curve['持仓'] != 0).mean()):.1%}"
    rows["买入持有"]["持仓时间占比"] = "100.0%"
    table = pd.DataFrame(rows).rename_axis("指标").reset_index()

    filled = getattr(run.strategy, "stat_filled", None)
    print(f"区间: {curve.index[0].date()} → {curve.index[-1].date()}  ({len(curve)} 根日线)")
    if filled is not None:
        print(f"成交 {filled} 笔  手续费合计 {run.strategy.stat_comm:,.2f}")
    print()
    print(table.to_string(index=False))

    xlsx_path, png_path = write_stats(
        table=table,
        equity=equity,
        buyhold=buyhold,
        outdir=Path(args.outdir),
        stem=f"{spec.name}_stats",
    )

    print()
    print(f"xlsx={xlsx_path.resolve()}")
    print(f"png ={png_path.resolve()}")


if __name__ == "__main__":
    main()
