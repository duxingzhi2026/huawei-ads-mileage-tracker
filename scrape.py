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
    from playwright.sync_api import sync_playwright

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
