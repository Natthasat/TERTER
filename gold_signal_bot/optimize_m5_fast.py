# ============================================================
# optimize_m5_fast.py — M5 Scalping Quick Optimization
# ============================================================
# ใช้ numpy array แทน pandas.iloc เพื่อความเร็ว

import numpy as np
import MetaTrader5 as mt5
from mt5_data import connect_mt5, disconnect_mt5, get_ohlc
from indicators import add_indicators


def fast_backtest(closes, highs, lows, ema_f, ema_s, rsis, adxs, atrs,
                  prev_lows, prev_highs, prev_ema_f,
                  sl_mult, tp_mult, adx_min=0):
    """NumPy-based fast backtest"""
    n = len(closes)
    trades = 0
    wins = 0
    total_pnl = 0.0
    max_dd = 0.0
    cum_pnl = 0.0
    peak = 0.0
    consec_loss = 0
    max_consec_loss = 0
    win_pnls = []
    loss_pnls = []

    i = 2
    while i < n:
        price = closes[i]
        ef = ema_f[i]
        es = ema_s[i]
        rsi = rsis[i]
        adx = adxs[i]

        sig = 0  # 0=none, 1=BUY, -1=SELL
        if adx >= adx_min:
            if price > ef > es and rsi > 50 and prev_lows[i] <= prev_ema_f[i]:
                sig = 1
            elif price < ef < es and rsi < 50 and prev_highs[i] >= prev_ema_f[i]:
                sig = -1

        if sig == 0:
            i += 1
            continue

        atr = atrs[i]
        ep = price

        if sig == 1:
            sl = ep - atr * sl_mult
            tp = ep + atr * tp_mult
        else:
            sl = ep + atr * sl_mult
            tp = ep - atr * tp_mult

        j = i + 1
        pnl = 0.0
        result = ""
        while j < n:
            if sig == 1:
                if lows[j] <= sl:
                    pnl = sl - ep
                    result = "LOSS"
                    break
                if highs[j] >= tp:
                    pnl = tp - ep
                    result = "WIN"
                    break
            else:
                if highs[j] >= sl:
                    pnl = ep - sl
                    result = "LOSS"
                    break
                if lows[j] <= tp:
                    pnl = ep - tp
                    result = "WIN"
                    break
            j += 1
        else:
            pnl = (closes[-1] - ep) if sig == 1 else (ep - closes[-1])
            result = "WIN" if pnl > 0 else "LOSS"

        trades += 1
        total_pnl += pnl
        cum_pnl += pnl
        if cum_pnl > peak:
            peak = cum_pnl
        dd = peak - cum_pnl
        if dd > max_dd:
            max_dd = dd

        if result == "WIN":
            wins += 1
            consec_loss = 0
            win_pnls.append(pnl)
        else:
            consec_loss += 1
            if consec_loss > max_consec_loss:
                max_consec_loss = consec_loss
            loss_pnls.append(pnl)

        i = j + 1

    if trades == 0:
        return None

    wr = wins / trades * 100
    avg_w = np.mean(win_pnls) if win_pnls else 0
    avg_l = np.mean(loss_pnls) if loss_pnls else 0
    gross_p = sum(win_pnls)
    gross_l = abs(sum(loss_pnls))
    pf = gross_p / gross_l if gross_l > 0 else 999

    return {
        "trades": trades, "wins": wins, "wr": wr, "pf": pf,
        "net": total_pnl, "dd": max_dd, "cl": max_consec_loss,
        "avg_win": avg_w, "avg_loss": avg_l,
    }


