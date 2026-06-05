# ============================================================
# optimize_m5.py — หาค่าที่ดีที่สุดสำหรับ M5 Scalping
# ============================================================
#
#  ทดสอบ:
#    - EMA pairs: 9/21, 8/21, 5/13, 10/30
#    - SL: 0.5 ~ 1.5 × ATR
#    - TP: 0.5 ~ 2.0 × ATR
#    - ADX: 0, 12, 15, 18, 20
#
# ============================================================

import sys
import pandas as pd
from itertools import product

import MetaTrader5 as mt5
from mt5_data   import connect_mt5, disconnect_mt5, get_ohlc
from indicators import add_indicators
from backtester import BacktestResult, Trade


def _signal(curr, prev, adx_min=0):
    """Scalping signal: EMA crossover + RSI + pullback"""
    price    = curr["close"]
    ema_fast = curr["ema_fast"]
    ema_slow = curr["ema_slow"]
    rsi      = curr["rsi"]
    adx      = curr.get("adx", 99)

    if adx < adx_min:
        return None

    # BUY
    if price > ema_fast > ema_slow and rsi > 50:
        if prev["low"] <= prev["ema_fast"]:   # pullback
            return "BUY"
    # SELL
    if price < ema_fast < ema_slow and rsi < 50:
        if prev["high"] >= prev["ema_fast"]:  # pullback
            return "SELL"
    return None


def run_bt(df, sl_mult, tp_mult, adx_min=0):
    """Lightweight backtest"""
    result = BacktestResult(risk_per_trade=100.0)
    n = len(df)
    i = 2
    while i < n:
        curr = df.iloc[i]
        prev = df.iloc[i - 1]
        sig = _signal(curr, prev, adx_min=adx_min)
        if sig is None:
            i += 1
            continue

        atr = curr["atr"]
        ep = curr["close"]
        if sig == "BUY":
            sl = ep - atr * sl_mult
            tp = ep + atr * tp_mult
        else:
            sl = ep + atr * sl_mult
            tp = ep - atr * tp_mult

        trade = Trade(direction=sig, entry_time=curr["time"],
                      entry_price=ep, sl=sl, tp=tp)

        j = i + 1
        while j < n:
            bar = df.iloc[j]
            if sig == "BUY":
                if bar["low"] <= sl:
                    trade.exit_price = sl
                    trade.pnl = sl - ep
                    trade.result = "LOSS"
                    break
                if bar["high"] >= tp:
                    trade.exit_price = tp
                    trade.pnl = tp - ep
                    trade.result = "WIN"
                    break
            else:
                if bar["high"] >= sl:
                    trade.exit_price = sl
                    trade.pnl = ep - sl
                    trade.result = "LOSS"
                    break
                if bar["low"] <= tp:
                    trade.exit_price = tp
                    trade.pnl = ep - tp
                    trade.result = "WIN"
                    break
            j += 1
        else:
            last = df.iloc[-1]
            trade.exit_price = last["close"]
            trade.pnl = (last["close"] - ep) if sig == "BUY" else (ep - last["close"])
            trade.result = "WIN" if trade.pnl > 0 else "LOSS"

        trade.exit_time = df.iloc[min(j, n - 1)]["time"] if j < n else df.iloc[n - 1]["time"]
        result.trades.append(trade)
        i = j + 1

    return result


