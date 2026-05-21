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
DIGIT_HEIGHT = 48


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
    def digit_from_top(top):
        top = str(top or "").replace("px", "").strip()
        if top == "":
            return None
        return round(abs(float(top)) / DIGIT_HEIGHT)

    def digit_from_transform(transform):
        transform = str(transform or "").strip()
        if transform in ("", "none"):
            return None

        values = re.findall(r"-?\d+(?:\.\d+)?", transform)
        if not values:
            return None

        if transform.startswith("matrix3d") and len(values) >= 16:
            translate_y = float(values[13])
        elif transform.startswith("matrix") and len(values) >= 6:
            translate_y = float(values[5])
        else:
            translate_y = float(values[-1])
        return round(abs(translate_y) / DIGIT_HEIGHT)

    def digit_from_inner_text(inner_text):
        text = str(inner_text or "").strip()
        return int(text) if re.fullmatch(r"\d", text) else None

    def read_digits(label, items):
        digits = []
        for index, item in enumerate(items):
            digit = digit_from_top(item.get("top"))
            source = "top"

            if digit is None:
                digit = digit_from_transform(item.get("transform"))
                source = "transform"

            if digit is None:
                digit = digit_from_inner_text(item.get("innerText"))
                source = "innerText"

            print(
                f"{label}[{index}] top={item.get('top')!r}, "
                f"transform={item.get('transform')!r}, "
                f"innerText={item.get('innerText')!r}, "
                f"digit={digit!r}, source={source}"
            )

            if digit is None:
                continue
            digits.append(str(digit))

        if not digits:
            raise RuntimeError(f"{label} 没有抓到任何数字位，页面结构可能变化或页面尚未加载完成")

        return int("".join(digits))

    def read_digit_items(page, selector):
        return page.locator(selector).evaluate_all("""
            els => els.map(el => {
                const style = getComputedStyle(el);
                return {
                    top: style.top,
                    transform: style.transform,
                    innerText: el.innerText,
                };
            })
        """)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            locale="zh-CN",
            viewport={"width": 1600, "height": 2200}
        )

        page.goto(URL, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(12000)

        print("#numberContainer1 count =", page.locator("#numberContainer1").count())
        print("#numberContainer2 count =", page.locator("#numberContainer2").count())
        print(
            "#numberContainer1 li.integer-digit count =",
            page.locator("#numberContainer1 li.integer-digit").count()
        )
        print(
            "#numberContainer2 li.integer-digit count =",
            page.locator("#numberContainer2 li.integer-digit").count()
        )

        assist_items = read_digit_items(page, "#numberContainer1 li.integer-digit")
        drive_items = read_digit_items(page, "#numberContainer2 li.integer-digit")

        browser.close()

    print("assist_items =", assist_items)
    print("drive_items =", drive_items)

    assist_total = read_digits("assist", assist_items)
    drive_total = read_digits("drive", drive_items)

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
