from datetime import date
import pandas as pd
from pathlib import Path

DATA = Path("data.csv")

today = str(date.today())

# 这里先用假数据测试，后面再换成华为官网抓取
assist_total = 1000000
drive_total = 5000000

if DATA.exists():
    df = pd.read_csv(DATA)
else:
    df = pd.DataFrame(columns=[
        "date", "assist_total", "drive_total",
        "daily_assist", "daily_drive", "ratio"
    ])

if len(df) > 0:
    last = df.iloc[-1]
    daily_assist = assist_total - last["assist_total"]
    daily_drive = drive_total - last["drive_total"]
else:
    daily_assist = 0
    daily_drive = 0

ratio = daily_assist / daily_drive if daily_drive else 0

new_row = {
    "date": today,
    "assist_total": assist_total,
    "drive_total": drive_total,
    "daily_assist": daily_assist,
    "daily_drive": daily_drive,
    "ratio": ratio
}

df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
df.to_csv(DATA, index=False, encoding="utf-8-sig")

print("done")
