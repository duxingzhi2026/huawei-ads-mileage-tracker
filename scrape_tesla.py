"""Collect Tesla's server-published FSD mileage baseline and average rate."""

from datetime import datetime
from pathlib import Path
import re
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from process_tesla_data import generate_tesla_output_files, upsert_tesla_snapshot
from scrape import TIMEZONE

TESLA_URL = "https://www.tesla.cn/tesla-assisted-driving/safety#data-updated"
TESLA_DATA = Path("tesla_fsd.csv")
KM_PER_MILE = 1.60934


def fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; MileageTracker/1.0)"})
    with urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def find_counter_script_url(page_html: str) -> str:
    match = re.search(r'<script[^>]+src="([^"]+scope=footer[^\"]*delta=0[^\"]*)"', page_html)
    if not match:
        raise RuntimeError("Tesla FSD 计数器脚本地址未找到")
    return urljoin(TESLA_URL, match.group(1).replace("&amp;", "&"))


def parse_tesla_baseline(script: str) -> dict:
    miles_match = re.search(r"const totalMilesStart\s*=\s*([\d.]+)", script)
    time_match = re.search(r"const startEpochTime\s*=\s*new Date\('([^']+)'\)", script)
    rate_match = re.search(
        r"const totalDistancePerMillisecondAdded\s*=\s*useKm\s*\?\s*\((\d+)\s*/\s*(\d+)\)",
        script,
    )
    if not (miles_match and time_match and rate_match):
        raise RuntimeError("Tesla FSD 基准参数未找到，页面脚本结构可能已经变化")

    miles_per_ms = int(rate_match.group(1)) / int(rate_match.group(2))
    return {
        "base_fsd_miles": int(float(miles_match.group(1))),
        "base_time_utc": time_match.group(1),
        "average_daily_fsd_km": miles_per_ms * 86_400_000 * KM_PER_MILE,
    }


def scrape_tesla_baseline() -> dict:
    page_html = fetch_text(TESLA_URL)
    script_url = find_counter_script_url(page_html)
    baseline = parse_tesla_baseline(fetch_text(script_url))
    baseline["source_url"] = script_url
    print("Tesla FSD 基准：", baseline)
    return baseline


def main():
    now = datetime.now(TIMEZONE)
    baseline = scrape_tesla_baseline()
    upsert_tesla_snapshot(
        TESLA_DATA,
        now.date().isoformat(),
        baseline,
        now.isoformat(timespec="seconds"),
    )
    generate_tesla_output_files()


if __name__ == "__main__":
    main()
