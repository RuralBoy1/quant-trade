"""风险收益指标。回答「这个策略值不值得跑」。"""

from __future__ import annotations

import math

import pandas as pd

# 加密现货 7x24，一年按 365 天算
DAYS_PER_YEAR = 365


def max_drawdown(equity: pd.Series) -> tuple[float, object, object]:
    """返回 (最大回撤, 峰值日, 谷底日)。回撤是负数。"""
    peak = equity.cummax()
    drawdown = equity / peak - 1.0
    trough = drawdown.idxmin()
    return float(drawdown.min()), equity.loc[:trough].idxmax(), trough


def cagr(equity: pd.Series) -> float:
    """年化复合增长率。"""
    years = (equity.index[-1] - equity.index[0]).days / DAYS_PER_YEAR
    if years <= 0:
        return float("nan")
    return (equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0


def summarize(equity: pd.Series) -> dict[str, object]:
    """把一条权益曲线压成一行指标。值都格式化成字符串，方便直接进 Excel。"""
    returns = equity.pct_change(fill_method=None).dropna()
    mdd, peak_day, trough_day = max_drawdown(equity)
    growth = cagr(equity)
    volatility = float(returns.std()) * math.sqrt(DAYS_PER_YEAR)
    sharpe = growth / volatility if volatility > 0 else float("nan")
    return {
        "期末权益": f"{equity.iloc[-1]:,.0f}",
        "总收益率": f"{equity.iloc[-1] / equity.iloc[0] - 1:.1%}",
        "年化收益 CAGR": f"{growth:.2%}",
        "年化波动": f"{volatility:.2%}",
        "夏普(rf=0)": f"{sharpe:.2f}",
        "最大回撤": f"{mdd:.2%}",
        "回撤区间": f"{pd.Timestamp(peak_day).date()} → {pd.Timestamp(trough_day).date()}",
        "Calmar": f"{growth / abs(mdd):.2f}" if mdd < 0 else "n/a",
    }
