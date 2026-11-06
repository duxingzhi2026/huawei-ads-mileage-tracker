"""Save one Huawei cumulative-mileage snapshot and rebuild hourly chart data."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from process_hourly_data import generate_hourly_output
from scrape import scrape_real_data


DATA = Path("hourly.csv")
TIMEZONE = ZoneInfo("Asia/Shanghai")


def append_snapshot(captured_at: datetime, assist_total: int, drive_total: int) -> None:
    record = pd.DataFrame([{
        "captured_at": captured_at.astimezone(TIMEZONE).isoformat(timespec="seconds"),
        "assist_total": assist_total,
        "drive_total": drive_total,
    }])
    if DATA.exists():
        previous = pd.read_csv(DATA)
        frame = pd.concat([previous, record], ignore_index=True)
    else:
        frame = record
    frame = frame.drop_duplicates(subset=["captured_at"], keep="last").sort_values("captured_at")
    frame.to_csv(DATA, index=False, encoding="utf-8-sig")


def main() -> None:
    captured_at = datetime.now(TIMEZONE)
    assist_total, drive_total = scrape_real_data()
    append_snapshot(captured_at, assist_total, drive_total)
    generate_hourly_output()
    print(f"小时快照已保存：{captured_at.isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()
