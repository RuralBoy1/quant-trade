"""与具体策略无关的回测框架：跑回测、记事件、算指标、出报告。

策略代码放 strategies/<name>/，这里只放可复用的部分。
"""

from backtest.engine import BacktestRun, add_common_args, run_backtest
from backtest.metrics import cagr, max_drawdown, summarize
from backtest.recorders import EquityCurve, EventLog

__all__ = [
    "BacktestRun",
    "EquityCurve",
    "EventLog",
    "add_common_args",
    "cagr",
    "max_drawdown",
    "run_backtest",
    "summarize",
]
