"""把 Backtrader 事件日志和 TradingView Pine 日志逐条对齐，输出差异 Excel。

先跑 export_events.py 生成事件日志，再跑本脚本：

    python export_events.py --strategy turtle
    python compare_pine_logs.py --strategy turtle

Pine 日志是格式化后的字符串（价格 2 位小数），所以数值比较带容差，
避免把纯粹的显示精度差异当成真差异。
"""

from __future__ import annotations

import argparse
import glob
from pathlib import Path

import pandas as pd

import strategies

# 纯说明性事件，两边对不齐是正常的（Backtrader 侧没有对应日志）
INFO_EVENTS = {"进入本地数据范围", "指标预热完成"}

# 想让 Excel 里字段列按这个顺序排，不在表里的字段排到后面
FIELD_ORDER = [
    "role", "reason", "close", "entryUp", "exitDown", "trigger",
    "fill", "barOpen", "N", "qty", "addedSize", "closedSize", "units",
    "nextAdd", "stop", "avgPrice", "position",
    "equity", "estimatedCash", "buyFills", "sellFills", "size", "cash", "status",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="对比 Backtrader 与 TradingView 的策略日志")
    parser.add_argument("--strategy", default="turtle", choices=sorted(strategies.REGISTRY))
    parser.add_argument("--bt", default=None, help="Backtrader 事件 csv，默认 <策略>_events.csv")
    parser.add_argument("--pine", default=None,
                        help="Pine 日志 csv，默认按策略注册表里的 glob 找")
    parser.add_argument("--out", default=None, help="输出 xlsx，默认 <策略>_log_compare.xlsx")
    parser.add_argument("--outdir", default="datas/logs")
    parser.add_argument("--abs-tol", type=float, default=0.05,
                        help="数值绝对容差，默认 0.05（Pine 价格只保留 2 位小数）")
    parser.add_argument("--rel-tol", type=float, default=1e-4, help="数值相对容差")
    parser.add_argument("--ignore", default=",".join(sorted(INFO_EVENTS)),
                        help="不参与对比的事件类型，逗号分隔；传空字符串表示全都比")
    parser.add_argument("--max-print", type=int, default=20, help="控制台最多打印多少条差异")
    return parser.parse_args()


def _to_number(text: str):
    """把 Pine 日志里的值转成数值：去掉千分位，能转 int 就 int，否则 float，再否则原样返回。"""
    cleaned = text.replace(",", "")
    try:
        return int(cleaned)
    except ValueError:
        pass
    try:
        return float(cleaned)
    except ValueError:
        return text


def parse_pine(path: Path) -> pd.DataFrame:
    """Pine 日志每行的格式是：事件名 | k=v | k=v | ..."""
    raw = pd.read_csv(path, encoding="utf-8-sig")
    message_column = "消息" if "消息" in raw.columns else raw.columns[-1]

    records = []
    for message in raw[message_column].astype(str):
        parts = [part.strip() for part in message.split("|")]
        record: dict[str, object] = {"event": parts[0]}
        for part in parts[1:]:
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            record[key.strip()] = _to_number(value.strip())
        # 消息里的“日期”是纯 YYYY-MM-DD，csv 那一列是带时区的完整时间戳，取前者
        record["date"] = record.pop("日期", None)
        records.append(record)
    return pd.DataFrame(records)


def _add_sequence(frame: pd.DataFrame) -> pd.DataFrame:
    """同一天同一类事件可能不止一条，用序号区分，才能按下标一一对齐。

    列名不带下划线，否则 DataFrame.itertuples 会把它重命名成 _1/_2 这种位置名。
    """
    frame = frame.copy()
    frame["date"] = frame["date"].astype(str).str.slice(0, 10)
    frame["seq_index"] = frame.groupby(["date", "event"], sort=False).cumcount() + 1
    return frame


def _values_match(left, right, abs_tol: float, rel_tol: float) -> bool:
    if pd.isna(left) and pd.isna(right):
        return True
    if pd.isna(left) or pd.isna(right):
        return False
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(left - right) <= max(abs_tol, rel_tol * max(abs(left), abs(right)))
    return str(left) == str(right)


