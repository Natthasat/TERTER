"""Analyze win rate by hour to find best trading times."""
import sys, numpy as np
import MetaTrader5 as mt5
from mt5_data import connect_mt5, disconnect_mt5, get_ohlc
from indicators import add_indicators

connect_mt5()
df = get_ohlc("GOLD", mt5.TIMEFRAME_M5, 5000)
df = add_indicators(df, ema_fast=10, ema_slow=30, rsi_period=14, atr_period=14, adx_period=14)
df = df.reset_index(drop=True)

c = df["close"].values; h = df["high"].values; l = df["low"].values
ef = df["ema_fast"].values; es = df["ema_slow"].values
rsi = df["rsi"].values; adx = df["adx"].values; atr = df["atr"].values
pl = np.roll(l, 1); ph = np.roll(h, 1); pef = np.roll(ef, 1)
pl[0] = l[0]; ph[0] = h[0]; pef[0] = ef[0]
times = df["time"].values
n = len(c)

hours_server = np.array([int(str(t)[11:13]) for t in times])

stats = {}
for hr in range(24):
    stats[hr] = {"wins": 0, "losses": 0, "total": 0}

sl_m, tp_m = 1.5, 1.2
i = 2
while i < n:
    if adx[i] < 12:
        i += 1; continue
    sig = 0
    if c[i] > ef[i] > es[i] and rsi[i] > 50 and pl[i] <= pef[i]:
        sig = 1
    elif c[i] < ef[i] < es[i] and rsi[i] < 50 and ph[i] >= pef[i]:
        sig = -1
    if sig == 0:
        i += 1; continue

    ep = c[i]; a = atr[i]
    hr = hours_server[i]
    if sig == 1:
        sl = ep - a * sl_m; tp = ep + a * tp_m
    else:
        sl = ep + a * sl_m; tp = ep - a * tp_m

    j = i + 1
    result = ""
    while j < n:
        if sig == 1:
            if l[j] <= sl: result = "LOSS"; break
            if h[j] >= tp: result = "WIN"; break
        else:
            if h[j] >= sl: result = "LOSS"; break
            if l[j] <= tp: result = "WIN"; break
        j += 1
    else:
        result = "WIN" if ((c[-1] - ep) * sig > 0) else "LOSS"

    stats[hr]["total"] += 1
    if result == "WIN":
        stats[hr]["wins"] += 1
    else:
        stats[hr]["losses"] += 1
    i = j + 1

print("=" * 65)
print("  WIN RATE by HOUR (Server UTC+2 -> Thai UTC+7)")
print("=" * 65)
header = f"{'Server':>7} {'Thai':>6} | {'Trades':>6} {'Wins':>5} {'WR%':>6}  Graph"
print(header)
print("-" * 65)

total_t = total_w = 0
best_hours = []
for hr in range(24):
    s = stats[hr]
    if s["total"] < 3:
        continue
    wr = s["wins"] / s["total"] * 100
    thai_hr = (hr + 5) % 24
    bar = "#" * int(wr / 5)
    star = " <<< BEST" if wr >= 60 and s["total"] >= 8 else ""
    print(f"{hr:>5}:00 {thai_hr:>4}:00 | {s['total']:>6} {s['wins']:>5} {wr:>5.1f}%  {bar}{star}")
    total_t += s["total"]; total_w += s["wins"]
    if wr >= 55 and s["total"] >= 5:
        best_hours.append((hr, thai_hr, wr, s["total"]))

print("-" * 65)
if total_t > 0:
    print(f"{'TOTAL':>14} | {total_t:>6} {total_w:>5} {total_w / total_t * 100:>5.1f}%")

# Session analysis
print()
print("=" * 65)
print("  SESSION ANALYSIS (Thai time)")
print("=" * 65)
sessions = {
    "Asia       (07-14 TH)": range(2, 9),
    "London     (14-20 TH)": range(9, 15),
    "New York   (20-02 TH)": list(range(15, 21)),
    "Late NY    (02-05 TH)": list(range(21, 24)),
    "Dead Zone  (05-07 TH)": [0, 1],
}
best_session = None
best_wr = 0
for name, hrs in sessions.items():
    tw = sum(stats[h]["wins"] for h in hrs)
    tt = sum(stats[h]["total"] for h in hrs)
    if tt < 5:
        continue
    wr = tw / tt * 100
    if wr >= 58:
        label = "[OK]"
    elif wr >= 50:
        label = "[--]"
    else:
        label = "[XX]"
    print(f"  {label} {name} | Trades: {tt:>4} | WR: {wr:.1f}%")
    if wr > best_wr:
        best_wr = wr
        best_session = name

print()
print("=" * 65)
print("  RECOMMENDATION")
print("=" * 65)
if best_hours:
    best_thai = sorted(best_hours, key=lambda x: -x[2])
    print(f"  Best hours (Thai time):")
    for _, th, wr, cnt in best_thai[:5]:
        print(f"    {th:02d}:00 - {(th+1)%24:02d}:00  WR={wr:.1f}%  ({cnt} trades)")
if best_session:
    print(f"  Best session: {best_session.strip()} (WR={best_wr:.1f}%)")

disconnect_mt5()
