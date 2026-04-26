from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

DATA = Path("data.csv")
DAILY_JSON = Path("daily.json")
MONTHLY_JSON = Path("monthly.json")
SUMMARY_JSON = Path("summary.json")

NUMERIC_COLUMNS = [
    "assist_total",
    "drive_total",
    "daily_assist",
    "daily_drive",
    "ratio",
    "grab_assist_total",
    "grab_drive_total",
]


def _safe_int(value) -> int:
    if pd.isna(value):
        return 0
    return int(float(value))


def _safe_float(value) -> float:
    if pd.isna(value):
        return 0.0
    return float(value)


def load_daily_data() -> pd.DataFrame:
    if not DATA.exists():
        return pd.DataFrame(columns=["date", *NUMERIC_COLUMNS])

    df = pd.read_csv(DATA)
    if df.empty:
        return df

    df["date"] = df["date"].astype(str)
    df = df.sort_values("date").drop_duplicates(subset=["date"], keep="last")

    for col in NUMERIC_COLUMNS:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # 以 CSV 中保存的 02:00 累计值为准，重新统一计算每日差值。
    # 第一条只能作为基准点，没有上一天 02:00 的累计值，所以日增量为 0。
    df["daily_assist"] = df["assist_total"].diff().fillna(0).clip(lower=0)
    df["daily_drive"] = df["drive_total"].diff().fillna(0).clip(lower=0)
    df["ratio"] = df.apply(
        lambda r: r["daily_assist"] / r["daily_drive"] if r["daily_drive"] else 0,
        axis=1,
    )

    return df


def build_daily_records(df: pd.DataFrame) -> list[dict]:
    records = []
    for _, r in df.iterrows():
        records.append({
            "date": str(r["date"]),
            "assist_total": _safe_int(r["assist_total"]),
            "drive_total": _safe_int(r["drive_total"]),
            "daily_assist": _safe_int(r["daily_assist"]),
            "daily_drive": _safe_int(r["daily_drive"]),
            "ratio": _safe_float(r["ratio"]),
            "grab_assist_total": _safe_int(r.get("grab_assist_total", r["assist_total"])),
            "grab_drive_total": _safe_int(r.get("grab_drive_total", r["drive_total"])),
        })
    return records


def build_monthly_records(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []

    temp = df.copy()
    temp["month"] = temp["date"].str.slice(0, 7)

    grouped = temp.groupby("month", sort=True)
    records = []

    for month, g in grouped:
        last = g.iloc[-1]
        monthly_assist = _safe_int(g["daily_assist"].sum())
        monthly_drive = _safe_int(g["daily_drive"].sum())
        records.append({
            "date": month,
            "assist_total": _safe_int(last["assist_total"]),
            "drive_total": _safe_int(last["drive_total"]),
            "daily_assist": monthly_assist,
            "daily_drive": monthly_drive,
            "ratio": monthly_assist / monthly_drive if monthly_drive else 0,
        })

    return records


def build_summary(daily: list[dict], monthly: list[dict]) -> dict:
    latest_daily = daily[-1] if daily else None
    latest_monthly = monthly[-1] if monthly else None

    return {
        "latest_daily": latest_daily,
        "latest_monthly": latest_monthly,
        "daily_count": len(daily),
        "monthly_count": len(monthly),
    }


def write_json(path: Path, data) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def generate_output_files() -> None:
    df = load_daily_data()
    daily = build_daily_records(df)
    monthly = build_monthly_records(df)
    summary = build_summary(daily, monthly)

    write_json(DAILY_JSON, daily)
    write_json(MONTHLY_JSON, monthly)
    write_json(SUMMARY_JSON, summary)

    # 同步把修正后的日增量写回 data.csv，保证 CSV 和 JSON 口径一致。
    if not df.empty:
        df.to_csv(DATA, index=False, encoding="utf-8-sig")

    print("已生成 daily.json / monthly.json / summary.json")


if __name__ == "__main__":
    generate_output_files()
