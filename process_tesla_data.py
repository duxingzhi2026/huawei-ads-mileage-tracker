"""Build Tesla FSD average-daily-mileage series from server-published baselines."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

TESLA_DATA = Path("tesla_fsd.csv")
TESLA_DAILY_JSON = Path("tesla_fsd_daily.json")
TESLA_MONTHLY_JSON = Path("tesla_fsd_monthly.json")
DATA_COLUMNS = [
    "date", "base_fsd_miles", "base_time_utc", "average_daily_fsd_km",
    "captured_at", "source_url",
]


def upsert_tesla_snapshot(path: Path, date: str, baseline: dict, captured_at: str) -> None:
    """Store one daily copy of Tesla's server-supplied counter parameters."""
    if path.exists():
        df = pd.read_csv(path)
    else:
        df = pd.DataFrame(columns=DATA_COLUMNS)

    for column in DATA_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    # 旧版记录的是浏览器外推后的累计值；新口径只保留服务器基准参数。
    df = df.reindex(columns=DATA_COLUMNS)
    df = df[df["date"].astype(str) != date]
    df = pd.concat([df, pd.DataFrame([{
        "date": date,
        "base_fsd_miles": int(baseline["base_fsd_miles"]),
        "base_time_utc": baseline["base_time_utc"],
        "average_daily_fsd_km": round(float(baseline["average_daily_fsd_km"]), 2),
        "captured_at": captured_at,
        "source_url": baseline.get("source_url", ""),
    }])], ignore_index=True).sort_values("date")
    df.to_csv(path, index=False, encoding="utf-8-sig")


def load_tesla_data(path: Path = TESLA_DATA) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=DATA_COLUMNS)
    df = pd.read_csv(path)
    if df.empty:
        return df
    for column in DATA_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    df["date"] = df["date"].astype(str)
    df["base_fsd_miles"] = pd.to_numeric(df["base_fsd_miles"], errors="coerce").fillna(0)
    df["average_daily_fsd_km"] = pd.to_numeric(df["average_daily_fsd_km"], errors="coerce").fillna(0)
    return df.sort_values("date").drop_duplicates(subset=["date"], keep="last")


def build_tesla_daily_records(df: pd.DataFrame) -> list[dict]:
    return [{
        "date": str(row.date),
        "base_fsd_miles": int(row.base_fsd_miles),
        "base_time_utc": str(row.base_time_utc),
        "average_daily_fsd_km": float(row.average_daily_fsd_km),
    } for _, row in df.iterrows()]


def build_tesla_monthly_records(daily: list[dict]) -> list[dict]:
    if not daily:
        return []
    df = pd.DataFrame(daily)
    df["month"] = df["date"].str.slice(0, 7)
    records = []
    for month, group in df.groupby("month", sort=True):
        last = group.iloc[-1]
        records.append({
            "date": month,
            "base_fsd_miles": int(last["base_fsd_miles"]),
            "base_time_utc": str(last["base_time_utc"]),
            "average_daily_fsd_km": float(group["average_daily_fsd_km"].mean()),
        })
    return records


def _write_json(path: Path, data: list[dict]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def generate_tesla_output_files() -> None:
    daily = build_tesla_daily_records(load_tesla_data())
    _write_json(TESLA_DAILY_JSON, daily)
    _write_json(TESLA_MONTHLY_JSON, build_tesla_monthly_records(daily))
    print("已生成 tesla_fsd_daily.json / tesla_fsd_monthly.json")


if __name__ == "__main__":
    generate_tesla_output_files()
