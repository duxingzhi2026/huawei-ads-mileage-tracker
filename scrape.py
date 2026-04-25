from datetime import date
from pathlib import Path
import re
import pandas as pd
from playwright.sync_api import sync_playwright

URL = "https://auto.huawei.com/cn/ads/safety-and-data-report"
DATA = Path("data.csv")


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
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale="zh-CN")

        page.goto(URL, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(8000)

        text = page.locator("body").inner_text()

        browser.close()

    print(text[:5000])

    import re

    # 找所有大数字（至少5位）
    nums = re.findall(r'[\d,]{5,}', text)

    nums = [int(x.replace(",", "")) for x in nums]

    nums = sorted(set(nums), reverse=True)

    print("网页中的大数字：", nums[:20])

    if len(nums) < 2:
        raise ValueError("页面没有找到足够大的数字")

    # 最大两个通常就是总里程和辅助驾驶里程
    drive_total = nums[0]
    assist_total = nums[1]

    # 保证总里程大于辅助驾驶里程
    if assist_total > drive_total:
        assist_total, drive_total = drive_total, assist_total

    return assist_total, drive_total


def main():
    today = str(date.today())

    assist_total, drive_total = scrape_real_data()

    if DATA.exists():
        df = pd.read_csv(DATA)
    else:
        df = pd.DataFrame(columns=[
            "date",
            "grab_assist_total",
            "grab_drive_total",
            "assist_total",
            "drive_total",
            "daily_assist",
            "daily_drive",
            "ratio"
        ])

    # 避免同一天重复追加
    if len(df) > 0 and str(df.iloc[-1]["date"]) == today:
        df = df.iloc[:-1]

    if len(df) > 0:
        last = df.iloc[-1]
        daily_assist = assist_total - int(last["assist_total"])
        daily_drive = drive_total - int(last["drive_total"])
    else:
        daily_assist = 0
        daily_drive = 0

    ratio = daily_assist / daily_drive if daily_drive else 0

    new_row = {
        "date": today,

        # 原始抓取值（网页展示用）
        "grab_assist_total": assist_total,
        "grab_drive_total": drive_total,

        # 正式统计字段
        "assist_total": assist_total,
        "drive_total": drive_total,

        "daily_assist": daily_assist,
        "daily_drive": daily_drive,
        "ratio": ratio
    }

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(DATA, index=False, encoding="utf-8-sig")

    print("抓取成功")
    print(new_row)


if __name__ == "__main__":
    main()
