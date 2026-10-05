"""meanrev 参数变体对照表：每个变体只改一个参数（控制变量），BTC/ETH 各跑一遍。

    python sweep_meanrev.py
"""

from __future__ import annotations

import pandas as pd

from backtest.engine import run_backtest
from backtest.metrics import summarize
from strategies.meanrev import MeanRevStrategy, MeanRevSize

DATASETS = ["datas/BTCUSDT_1d.csv", "datas/ETHUSDT_1d.csv"]

VARIANTS = [
    ("基线", {}),
    ("A_atr止损", {"stop_mode": "atr"}),
    ("B_上轨止盈", {"exit_band": "top"}),
    ("C_冷却5", {"cooldown_bars": 5}),
    ("D_阳线过滤", {"require_bull": True}),
]

# 打印时砍掉噪音列（年化波动、回撤区间），完整表进 xlsx
PRINT_COLS = [
    "变体", "期末权益", "总收益率", "年化收益 CAGR",
    "最大回撤", "Calmar", "夏普(rf=0)", "持仓占比", "成交笔数", "退出分布",
]


def exit_mix(events: pd.DataFrame) -> str:
    counts = events.loc[events["event"] == "退出信号", "reason"].value_counts()
    return " / ".join(f"{reason} {count}" for reason, count in counts.items())


def main() -> None:
    rows = []
    for data_path in DATASETS:
        for name, kwargs in VARIANTS:
            run = run_backtest(
                MeanRevStrategy, MeanRevSize,
                data_path=data_path,
                strategy_kwargs=kwargs,
                with_equity_curve=True,
            )
            curve = run.equity
            events = run.strategy.events.to_dataframe()

            rows.append({
                "标的": data_path.rsplit("/", 1)[-1].removesuffix("_1d.csv"),
                "变体": name,
                **summarize(curve["权益"]),
                "持仓占比": f"{(curve['持仓'] != 0).mean():.1%}",
                "成交笔数": run.strategy.stat_filled,
                "退出分布": exit_mix(events),
            })

    table = pd.DataFrame(rows)
    for asset, group in table.groupby("标的", sort=False):
        print(f"\n=== {asset} ===")
        print(group[PRINT_COLS].to_string(index=False))

    xlsx = "datas/logs/meanrev_sweep.xlsx"
    table.to_excel(xlsx, index=False)
    print(f"\nxlsx={xlsx}")


if __name__ == "__main__":
    main()
