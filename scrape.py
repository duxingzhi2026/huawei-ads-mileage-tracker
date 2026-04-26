from datetime import datetime, timedelta
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import pandas as pd
from playwright.sync_api import sync_playwright

from process_data import generate_output_files

URL = "https://auto.huawei.com/cn/ads/safety-and-data-report"
DATA = Path("data.csv")
TIMEZONE = ZoneInfo("Asia/Shanghai")


def parse_number(text):
    text = text.replace(",", "")
    m = re.search(r"([\d.]+)\s*(亿|万)?", text)
    if not m:
        return None

    num = float(m.group(1))
    unit = m.group(2)

    if unit == "亿":
        num *= 100000000
    elif unit == "万":
        num *= 10000

    return int(num)


def scrape_real_data():
    def tops_to_number(tops):
        digits = []
        for top in tops:
            top = str(top).replace("px", "").strip()
            if top == "":
                continue
            digit = round(abs(float(top)) / 48)
            digits.append(str(digit))
        return int("".join(digits))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            locale="zh-CN",
            viewport={"width": 1600, "height": 2200}
        )

        page.goto(URL, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(12000)

        assist_tops = page.locator(
            "#numberContainer1 li.integer-digit"
        ).evaluate_all("""
            els => els.map(el => getComputedStyle(el).top)
        """)

        drive_tops = page.locator(
            "#numberContainer2 li.integer-digit"
        ).evaluate_all("""
            els => els.map(el => getComputedStyle(el).top)
        """)

        browser.close()

    print("assist_tops =", assist_tops)
    print("drive_tops =", drive_tops)

    assist_total = tops_to_number(assist_tops)
    drive_total = tops_to_number(drive_tops)

    print("辅助驾驶累计：", assist_total)
    print("总驾驶累计：", drive_total)

    return assist_total, drive_total


def get_stat_date(now=None):
    """
    每天 02:00 抓到的是“截至今天 02:00 的累计值”。
    该累计值减去前一天 02:00 的累计值，得到的是“昨天”的行驶里程。

    例：2026-04-27 02:00 抓取值 - 2026-04-26 02:00 抓取值 = 2026-04-26 的里程。
    """
    if now is None:
        now = datetime.now(TIMEZONE)
    return (now.date() - timedelta(days=1)).isoformat()


def main():
    stat_date = get_stat_date()

    assist_total, drive_total = scrape_real_data()

    if DATA.exists():
        df = pd.read_csv(DATA)
    else:
        df = pd.DataFrame(columns=[
            "date",
            "assist_total",
            "drive_total",
            "daily_assist",
            "daily_drive",
            "ratio",
            "grab_assist_total",
            "grab_drive_total"
        ])

    # 避免同一个统计日期重复追加。
    # 例如当天手动重跑 workflow 时，先删除旧的同日记录，再用最新抓取值重算。
    if len(df) > 0 and str(df.iloc[-1]["date"]) == stat_date:
        df = df.iloc[:-1]

    if len(df) > 0:
        last = df.iloc[-1]
        previous_assist_total = int(float(last["assist_total"]))
        previous_drive_total = int(float(last["drive_total"]))
        daily_assist = assist_total - previous_assist_total
        daily_drive = drive_total - previous_drive_total
    else:
        # 第一条记录只能作为基准点，没有上一天 02:00 的累计值，所以日增量记为 0。
        daily_assist = 0
        daily_drive = 0

    ratio = daily_assist / daily_drive if daily_drive else 0

    new_row = {
        # 注意：这里不是抓取当天，而是本次差值对应的统计日期。
        "date": stat_date,

        # 正式统计字段：保存本次 02:00 抓到的累计值，供下一天计算差值使用。
        "assist_total": assist_total,
        "drive_total": drive_total,

        # 本统计日的行驶里程 = 本次累计值 - 上一次 02:00 累计值。
        "daily_assist": daily_assist,
        "daily_drive": daily_drive,
        "ratio": ratio,

        # 原始抓取值保留一份，方便以后排查。
        "grab_assist_total": assist_total,
        "grab_drive_total": drive_total,
    }

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(DATA, index=False, encoding="utf-8-sig")
    generate_output_files()

    print("抓取成功")
    print("统计日期：", stat_date)
    print(new_row)


if __name__ == "__main__":
    main()