def main():
    if not connect_mt5():
        return

    print("=" * 75)
    print("  🔍 M5 SCALPING FAST OPTIMIZATION — GOLD")
    print("=" * 75)

    df_raw = get_ohlc("GOLD", mt5.TIMEFRAME_M5, 5000)
    if df_raw is None:
        disconnect_mt5()
        return

    print(f"Data: {len(df_raw)} M5 bars ({df_raw['time'].iloc[0]} → {df_raw['time'].iloc[-1]})")

    ema_pairs = [(9, 21), (8, 21), (5, 13), (10, 30)]
    sl_opts = [0.5, 0.8, 1.0, 1.2, 1.5]
    tp_opts = [0.5, 0.6, 0.8, 1.0, 1.2, 1.5]
    adx_opts = [0, 12, 15, 20]

    all_results = []

    for ema_f_period, ema_s_period in ema_pairs:
        df = add_indicators(df_raw.copy(), ema_fast=ema_f_period,
                            ema_slow=ema_s_period,
                            rsi_period=14, atr_period=14, adx_period=14)
        df = df.reset_index(drop=True)

        # Prepare numpy arrays
        closes = df["close"].values
        highs = df["high"].values
        lows = df["low"].values
        ema_f = df["ema_fast"].values
        ema_s = df["ema_slow"].values
        rsis = df["rsi"].values
        adxs = df["adx"].values
        atrs = df["atr"].values

        # prev arrays (shift by 1)
        prev_lows = np.roll(lows, 1)
        prev_highs = np.roll(highs, 1)
        prev_ema_f = np.roll(ema_f, 1)
        prev_lows[0] = lows[0]
        prev_highs[0] = highs[0]
        prev_ema_f[0] = ema_f[0]

        for sl in sl_opts:
            for tp in tp_opts:
                for adx_min in adx_opts:
                    res = fast_backtest(closes, highs, lows, ema_f, ema_s,
                                        rsis, adxs, atrs,
                                        prev_lows, prev_highs, prev_ema_f,
                                        sl, tp, adx_min)
                    if res is None or res["trades"] < 30:
                        continue

                    res["ema"] = f"{ema_f_period}/{ema_s_period}"
                    res["sl"] = sl
                    res["tp"] = tp
                    res["adx"] = adx_min
                    all_results.append(res)

    print(f"\nTotal combos: {len(all_results)}")

    # ── TOP 15 Win Rate ──
    qual = [r for r in all_results if r["pf"] >= 1.0 and r["trades"] >= 30]
    qual.sort(key=lambda x: (x["wr"], x["pf"]), reverse=True)

    print()
    print("=" * 75)
    print("  🏆 TOP 15: Win Rate สูงสุด (PF ≥ 1.0)")
    print("=" * 75)
    print(f"{'#':>2} {'EMA':>6} {'SL':>4} {'TP':>4} {'ADX':>4} │ "
          f"{'Trd':>5} {'WR%':>6} {'PF':>6} {'Net':>8} {'AvgW':>6} "
          f"{'AvgL':>7} {'DD':>8} {'CL':>3}")
    print("─" * 75)
    for i, r in enumerate(qual[:15], 1):
        print(f"{i:>2} {r['ema']:>6} {r['sl']:>4.1f} {r['tp']:>4.1f} "
              f"{r['adx']:>4} │ {r['trades']:>5} {r['wr']:>5.1f}% "
              f"{r['pf']:>6.2f} {r['net']:>8.1f} {r['avg_win']:>6.1f} "
              f"{r['avg_loss']:>7.1f} {r['dd']:>8.1f} {r['cl']:>3}")

    # ── TOP 10 BALANCED ──
    bal = [r for r in all_results
           if r["wr"] >= 55 and r["pf"] >= 1.1 and r["trades"] >= 50]
    for r in bal:
        dd_s = (300 / r["dd"]) if r["dd"] > 0 else 10
        r["score"] = r["wr"] * 0.3 + r["pf"] * 20 + dd_s - r["cl"] * 0.5 + r["net"] / 100

    bal.sort(key=lambda x: x.get("score", 0), reverse=True)

    print()
    print("=" * 75)
    print("  ⚖️  TOP 10 BALANCED: WR≥55% + PF≥1.1 + Trades≥50")
    print("=" * 75)
    print(f"{'#':>2} {'EMA':>6} {'SL':>4} {'TP':>4} {'ADX':>4} │ "
          f"{'Trd':>5} {'WR%':>6} {'PF':>6} {'Net':>8} {'DD':>8} "
          f"{'CL':>3} {'Score':>6}")
    print("─" * 75)
    for i, r in enumerate(bal[:10], 1):
        print(f"{i:>2} {r['ema']:>6} {r['sl']:>4.1f} {r['tp']:>4.1f} "
              f"{r['adx']:>4} │ {r['trades']:>5} {r['wr']:>5.1f}% "
              f"{r['pf']:>6.2f} {r['net']:>8.1f} {r['dd']:>8.1f} "
              f"{r['cl']:>3} {r['score']:>6.1f}")

    # ── Best overall recommendation ──
    if bal:
        best = bal[0]
        print()
        print("=" * 75)
        print(f"  ✅ RECOMMENDED M5 SETTING:")
        print(f"     EMA: {best['ema']}  SL: {best['sl']}×ATR  TP: {best['tp']}×ATR  ADX≥{best['adx']}")
        print(f"     WR: {best['wr']:.1f}%  PF: {best['pf']:.2f}  Net: {best['net']:.0f} pts  DD: {best['dd']:.0f} pts  ConsLoss: {best['cl']}")
        print("=" * 75)

    disconnect_mt5()


if __name__ == "__main__":
    main()