def main():
    if not connect_mt5():
        return

    print("=" * 75)
    print("  🔍 M5 SCALPING OPTIMIZATION — GOLD")
    print("=" * 75)

    # ── ดึง data M5 ──
    df_raw = get_ohlc("GOLD", mt5.TIMEFRAME_M5, 10000)
    if df_raw is None:
        print("ดึงข้อมูล M5 ไม่ได้")
        disconnect_mt5()
        return

    print(f"Data: {len(df_raw)} bars ({df_raw['time'].iloc[0]} → {df_raw['time'].iloc[-1]})")

    # ── EMA combinations ──
    ema_pairs = [(9, 21), (8, 21), (5, 13), (10, 30), (12, 26)]
    sl_opts = [0.5, 0.8, 1.0, 1.2, 1.5]
    tp_opts = [0.5, 0.6, 0.8, 1.0, 1.2, 1.5, 2.0]
    adx_opts = [0, 12, 15, 18, 20]

    all_results = []

    for ema_f, ema_s in ema_pairs:
        # คำนวณ indicator ใหม่สำหรับแต่ละ EMA pair
        df = add_indicators(df_raw.copy(), ema_fast=ema_f, ema_slow=ema_s,
                            rsi_period=14, atr_period=14, adx_period=14)

        for sl, tp in product(sl_opts, tp_opts):
            for adx_min in adx_opts:
                res = run_bt(df, sl, tp, adx_min=adx_min)
                if res.total_trades < 30:
                    continue

                all_results.append({
                    "ema": f"{ema_f}/{ema_s}",
                    "sl": sl, "tp": tp, "adx": adx_min,
                    "trades": res.total_trades,
                    "wr": res.win_rate,
                    "pf": res.profit_factor,
                    "net": res.net_pnl,
                    "dd": res.max_drawdown,
                    "cl": res.max_consecutive_losses,
                    "avg_win": res.avg_win,
                    "avg_loss": res.avg_loss,
                })

    print(f"\nTotal combos tested: {len(all_results)}")

    # ── TOP 15: Win Rate สูงสุด (PF ≥ 1.0, Trades ≥ 30) ──
    print()
    print("=" * 75)
    print("  🏆 TOP 15: Win Rate สูงสุด (PF ≥ 1.0, Trades ≥ 30)")
    print("=" * 75)

    qual = [r for r in all_results if r["pf"] >= 1.0 and r["trades"] >= 30]
    qual.sort(key=lambda x: (x["wr"], x["pf"]), reverse=True)

    print(f"{'#':>2} {'EMA':>6} {'SL':>4} {'TP':>4} {'ADX':>4} │ "
          f"{'Trd':>5} {'WR%':>6} {'PF':>6} {'Net':>8} {'AvgW':>6} "
          f"{'AvgL':>7} {'DD':>8} {'CL':>3}")
    print("─" * 75)

    for i, r in enumerate(qual[:15], 1):
        print(f"{i:>2} {r['ema']:>6} {r['sl']:>4.1f} {r['tp']:>4.1f} "
              f"{r['adx']:>4} │ {r['trades']:>5} {r['wr']:>5.1f}% "
              f"{r['pf']:>6.2f} {r['net']:>8.1f} {r['avg_win']:>6.1f} "
              f"{r['avg_loss']:>7.1f} {r['dd']:>8.1f} {r['cl']:>3}")

    # ── TOP 10 BALANCED: WR ≥ 55% + PF สูง + DD ต่ำ ──
    print()
    print("=" * 75)
    print("  ⚖️  TOP 10 BALANCED: WR ≥ 55% + PF ≥ 1.1 + Trades ≥ 50")
    print("=" * 75)

    bal = [r for r in all_results
           if r["wr"] >= 55 and r["pf"] >= 1.1 and r["trades"] >= 50]
    for r in bal:
        dd_s = (500 / r["dd"]) if r["dd"] > 0 else 10
        r["score"] = r["wr"] * 0.3 + r["pf"] * 20 + dd_s - r["cl"] * 0.5 + (r["net"] / 100)

    bal.sort(key=lambda x: x["score"], reverse=True)

    print(f"{'#':>2} {'EMA':>6} {'SL':>4} {'TP':>4} {'ADX':>4} │ "
          f"{'Trd':>5} {'WR%':>6} {'PF':>6} {'Net':>8} {'DD':>8} "
          f"{'CL':>3} {'Score':>6}")
    print("─" * 75)

    for i, r in enumerate(bal[:10], 1):
        print(f"{i:>2} {r['ema']:>6} {r['sl']:>4.1f} {r['tp']:>4.1f} "
              f"{r['adx']:>4} │ {r['trades']:>5} {r['wr']:>5.1f}% "
              f"{r['pf']:>6.2f} {r['net']:>8.1f} {r['dd']:>8.1f} "
              f"{r['cl']:>3} {r['score']:>6.1f}")

    # ── TOP 5: กำไรสูงสุด (WR ≥ 50%) ──
    print()
    print("=" * 75)
    print("  💰 TOP 5: Net กำไรสูงสุด (WR ≥ 50% + PF ≥ 1.0)")
    print("=" * 75)

    profit = [r for r in all_results if r["wr"] >= 50 and r["pf"] >= 1.0]
    profit.sort(key=lambda x: x["net"], reverse=True)

    print(f"{'#':>2} {'EMA':>6} {'SL':>4} {'TP':>4} {'ADX':>4} │ "
          f"{'Trd':>5} {'WR%':>6} {'PF':>6} {'Net':>8} {'DD':>8} {'CL':>3}")
    print("─" * 75)

    for i, r in enumerate(profit[:5], 1):
        print(f"{i:>2} {r['ema']:>6} {r['sl']:>4.1f} {r['tp']:>4.1f} "
              f"{r['adx']:>4} │ {r['trades']:>5} {r['wr']:>5.1f}% "
              f"{r['pf']:>6.2f} {r['net']:>8.1f} {r['dd']:>8.1f} {r['cl']:>3}")

    disconnect_mt5()


if __name__ == "__main__":
    main()
