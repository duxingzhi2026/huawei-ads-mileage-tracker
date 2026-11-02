"""Collect Tesla's rendered, real-time global FSD mileage counter."""

from datetime import datetime
from pathlib import Path
import re

from process_tesla_data import generate_tesla_output_files, upsert_tesla_snapshot
from scrape import TIMEZONE

TESLA_URL = "https://www.tesla.cn/tesla-assisted-driving/safety#data-updated"
TESLA_DATA = Path("tesla_fsd.csv")


def parse_counter_text(text: str) -> int:
    digits = re.sub(r"[^0-9]", "", str(text))
    if not digits:
        raise RuntimeError("Tesla FSD 实时计数器为空或不是数字")
    return int(digits)


def scrape_tesla_fsd_total() -> int:
    """Read the hydrated DOM and verify the displayed counter is still increasing."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale="zh-CN", viewport={"width": 1600, "height": 1200})
        page.goto(TESLA_URL, wait_until="networkidle", timeout=120000)
        counter = page.locator("#total-fsd-mileage")
        counter.wait_for(state="visible", timeout=30000)
        first = parse_counter_text(counter.inner_text())
        page.wait_for_timeout(3000)
        total = parse_counter_text(counter.inner_text())
        browser.close()

    if total <= first:
        raise RuntimeError(
            f"Tesla FSD 计数器未在渲染页面中递增（{first:,} → {total:,}），拒绝写入快照"
        )
    print("Tesla FSD 全球累计：", total, "公里")
    return total


def main():
    now = datetime.now(TIMEZONE)
    total = scrape_tesla_fsd_total()
    # 每日固定采集时点在下午；快照归属其当天。
    upsert_tesla_snapshot(
        TESLA_DATA,
        now.date().isoformat(),
        total,
        now.isoformat(timespec="seconds"),
    )
    generate_tesla_output_files()


if __name__ == "__main__":
    main()