def build_report(bt: pd.DataFrame, tv: pd.DataFrame, ignore: set[str],
                 abs_tol: float, rel_tol: float) -> dict[str, pd.DataFrame]:
    bt = _add_sequence(bt)
    tv = _add_sequence(tv)

    merged = bt.merge(
        tv, on=["date", "event", "seq_index"], how="outer",
        suffixes=("_bt", "_tv"), indicator=True,
    ).sort_values(["date", "event", "seq_index"], kind="stable").reset_index(drop=True)
    merged = merged.rename(columns={"_merge": "merge_kind"})

    bt_fields = set(bt.columns) - {"date", "event", "seq_index"}
    tv_fields = set(tv.columns) - {"date", "event", "seq_index"}
    shared_fields = [f for f in FIELD_ORDER if f in bt_fields & tv_fields]
    shared_fields += sorted(bt_fields & tv_fields - set(shared_fields))

    side_by_side = []
    diffs = []

    for row in merged.itertuples(index=False):
        date, event, seq = row.date, row.event, row.seq_index

        if row.merge_kind == "left_only":
            status = "仅 Backtrader"
        elif row.merge_kind == "right_only":
            status = "仅 TradingView"
        else:
            status = "OK"

        entry = {"日期": date, "事件": event, "序号": seq, "状态": status}
        for field in shared_fields:
            entry[f"bt_{field}"] = getattr(row, f"{field}_bt", None)
            entry[f"tv_{field}"] = getattr(row, f"{field}_tv", None)

        if event in ignore:
            entry["状态"] = f"{status}（不参与对比）"
            side_by_side.append(entry)
            continue

        if row.merge_kind != "both":
            side_by_side.append(entry)
            diffs.append({
                "日期": date, "事件": event, "序号": seq, "字段": "<整条事件>",
                "Backtrader": "缺失" if row.merge_kind == "right_only" else "有",
                "TradingView": "缺失" if row.merge_kind == "left_only" else "有",
                "差值": None,
                "备注": status,
            })
            continue

        mismatched = False
        for field in shared_fields:
            left = getattr(row, f"{field}_bt", None)
            right = getattr(row, f"{field}_tv", None)
            if _values_match(left, right, abs_tol, rel_tol):
                continue
            mismatched = True
            delta = (left - right) if isinstance(left, (int, float)) and isinstance(right, (int, float)) else None
            diffs.append({
                "日期": date, "事件": event, "序号": seq, "字段": field,
                "Backtrader": left, "TradingView": right, "差值": delta,
                "备注": "",
            })
        if mismatched:
            entry["状态"] = "有差异"
        side_by_side.append(entry)

    compare = pd.DataFrame(side_by_side)
    detail = pd.DataFrame(diffs)

    # 汇总：每类事件的条数和对齐情况 + 首个差异
    active = compare[~compare["状态"].str.contains("不参与对比")]
    per_event = []
    for event in sorted(set(bt["event"]) | set(tv["event"])):
        bt_count = int((bt["event"] == event).sum())
        tv_count = int((tv["event"] == event).sum())
        subset = active[active["事件"] == event]
        per_event.append({
            "事件": event,
            "Backtrader 条数": bt_count,
            "TradingView 条数": tv_count,
            "条数差": bt_count - tv_count,
            "对齐后有差异": int((subset["状态"] == "有差异").sum()),
            "仅 Backtrader": int((subset["状态"] == "仅 Backtrader").sum()),
            "仅 TradingView": int((subset["状态"] == "仅 TradingView").sum()),
        })

    real_diffs = active[active["状态"] != "OK"]
    summary_rows = [
        {"项目": "首个不一致", "值": str(real_diffs["日期"].iloc[0]) if len(real_diffs) else "无"},
        {"项目": "首个不一致事件", "值": str(real_diffs["事件"].iloc[0]) if len(real_diffs) else "无"},
        {"项目": "不一致月份数", "值": int(real_diffs["日期"].str.slice(0, 7).nunique()) if len(real_diffs) else 0},
        {"项目": "字段级差异条数", "值": len(detail[detail["字段"] != "<整条事件>"]) if len(detail) else 0},
        {"项目": "事件级缺失条数", "值": int((detail["字段"] == "<整条事件>").sum()) if len(detail) else 0},
    ]

    return {
        "汇总": pd.DataFrame(summary_rows),
        "按事件汇总": pd.DataFrame(per_event),
        "对比": compare,
        "差异明细": detail,
        "Backtrader": bt.drop(columns=["seq_index"]),
        "TradingView": tv.drop(columns=["seq_index"]),
    }


def _resolve_pine(spec, outdir: Path, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    if not spec.pine_log:
        raise SystemExit(f"策略 {spec.name!r} 没有配置 TradingView 参考日志，请用 --pine 指定")
    matches = sorted(outdir.glob(spec.pine_log))
    if not matches:
        raise SystemExit(f"在 {outdir} 下找不到 {spec.pine_log}，请用 --pine 指定")
    return matches[-1]


def main() -> None:
    args = parse_args()
    ignore = {name.strip() for name in args.ignore.split(",") if name.strip()}
    spec = strategies.get(args.strategy)
    outdir = Path(args.outdir)

    bt_path = Path(args.bt) if args.bt else outdir / f"{spec.name}_events.csv"
    if not bt_path.exists():
        raise SystemExit(f"找不到 {bt_path}，先运行：python export_events.py --strategy {spec.name}")
    pine_path = _resolve_pine(spec, outdir, args.pine)

    print(f"backtrader = {bt_path}")
    print(f"pine       = {pine_path}")

    bt = pd.read_csv(bt_path, encoding="utf-8-sig")
    tv = parse_pine(pine_path)

    sheets = build_report(bt, tv, ignore, args.abs_tol, args.rel_tol)

    out_path = Path(args.out) if args.out else outdir / f"{spec.name}_log_compare.xlsx"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)

    print(sheets["汇总"].to_string(index=False))
    print()
    print(sheets["按事件汇总"].to_string(index=False))
    print()
    detail = sheets["差异明细"]
    if len(detail):
        print(f"差异明细（共 {len(detail)} 条，打印前 {args.max_print} 条）：")
        print(detail.head(args.max_print).to_string(index=False))
    else:
        print("两边完全一致，没有差异。")
    print()
    print(f"excel={out_path.resolve()}")


if __name__ == "__main__":
    main()
