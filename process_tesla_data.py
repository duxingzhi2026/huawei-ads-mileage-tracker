"""Build daily and monthly FSD increments from Tesla's real-time total counter."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

TESLA_DATA = Path("tesla_fsd.csv")
TESLA_DAILY_JSON = Path("tesla_fsd_daily.json")
TESLA_MONTHLY_JSON = Path("tesla_fsd_monthly.json")


def upsert_tesla_snapshot(path: Path, date: str, total_km: int, captured_at: str) -> None:
    """Store one fixed-time snapshot for the statistical day, replacing a retry."""
    columns = ["date", "fsd_total_km", "captured_at"]
    if path.exists():
        df = pd.read_csv(path)
    else:
        df = pd.DataFrame(columns=columns)

    for column in columns:
        if column not in df.columns:
            df[column] = ""

    df = df[df["date"].astype(str) != date]
    df = pd.concat([df, pd.DataFrame([{
        "date": date,
        "fsd_total_km": int(total_km),
        "captured_at": captured_at,
    }])], ignore_index=True)
    df = df.sort_values("date")
    df.to_csv(path, index=False, encoding="utf-8-sig")


def load_tesla_data(path: Path = TESLA_DATA) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["date", "fsd_total_km", "captured_at"])

    df = pd.read_csv(path)
    if df.empty:
        return df
    df["date"] = df["date"].astype(str)
    df["fsd_total_km"] = pd.to_numeric(df["fsd_total_km"], errors="coerce").fillna(0)
    return df.sort_values("date").drop_duplicates(subset=["date"], keep="last")


def build_tesla_daily_records(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    totals = df["fsd_total_km"].astype("int64")
    increments = totals.diff().fillna(0).clip(lower=0).astype("int64")
    return [{
        "date": str(row.date),
        "fsd_total_km": int(row.fsd_total_km),
        "daily_fsd_km": int(increments.loc[index]),
    } for index, row in df.iterrows()]


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
            "fsd_total_km": int(last["fsd_total_km"]),
            "monthly_fsd_km": int(group["daily_fsd_km"].sum()),
        })
    return records


def _write_json(path: Path, data: list[dict]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def generate_tesla_output_files() -> None:
    daily = build_tesla_daily_records(load_tesla_data())
    monthly = build_tesla_monthly_records(daily)
    _write_json(TESLA_DAILY_JSON, daily)
    _write_json(TESLA_MONTHLY_JSON, monthly)
    print("已生成 tesla_fsd_daily.json / tesla_fsd_monthly.json")


if __name__ == "__main__":
    generate_tesla_output_files()
