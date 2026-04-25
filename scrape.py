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
    import re

    def parse_container(html):
        tops = re.findall(
            r'<li class="integer-digit" style="top: (-?\d+)px;">',
            html
        )

        digits = []

        for t in tops:
            t = abs(int(t))
            d = round(t / 48)
            if d > 9:
                d = 9
            digits.append(str(d))

        num = "".join(digits)

        return int(num)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page(
            locale="zh-CN",
            viewport={"width": 1600, "height": 2200}
        )

        page.goto(URL, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(10000)

        html = page.content()

        browser.close()

    m1 = re.search(
        r'<div id="numberContainer1">(.*?)</ul></div>',
        html,
        re.S
    )

    m2 = re.search(
        r'<div id="numberContainer2">(.*?)</ul></div>',
        html,
        re.S
    )

    if not m1 or not m2:
        raise ValueError("没有找到数字容器")

    assist_total = parse_container(m1.group(1))
    drive_total = parse_container(m2.group(1))

    # 加单位换算：前三位是亿，中四位是万，后四位个位
    def convert(n):
        s = str(n)

        if len(s) == 11:
            return int(s)

        return int(s)

    assist_total = convert(assist_total)
    drive_total = convert(drive_total)

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
