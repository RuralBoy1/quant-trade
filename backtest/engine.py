"""回测引擎：组装 cerebro 并运行。参数解析的公共部分也在这里。"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import backtrader as bt
import pandas as pd

from backtest.recorders import EquityCurve


@dataclass
class BacktestRun:
    strategy: bt.Strategy
    cerebro: bt.Cerebro
    data: pd.DataFrame
    equity: pd.DataFrame | None = None  # 只有 with_equity_curve=True 时才有


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """三个入口脚本共用的参数。"""
    parser.add_argument("--data", default=None, help="行情 CSV；默认取策略注册表里的配置")
    parser.add_argument("--cash", type=float, default=100000.0)
    parser.add_argument("--commission", type=float, default=0.001)
    parser.add_argument("--slippage", type=float, default=0.0,
                        help="与 Pine 对齐时保持 0；cerobro_core.py 里用的 0.001 会产生假差异")


def run_backtest(
    strategy_cls,
    sizer_cls,
    *,
    data_path: str,
    cash: float = 100000.0,
    commission: float = 0.001,
    slippage: float = 0.0,
    strategy_kwargs: dict | None = None,
    with_equity_curve: bool = False,
) -> BacktestRun:
    dataframe = pd.read_csv(data_path, index_col=0, parse_dates=True)

    cerebro = bt.Cerebro()
    cerebro.adddata(bt.feeds.PandasData(dataname=dataframe))
    cerebro.addstrategy(strategy_cls, **(strategy_kwargs or {}))
    cerebro.addsizer(sizer_cls)
    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=commission)
    if slippage:
        cerebro.broker.set_slippage_perc(perc=slippage)
    if with_equity_curve:
        cerebro.addanalyzer(EquityCurve, _name="equity")

    strategy = cerebro.run()[0]

    equity = None
    if with_equity_curve:
        analysis = strategy.analyzers.equity.get_analysis()
        equity = pd.DataFrame(
            {"权益": analysis["values"], "持仓": analysis["positions"]},
            index=pd.to_datetime(analysis["dates"]),
        )

    return BacktestRun(strategy=strategy, cerebro=cerebro, data=dataframe, equity=equity)
