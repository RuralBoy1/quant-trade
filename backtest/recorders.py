"""回测过程中的记录器：结构化事件日志 + 逐 bar 权益曲线。"""

from __future__ import annotations

import datetime as dt

import backtrader as bt
import pandas as pd

# 事件的字段随类型不同而不同，这里固定一个列顺序，让导出的表更好读。
# 名字与 TradingView 的 pine-logs 保持一致，方便逐字段对比。
EVENT_COLUMNS = [
    "date", "event", "role", "reason",
    "close", "entryUp", "exitDown", "trigger",
    "fill", "barOpen", "N", "qty",
    "addedSize", "closedSize", "units",
    "nextAdd", "stop", "avgPrice", "position",
    "equity", "estimatedCash", "buyFills", "sellFills",
    "size", "cash", "status",
]


class EventLog:
    """收集策略事件日志。

    策略持有一个实例，log() 委托给它：verbose 只控制打印，结构化字段永远记下来，
    所以安静模式跑完也能导出完整日志。

    刻意不做成 mixin —— backtrader 的 MetaParams 元类在多继承时合并 params
    的行为容易出坑，用一个普通对象持有更稳。
    """

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose
        self.rows: list[dict[str, object]] = []

    def add(self, day: dt.date, txt: str, force: bool = False, **fields) -> None:
        """打印一行日志并记录。

        force=True 的异常日志无视 verbose 总是打印（资金不足/被拒这类要看得见）。
        """
        if self.verbose or force:
            print(f"{day} {txt}")
        self.record(day, **fields)

    def record(self, day: dt.date, **fields) -> None:
        """只记录不打印。回测结束时补一条持仓状态用。"""
        self.rows.append({"date": day.isoformat(), **fields})

    def to_dataframe(self) -> pd.DataFrame:
        frame = pd.DataFrame(self.rows)
        if frame.empty:
            return frame
        ordered = [name for name in EVENT_COLUMNS if name in frame.columns]
        extra = [name for name in frame.columns if name not in ordered]
        return frame.reindex(columns=ordered + extra)


class EquityCurve(bt.Analyzer):
    """逐 bar 记录权益和持仓，用来算回撤、夏普、持仓时间占比。"""

    def start(self):
        self.dates: list = []
        self.values: list[float] = []
        self.positions: list[float] = []

    def next(self):
        self.dates.append(self.strategy.data.datetime.date(0))
        self.values.append(self.strategy.broker.getvalue())
        self.positions.append(self.strategy.position.size)

    def get_analysis(self):
        return {
            "dates": self.dates,
            "values": self.values,
            "positions": self.positions,
        }
