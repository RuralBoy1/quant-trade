"""策略注册表。

加一个新策略 = 加一个 `strategies/<name>/` 子包，再在 REGISTRY 里加一行。
三个入口脚本（export_events / report_stats / compare_pine_logs）靠 `--strategy` 选它。
"""

from __future__ import annotations

from dataclasses import dataclass

from strategies.turtle import TurtleSize, TurtleStrategy


@dataclass(frozen=True)
class StrategySpec:
    name: str
    strategy: type
    sizer: type
    data: str  # 默认行情文件
    pine_log: str | None  # TradingView 参考日志的 glob，没有就 None


REGISTRY = {
    "turtle": StrategySpec(
        name="turtle",
        strategy=TurtleStrategy,
        sizer=TurtleSize,
        data="datas/BTCUSDT_1d.csv",
        pine_log="pine-logs-*Turtle*.csv",
    ),
}


def get(name: str) -> StrategySpec:
    try:
        return REGISTRY[name]
    except KeyError:
        raise SystemExit(
            f"未知策略 {name!r}，可选：{', '.join(sorted(REGISTRY))}"
        ) from None
