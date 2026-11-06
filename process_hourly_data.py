"""Convert irregular cumulative Huawei mileage snapshots into hour-of-day averages.

Snapshots are cumulative counters, not per-hour measurements.  Consecutive
snapshots are therefore treated as one interval and its increment is allocated
proportionally to every clock-hour it overlaps.  This prevents a late GitHub
Actions run from assigning several hours of driving to the hour in which it
eventually ran.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


RAW_DATA = Path("hourly.csv")
OUTPUT = Path("hourly.json")
TIMEZONE = ZoneInfo("Asia/Shanghai")
# Normal sampling is every 5 minutes.  A longer interruption is not safe to
# turn into made-up hourly behaviour, so omit only that interval.
MAX_INTERVAL = timedelta(minutes=30)


def _empty_payload() -> dict:
    return {
        "months": [],
        "note": "小时数据正在积累，采样满一个自然月后将形成完整月度均值。",
    }


def _read_snapshots() -> pd.DataFrame:
    if not RAW_DATA.exists():
        return pd.DataFrame(columns=["captured_at", "assist_total", "drive_total"])

    frame = pd.read_csv(RAW_DATA)
    required = {"captured_at", "assist_total", "drive_total"}
    if frame.empty or not required.issubset(frame.columns):
        return pd.DataFrame(columns=list(required))

    frame["captured_at"] = pd.to_datetime(frame["captured_at"], errors="coerce", utc=True)
    frame["assist_total"] = pd.to_numeric(frame["assist_total"], errors="coerce")
    frame["drive_total"] = pd.to_numeric(frame["drive_total"], errors="coerce")
    frame = frame.dropna(subset=["captured_at", "assist_total", "drive_total"])
    return frame.sort_values("captured_at").drop_duplicates("captured_at", keep="last")


def build_hourly_payload(frame: pd.DataFrame) -> dict:
    if len(frame) < 2:
        return _empty_payload()

    frame = frame.copy()
    frame["local_time"] = frame["captured_at"].dt.tz_convert(TIMEZONE)
    newest = frame["local_time"].iloc[-1]
    month_buckets: dict[str, list[dict]] = {}
    skipped_intervals = 0

    for previous, current in zip(frame.iloc[:-1].itertuples(), frame.iloc[1:].itertuples()):
        start = previous.local_time.to_pydatetime()
        end = current.local_time.to_pydatetime()
        duration = end - start
        assist_delta = float(current.assist_total - previous.assist_total)
        drive_delta = float(current.drive_total - previous.drive_total)

        if duration <= timedelta(0) or duration > MAX_INTERVAL or assist_delta < 0 or drive_delta < 0:
            skipped_intervals += 1
            continue

        cursor = start
        full_seconds = duration.total_seconds()
        while cursor < end:
            next_hour = (cursor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
            segment_end = min(next_hour, end)
            seconds = (segment_end - cursor).total_seconds()
            fraction = seconds / full_seconds
            month = cursor.strftime("%Y-%m")
            buckets = month_buckets.setdefault(
                month,
                [{"assist": 0.0, "drive": 0.0, "coverage": 0.0, "intervals": 0} for _ in range(24)],
            )
            bucket = buckets[cursor.hour]
            bucket["assist"] += assist_delta * fraction
            bucket["drive"] += drive_delta * fraction
            bucket["coverage"] += seconds / 3600
            bucket["intervals"] += 1
            cursor = segment_end

    months = []
    for month, buckets in sorted(month_buckets.items()):
        hours = []
        for hour, bucket in enumerate(buckets):
            coverage = bucket["coverage"]
            if coverage == 0:
                continue
            average_assist = bucket["assist"] / coverage
            average_drive = bucket["drive"] / coverage
            hours.append({
                "hour": hour,
                "assist_km": round(average_assist, 2),
                "drive_km": round(average_drive, 2),
                "ratio": round(average_assist / average_drive, 8) if average_drive else 0,
                "coverage_days": round(coverage, 2),
                "intervals": bucket["intervals"],
            })
        months.append({"month": month, "hours": hours})

    return {
        "latest_month": newest.strftime("%Y-%m"),
        "months": months,
        "skipped_intervals": skipped_intervals,
        "note": "按有效采样时长加权；单次采样间隔超过 30 分钟的区间不纳入计算。",
    }


def generate_hourly_output() -> None:
    payload = build_hourly_payload(_read_snapshots())
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成 {OUTPUT}")


if __name__ == "__main__":
    generate_hourly_output()
