"""Backtest advanced features to find what improves WR."""
import numpy as np
import MetaTrader5 as mt5
import sys; sys.path.insert(0, ".")
from mt5_data import connect_mt5, disconnect_mt5, get_ohlc
from indicators import add_indicators

connect_mt5()

# Load M5 data
df5 = get_ohlc("GOLD", mt5.TIMEFRAME_M5, 5000)
df5 = add_indicators(df5, ema_fast=10, ema_slow=30, rsi_period=14, atr_period=14, adx_period=14)
df5 = df5.reset_index(drop=True)

# Load M15 for multi-timeframe
df15 = get_ohlc("GOLD", mt5.TIMEFRAME_M15, 2000)
df15 = add_indicators(df15, ema_fast=10, ema_slow=30, rsi_period=14, atr_period=14, adx_period=14)
df15 = df15.reset_index(drop=True)

# Load H1 for multi-timeframe
dfh1 = get_ohlc("GOLD", mt5.TIMEFRAME_H1, 500)
dfh1 = add_indicators(dfh1, ema_fast=10, ema_slow=30, rsi_period=14, atr_period=14, adx_period=14)
dfh1 = dfh1.reset_index(drop=True)

disconnect_mt5()

# Prepare M5 arrays
c = df5["close"].values; h = df5["high"].values; l = df5["low"].values
o = df5["open"].values
ef = df5["ema_fast"].values; es = df5["ema_slow"].values
rsi = df5["rsi"].values; adx = df5["adx"].values; atr = df5["atr"].values
pl = np.roll(l, 1); ph = np.roll(h, 1); pef = np.roll(ef, 1)
pl[0] = l[0]; ph[0] = h[0]; pef[0] = ef[0]
times5 = df5["time"].values
n = len(c)

# Time filter
hours_server = np.array([int(str(t)[11:13]) for t in times5])
ALLOWED_TH = [3, 4, 6, 8, 9, 12, 13, 15, 16, 21, 22, 23, 0]
ALLOWED_SERVER = set((th - 5) % 24 for th in ALLOWED_TH)

# Build M15 trend lookup: time -> (ema_fast > ema_slow = 1, else -1)
m15_trend = {}
for _, row in df15.iterrows():
    t = row["time"]
    if row["ema_fast"] > row["ema_slow"]:
        m15_trend[t] = 1
    else:
        m15_trend[t] = -1

# Build H1 trend lookup
h1_trend = {}
for _, row in dfh1.iterrows():
    t = row["time"]
    if row["ema_fast"] > row["ema_slow"]:
        h1_trend[t] = 1
    else:
        h1_trend[t] = -1

def get_m15_trend(m5_time):
    """Get M15 trend at M5 bar time."""
    import pandas as pd
    t = pd.Timestamp(m5_time)
    # Round down to nearest 15 min
    m15_t = t.floor("15min")
    return m15_trend.get(m15_t, 0)

def get_h1_trend(m5_time):
    """Get H1 trend at M5 bar time."""
    import pandas as pd
    t = pd.Timestamp(m5_time)
    h1_t = t.floor("h")
    return h1_trend.get(h1_t, 0)

sl_m, tp_m = 1.5, 1.2

