"""把回测结果写成人能看的东西：Excel 和图表。"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def write_events(events: pd.DataFrame, outdir: Path, stem: str) -> tuple[Path, Path]:
    """事件表落盘。csv 给脚本读，xlsx 给人看。"""
    outdir.mkdir(parents=True, exist_ok=True)
    csv_path = outdir / f"{stem}.csv"
    xlsx_path = outdir / f"{stem}.xlsx"

    events.to_csv(csv_path, index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        events.to_excel(writer, sheet_name="事件", index=False)
        summary = (
            events.groupby("event", sort=False).size().rename("条数").reset_index()
        )
        summary.to_excel(writer, sheet_name="汇总", index=False)

    return csv_path, xlsx_path


def _configure_cjk_font() -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def write_stats(
    *,
    table: pd.DataFrame,
    equity: pd.Series,
    buyhold: pd.Series,
    outdir: Path,
    stem: str,
) -> tuple[Path, Path]:
    """指标表 + 权益曲线图（上图对数轴看收益，下图看回撤）。"""
    outdir.mkdir(parents=True, exist_ok=True)
    xlsx_path = outdir / f"{stem}.xlsx"
    png_path = outdir / f"{stem}.png"

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        table.to_excel(writer, sheet_name="指标", index=False)
        pd.DataFrame({"策略": equity, "买入持有": buyhold}).to_excel(
            writer, sheet_name="权益曲线"
        )

    _configure_cjk_font()
    figure, (top, bottom) = plt.subplots(
        2, 1, figsize=(12, 8), sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )

    top.plot(equity.index, equity, label="策略", linewidth=1.5)
    top.plot(buyhold.index, buyhold, label="买入持有", linewidth=1.2, alpha=0.8)
    top.set_yscale("log")
    top.set_ylabel("权益（对数轴）")
    top.set_title("策略 vs 买入持有")
    top.legend()
    top.grid(alpha=0.3)

    drawdown = equity / equity.cummax() - 1.0
    bottom.fill_between(drawdown.index, drawdown * 100, 0, color="tab:red", alpha=0.4)
    bottom.set_ylabel("策略回撤 %")
    bottom.grid(alpha=0.3)

    figure.tight_layout()
    figure.savefig(png_path, dpi=120)
    plt.close(figure)

    return xlsx_path, png_path
