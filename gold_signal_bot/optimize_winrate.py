# ============================================================
# optimize_winrate.py — หา Setting ที่ Win Rate สูงสุด (~60%)
# ============================================================
#
#  ทดสอบ 3 แนวทาง:
#    1. ปรับ SL/TP ให้ TP ใกล้ขึ้น (ชนง่ายขึ้น = WR สูงขึ้น)
#    2. เพิ่ม RSI Filter เข้มขึ้น (เข้าเฉพาะจุดที่ RSI สุดขีด)
#    3. เพิ่ม Trend Strength Filter (ADX สูงขึ้น = trend ชัดกว่า)
#    4. ลด SL ให้น้อยลง (ขาดทุนต่อไม้น้อยลง)
#
# ============================================================

import sys
import pandas as pd
from itertools import product

import config
from mt5_data    import connect_mt5, disconnect_mt5, get_ohlc
from indicators  import add_indicators
from backtester  import BacktestResult, Trade
from strategy    import FilterConfig
from filters     import apply_all_filters


# ─── Enhanced backtest with flexible signal logic ────────────
def _enhanced_signal(curr, prev, rsi_buy_min=50, rsi_sell_max=50,
                     adx_min=0, require_pullback=True):
    """Signal ที่ปรับ RSI / ADX / pullback ได้"""
    price    = curr["close"]
    ema_fast = curr["ema_fast"]
    ema_slow = curr["ema_slow"]
    rsi      = curr["rsi"]
    adx      = curr.get("adx", 99)

    # ADX filter
    if adx < adx_min:
        return None

    # BUY
    if price > ema_fast > ema_slow and rsi > rsi_buy_min:
        if require_pullback and prev["low"] > prev["ema_fast"]:
            return None  # ไม่มี pullback
        return "BUY"

    # SELL
    if price < ema_fast < ema_slow and rsi < rsi_sell_max:
        if require_pullback and prev["high"] < prev["ema_fast"]:
            return None
        return "SELL"

    return None


def run_enhanced_backtest(df, atr_sl_mult, atr_tp_mult,
                          rsi_buy_min=50, rsi_sell_max=50,
                          adx_min=0, require_pullback=True,
                          use_trailing_sl=False):
    """Backtest ที่ปรับ parameter ได้หลากหลาย"""
    result = BacktestResult(risk_per_trade=100.0)
    n = len(df)
    i = 2

    while i < n:
        curr = df.iloc[i]
        prev = df.iloc[i - 1]

        signal = _enhanced_signal(curr, prev,
                                  rsi_buy_min=rsi_buy_min,
                                  rsi_sell_max=rsi_sell_max,
                                  adx_min=adx_min,
                                  require_pullback=require_pullback)

        if signal is None:
            i += 1
            continue

        atr = curr["atr"]
        entry_price = curr["close"]

        if signal == "BUY":
            sl = entry_price - atr * atr_sl_mult
            tp = entry_price + atr * atr_tp_mult
        else:
            sl = entry_price + atr * atr_sl_mult
            tp = entry_price - atr * atr_tp_mult

        trade = Trade(direction=signal, entry_time=curr["time"],
                      entry_price=entry_price, sl=sl, tp=tp)

        # trailing SL: ขยับ SL ตาม high/low ของแท่งก่อน
        trailing_sl = sl

        j = i + 1
        while j < n:
            bar = df.iloc[j]

            if use_trailing_sl and j > i + 1:
                prev_bar = df.iloc[j - 1]
                if signal == "BUY":
                    new_sl = prev_bar["low"] - atr * 0.3
                    trailing_sl = max(trailing_sl, new_sl)
                else:
                    new_sl = prev_bar["high"] + atr * 0.3
                    trailing_sl = min(trailing_sl, new_sl)

            active_sl = trailing_sl if use_trailing_sl else sl

            if signal == "BUY":
                if bar["low"] <= active_sl:
                    trade.exit_price = active_sl
                    trade.pnl = active_sl - entry_price
                    trade.result = "LOSS" if trade.pnl < 0 else "WIN"
                    break
                if bar["high"] >= tp:
                    trade.exit_price = tp
                    trade.pnl = tp - entry_price
                    trade.result = "WIN"
                    break
            else:
                if bar["high"] >= active_sl:
                    trade.exit_price = active_sl
                    trade.pnl = entry_price - active_sl
                    trade.result = "LOSS" if trade.pnl < 0 else "WIN"
                    break
                if bar["low"] <= tp:
                    trade.exit_price = tp
                    trade.pnl = entry_price - tp
                    trade.result = "WIN"
                    break

            j += 1
        else:
            # ไม่ชน SL/TP จนหมด data — ปิด ณ ราคาปิดสุดท้าย
            last = df.iloc[-1]
            trade.exit_price = last["close"]
            if signal == "BUY":
                trade.pnl = last["close"] - entry_price
            else:
                trade.pnl = entry_price - last["close"]
            trade.result = "WIN" if trade.pnl > 0 else "LOSS"

        trade.exit_time = df.iloc[min(j, n - 1)]["time"] if j < n else df.iloc[n - 1]["time"]
        result.trades.append(trade)
        i = j + 1

    return result