def run_backtest(use_time=True, use_mtf_m15=False, use_mtf_h1=False,
                 use_engulfing=False, use_breakeven=False, be_trigger=0.5):
    """Run backtest with optional features."""
    wins = losses = 0
    net = 0.0
    i = 2
    while i < n:
        if adx[i] < 12:
            i += 1; continue

        # Time filter
        if use_time and hours_server[i] not in ALLOWED_SERVER:
            i += 1; continue

        sig = 0
        if c[i] > ef[i] > es[i] and rsi[i] > 50 and pl[i] <= pef[i]:
            sig = 1
        elif c[i] < ef[i] < es[i] and rsi[i] < 50 and ph[i] >= pef[i]:
            sig = -1
        if sig == 0:
            i += 1; continue

        # Multi-timeframe M15
        if use_mtf_m15:
            mt15 = get_m15_trend(times5[i])
            if mt15 != sig:  # M15 trend must agree
                i += 1; continue

        # Multi-timeframe H1
        if use_mtf_h1:
            mh1 = get_h1_trend(times5[i])
            if mh1 != sig:  # H1 trend must agree
                i += 1; continue

        # Engulfing candle filter
        if use_engulfing:
            body = abs(c[i] - o[i])
            candle_range = h[i] - l[i]
            if candle_range > 0:
                body_ratio = body / candle_range
                if body_ratio < 0.4:  # ต้องมี body ≥ 40% ของแท่ง
                    i += 1; continue

        ep = c[i]; a = atr[i]
        if sig == 1:
            sl_price = ep - a * sl_m; tp_price = ep + a * tp_m
        else:
            sl_price = ep + a * sl_m; tp_price = ep - a * tp_m

        # Simulate with optional breakeven
        j = i + 1
        result = ""
        be_activated = False

        while j < n:
            if use_breakeven and not be_activated:
                # Move SL to breakeven when price moves be_trigger * ATR in our favor
                if sig == 1 and h[j] >= ep + a * be_trigger:
                    sl_price = ep + 1  # breakeven + 1 pt
                    be_activated = True
                elif sig == -1 and l[j] <= ep - a * be_trigger:
                    sl_price = ep - 1
                    be_activated = True

            if sig == 1:
                if l[j] <= sl_price:
                    result = "LOSS" if not be_activated else "BE"
                    break
                if h[j] >= tp_price:
                    result = "WIN"; break
            else:
                if h[j] >= sl_price:
                    result = "LOSS" if not be_activated else "BE"
                    break
                if l[j] <= tp_price:
                    result = "WIN"; break
            j += 1
        else:
            result = "WIN" if ((c[-1] - ep) * sig > 0) else "LOSS"

        if result == "WIN":
            wins += 1; net += a * tp_m
        elif result == "BE":
            # breakeven = tiny profit/loss ~0
            net += (1 if sig == 1 else -1)
        else:
            losses += 1; net -= a * sl_m
        i = j + 1

    total = wins + losses
    wr = wins / total * 100 if total > 0 else 0
    pf = (wins * tp_m) / (losses * sl_m) if losses > 0 else 999
    return total, wins, losses, wr, pf, net


# ═══════════════════════════════════════════════════════════
# Run all combinations
# ═══════════════════════════════════════════════════════════
tests = [
    ("BASELINE (Time filter only)",
     dict(use_time=True)),

    ("+ M15 MTF Confirmation",
     dict(use_time=True, use_mtf_m15=True)),

    ("+ H1 MTF Confirmation",
     dict(use_time=True, use_mtf_h1=True)),

    ("+ M15 + H1 MTF (both)",
     dict(use_time=True, use_mtf_m15=True, use_mtf_h1=True)),

    ("+ Engulfing Filter (body≥40%)",
     dict(use_time=True, use_engulfing=True)),

    ("+ Breakeven (0.5x ATR)",
     dict(use_time=True, use_breakeven=True, be_trigger=0.5)),

    ("+ Breakeven (0.7x ATR)",
     dict(use_time=True, use_breakeven=True, be_trigger=0.7)),

    ("+ M15 MTF + Engulfing",
     dict(use_time=True, use_mtf_m15=True, use_engulfing=True)),

    ("+ M15 MTF + Breakeven 0.5",
     dict(use_time=True, use_mtf_m15=True, use_breakeven=True, be_trigger=0.5)),

    ("COMBO: M15 + Engulfing + BE 0.5",
     dict(use_time=True, use_mtf_m15=True, use_engulfing=True, use_breakeven=True, be_trigger=0.5)),
]

print("=" * 80)
print("  ADVANCED FEATURES BACKTEST — GOLD M5")
print("=" * 80)
print(f"{'Feature':42s} {'Trades':>6} {'Wins':>5} {'WR%':>6} {'PF':>6} {'Net':>8}")
print("-" * 80)

results = []
for name, kwargs in tests:
    total, wins, losses, wr, pf, net = run_backtest(**kwargs)
    results.append((name, total, wins, losses, wr, pf, net))
    marker = " ★" if wr > 65 else (" ✓" if wr > 63.8 else "")
    print(f"{name:42s} {total:>6} {wins:>5} {wr:>5.1f}% {pf:>6.2f} {net:>7.0f}{marker}")

print("-" * 80)
# Find best
best = max(results, key=lambda x: x[4])  # by WR
print(f"\n🏆 Best WR: {best[0]}")
print(f"   WR={best[4]:.1f}%, PF={best[5]:.2f}, Net={best[6]:.0f}")

best_pf = max(results, key=lambda x: x[5] if x[1] > 30 else 0)
print(f"\n💰 Best PF: {best_pf[0]}")
print(f"   WR={best_pf[4]:.1f}%, PF={best_pf[5]:.2f}, Net={best_pf[6]:.0f}")
