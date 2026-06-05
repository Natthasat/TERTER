"""Backtest comparison: with vs without Time Filter."""
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

# Thai allowed hours from config
ALLOWED_TH = [3, 4, 6, 8, 9, 12, 13, 15, 16, 21, 22, 23, 0]
# Convert to server hours (Thai - 5 = server UTC+2)
ALLOWED_SERVER = set((th - 5) % 24 for th in ALLOWED_TH)

sl_m, tp_m = 1.5, 1.2

def backtest(use_time_filter):
    wins = losses = 0
    net_pts = 0
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

        if use_time_filter and hours_server[i] not in ALLOWED_SERVER:
            i += 1; continue

        ep = c[i]; a = atr[i]
        if sig == 1:
            sl = ep - a*sl_m; tp = ep + a*tp_m
        else:
            sl = ep + a*sl_m; tp = ep - a*tp_m

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

        if result == "WIN":
            wins += 1
            net_pts += a * tp_m
        else:
            losses += 1
            net_pts -= a * sl_m
        i = j + 1
    return wins, losses, net_pts

# Run both
w1, l1, p1 = backtest(False)
w2, l2, p2 = backtest(True)

print("=" * 60)
print("  BACKTEST: Time Filter Comparison (M5 GOLD)")
print("=" * 60)
print(f"{'':30s} {'NO Filter':>12} {'WITH Filter':>12}")
print("-" * 60)
t1 = w1 + l1; t2 = w2 + l2
wr1 = w1/t1*100; wr2 = w2/t2*100
pf1 = (w1 * tp_m) / (l1 * sl_m) if l1 > 0 else 999
pf2 = (w2 * tp_m) / (l2 * sl_m) if l2 > 0 else 999
print(f"{'Trades':30s} {t1:>12} {t2:>12}")
print(f"{'Wins':30s} {w1:>12} {w2:>12}")
print(f"{'Losses':30s} {l1:>12} {l2:>12}")
print(f"{'Win Rate':30s} {wr1:>11.1f}% {wr2:>11.1f}%")
print(f"{'Profit Factor':30s} {pf1:>12.2f} {pf2:>12.2f}")
print(f"{'Net Points':30s} {p1:>11.1f} {p2:>11.1f}")
print(f"{'Trades Filtered Out':30s} {'—':>12} {t1-t2:>12}")
print("-" * 60)
delta_wr = wr2 - wr1
delta_pf = pf2 - pf1
print(f"{'Improvement WR':30s} {'':>12} {'+' if delta_wr>=0 else ''}{delta_wr:.1f}%")
print(f"{'Improvement PF':30s} {'':>12} {'+' if delta_pf>=0 else ''}{delta_pf:.2f}")
print()
if wr2 > wr1:
    print("  >>> Time Filter IMPROVES win rate!")
else:
    print("  >>> Time Filter does not improve win rate")

disconnect_mt5()