# ─── Main Optimization ──────────────────────────────────────
def main():
    if not connect_mt5():
        return

    print("=" * 70)
    print("  🔍 OPTIMIZATION: หา Win Rate 60%+ พร้อม SL ต่ำ")
    print("=" * 70)

    # ดึงข้อมูล
    df = get_ohlc(config.SYMBOL, config.TIMEFRAME, 5000)
    if df is None:
        print("ไม่สามารถดึงข้อมูลได้")
        disconnect_mt5()
        return

    df = add_indicators(df,
                        ema_fast=config.EMA_FAST,
                        ema_slow=config.EMA_SLOW,
                        rsi_period=config.RSI_PERIOD,
                        atr_period=14,
                        adx_period=14)

    print(f"Data: {len(df)} bars ({df['time'].iloc[0]} → {df['time'].iloc[-1]})")
    print()

    # ── ตัวแปรที่ทดสอบ ──
    sl_options = [0.5, 0.8, 1.0, 1.2, 1.5]
    tp_options = [0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0]
    rsi_buy_options = [50, 55]          # RSI ≥ X ถึงจะ BUY
    rsi_sell_options = [50, 45]         # RSI ≤ X ถึงจะ SELL
    adx_options = [0, 15, 20, 25]      # ADX ≥ X
    pullback_options = [True, False]
    trailing_options = [False, True]

    # ── Phase 1: ทดสอบ SL/TP ก่อน (กับ ADX=15 + Pullback) ──
    print("─" * 70)
    print("  Phase 1: Grid SL × TP  (ADX≥15, RSI basic, Pullback=ON)")
    print("─" * 70)
    print(f"{'SL':>5} {'TP':>5} │ {'Trades':>6} {'WR%':>6} {'PF':>6} "
          f"{'AvgWin':>8} {'AvgLoss':>8} {'Net':>8} {'MaxDD':>8} {'ConsL':>5}")

    phase1_results = []
    for sl, tp in product(sl_options, tp_options):
        if tp <= sl * 0.5:  # TP ต้องอย่างน้อย 50% ของ SL
            continue
        res = run_enhanced_backtest(df, sl, tp,
                                    rsi_buy_min=50, rsi_sell_max=50,
                                    adx_min=15, require_pullback=True)
        if res.total_trades < 20:
            continue

        phase1_results.append({
            "sl": sl, "tp": tp, "trades": res.total_trades,
            "wr": res.win_rate, "pf": res.profit_factor,
            "avg_win": res.avg_win, "avg_loss": res.avg_loss,
            "net": res.net_pnl, "dd": res.max_drawdown,
            "cons_loss": res.max_consecutive_losses,
        })

        flag = " ★" if res.win_rate >= 55 and res.profit_factor >= 1.0 else ""
        print(f"{sl:>5.1f} {tp:>5.1f} │ {res.total_trades:>6} "
              f"{res.win_rate:>5.1f}% {res.profit_factor:>6.2f} "
              f"{res.avg_win:>8.1f} {res.avg_loss:>8.1f} "
              f"{res.net_pnl:>8.1f} {res.max_drawdown:>8.1f} "
              f"{res.max_consecutive_losses:>5}{flag}")

    # ── Phase 2: ทดสอบ RSI เข้มขึ้น + ADX สูงขึ้น + Trailing SL ──
    print()
    print("─" * 70)
    print("  Phase 2: Top SL/TP + RSI เข้ม + ADX สูง + Trailing SL")
    print("─" * 70)

    # หา Top 5 SL/TP จาก Phase 1 ที่ WR ≥ 50%
    good_sltp = [(r["sl"], r["tp"]) for r in phase1_results if r["wr"] >= 50]
    if not good_sltp:
        good_sltp = [(0.8, 0.8), (1.0, 0.8), (1.0, 1.0)]
    # จำกัดไม่เกิน 8 คู่
    good_sltp = good_sltp[:8]

    print(f"{'SL':>5} {'TP':>5} {'RSIb':>5} {'RSIs':>5} {'ADX':>4} "
          f"{'TRL':>4} │ {'Trd':>4} {'WR%':>6} {'PF':>6} "
          f"{'Net':>8} {'DD':>8} {'CL':>3}")

    all_results = []
    for sl, tp in good_sltp:
        for rsi_b, rsi_s in zip(rsi_buy_options, rsi_sell_options):
            for adx_min in adx_options:
                for trail in trailing_options:
                    res = run_enhanced_backtest(
                        df, sl, tp,
                        rsi_buy_min=rsi_b, rsi_sell_max=rsi_s,
                        adx_min=adx_min, require_pullback=True,
                        use_trailing_sl=trail)

                    if res.total_trades < 15:
                        continue

                    row = {
                        "sl": sl, "tp": tp,
                        "rsi_buy": rsi_b, "rsi_sell": rsi_s,
                        "adx_min": adx_min, "pullback": True,
                        "trailing": trail,
                        "trades": res.total_trades,
                        "wr": res.win_rate,
                        "pf": res.profit_factor,
                        "net": res.net_pnl,
                        "dd": res.max_drawdown,
                        "cons_loss": res.max_consecutive_losses,
                        "avg_win": res.avg_win,
                        "avg_loss": res.avg_loss,
                    }
                    all_results.append(row)

                    if res.win_rate >= 55 and res.profit_factor >= 1.0:
                        tr_str = "Y" if trail else "N"
                        print(f"{sl:>5.1f} {tp:>5.1f} {rsi_b:>5} "
                              f"{rsi_s:>5} {adx_min:>4} "
                              f"{tr_str:>4} │ {res.total_trades:>4} "
                              f"{res.win_rate:>5.1f}% {res.profit_factor:>6.2f} "
                              f"{res.net_pnl:>8.1f} {res.max_drawdown:>8.1f} "
                              f"{res.max_consecutive_losses:>3}")

    # ── สรุป Top 10 (เรียงตาม WR แล้ว PF) ──
    print()
    print("=" * 70)
    print("  🏆 TOP 10: Win Rate สูงสุด (ที่ PF ≥ 1.0 + Trades ≥ 20)")
    print("=" * 70)

    # กรอง PF ≥ 1.0 และ trades ≥ 20
    qualified = [r for r in all_results if r["pf"] >= 1.0 and r["trades"] >= 20]
    qualified.sort(key=lambda x: (x["wr"], x["pf"]), reverse=True)
    top10 = qualified[:10]

    print(f"{'#':>2} {'SL':>4} {'TP':>4} {'RSI':>5} {'ADX':>4} "
          f"{'PB':>3} {'TRL':>4} │ {'Trd':>4} {'WR%':>6} {'PF':>6} "
          f"{'Net':>8} {'AvgW':>7} {'AvgL':>7} {'DD':>8} {'CL':>3}")
    print("─" * 70)

    for i, r in enumerate(top10, 1):
        pb_str = "Y" if r["pullback"] else "N"
        tr_str = "Y" if r["trailing"] else "N"
        rsi_str = f"{r['rsi_buy']}/{r['rsi_sell']}"

        print(f"{i:>2} {r['sl']:>4.1f} {r['tp']:>4.1f} {rsi_str:>5} "
              f"{r['adx_min']:>4} {pb_str:>3} {tr_str:>4} │ "
              f"{r['trades']:>4} {r['wr']:>5.1f}% {r['pf']:>6.2f} "
              f"{r['net']:>8.1f} {r['avg_win']:>7.1f} {r['avg_loss']:>7.1f} "
              f"{r['dd']:>8.1f} {r['cons_loss']:>3}")

    # ── สรุป Top 5 ที่ Balance ดีสุด (WR ≥ 50% + PF สูง + DD ต่ำ) ──
    print()
    print("=" * 70)
    print("  ⚖️  TOP 5 BALANCED: WR ≥ 50% + PF สูง + DD ต่ำ")
    print("=" * 70)

    balanced = [r for r in all_results
                if r["wr"] >= 50 and r["pf"] >= 1.0 and r["trades"] >= 20]
    # Score = WR*0.3 + PF*20 + (1/DD)*500 - cons_loss*0.5
    for r in balanced:
        dd_score = (500 / r["dd"]) if r["dd"] > 0 else 10
        r["score"] = r["wr"] * 0.3 + r["pf"] * 20 + dd_score - r["cons_loss"] * 0.5

    balanced.sort(key=lambda x: x["score"], reverse=True)
    top5 = balanced[:5]

    print(f"{'#':>2} {'SL':>4} {'TP':>4} {'RSI':>5} {'ADX':>4} "
          f"{'PB':>3} {'TRL':>4} │ {'Trd':>4} {'WR%':>6} {'PF':>6} "
          f"{'Net':>8} {'DD':>8} {'CL':>3} {'Score':>6}")
    print("─" * 70)

    for i, r in enumerate(top5, 1):
        pb_str = "Y" if r["pullback"] else "N"
        tr_str = "Y" if r["trailing"] else "N"
        rsi_str = f"{r['rsi_buy']}/{r['rsi_sell']}"

        print(f"{i:>2} {r['sl']:>4.1f} {r['tp']:>4.1f} {rsi_str:>5} "
              f"{r['adx_min']:>4} {pb_str:>3} {tr_str:>4} │ "
              f"{r['trades']:>4} {r['wr']:>5.1f}% {r['pf']:>6.2f} "
              f"{r['net']:>8.1f} {r['dd']:>8.1f} {r['cons_loss']:>3} "
              f"{r['score']:>6.1f}")

    print()
    print(f"  Total combinations tested: {len(all_results)}")

    disconnect_mt5()


if __name__ == "__main__":
    main()
