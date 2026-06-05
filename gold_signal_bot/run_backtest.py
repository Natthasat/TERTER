# ============================================================
# run_backtest.py — Entry Point สำหรับรัน Backtest
# ============================================================
#
#  Usage:
#     python run_backtest.py
#
#  รันได้ 2 โหมด:
#     1. Backtest แบบมี filter (default)
#     2. เปรียบเทียบ กับ/ไม่มี filter
#
# ============================================================

import sys
import config
from mt5_data    import connect_mt5, disconnect_mt5, get_ohlc
from indicators  import add_indicators
from backtester  import run_backtest, print_report, trades_to_dataframe
from strategy    import FilterConfig


# ─── SETTINGS (ปรับได้ตามต้องการ) ────────────────────────────
SYMBOL          = config.SYMBOL            # "XAUUSD"
TIMEFRAME       = config.TIMEFRAME         # mt5.TIMEFRAME_M15
TIMEFRAME_LABEL = config.TIMEFRAME_LABEL   # "M15"
NUM_BARS        = 5000                     # แท่งย้อนหลัง (backtest ใช้มากกว่า live)

EMA_FAST        = config.EMA_FAST          # 20
EMA_SLOW        = config.EMA_SLOW          # 50
RSI_PERIOD      = config.RSI_PERIOD        # 14
ATR_PERIOD      = getattr(config, "ATR_PERIOD", 14)
ADX_PERIOD      = getattr(config, "ADX_PERIOD", 14)

ATR_SL_MULT     = getattr(config, 'ATR_SL_MULT', 1.5)   # SL = 1.5 × ATR
ATR_TP_MULT     = getattr(config, 'ATR_TP_MULT', 0.8)   # TP = 0.8 × ATR (WR 68%)
RISK_PER_TRADE  = 100.0   # $ ต่อไม้ (flat risk)

# ตั้งค่า true เพื่อเปรียบเทียบผลแบบ มี/ไม่มี filter
COMPARE_MODE    = True


def _fetch_data():
    """ดึงข้อมูลและคำนวณ indicator"""
    print(f"\n[Backtest] ดึงข้อมูล {SYMBOL} {TIMEFRAME_LABEL} "
          f"จำนวน {NUM_BARS} แท่ง …")

    df = get_ohlc(SYMBOL, TIMEFRAME, NUM_BARS)
    if df is None:
        print("[Backtest] ไม่สามารถดึงข้อมูลได้ — ยกเลิก")
        return None

    print(f"[Backtest] ได้ข้อมูล {len(df)} แท่ง "
          f"({df['time'].iloc[0]} → {df['time'].iloc[-1]})")

    df = add_indicators(
        df,
        ema_fast=EMA_FAST,
        ema_slow=EMA_SLOW,
        rsi_period=RSI_PERIOD,
        atr_period=ATR_PERIOD,
        adx_period=ADX_PERIOD,
    )
    print(f"[Backtest] Indicators พร้อม — {len(df)} แท่ง (หลังตัด NaN)")
    return df


def _run_and_report(df, fc, label: str) -> None:
    """รัน backtest แล้วแสดงรายงาน + export CSV"""
    result = run_backtest(
        df,
        atr_sl_mult=ATR_SL_MULT,
        atr_tp_mult=ATR_TP_MULT,
        risk_per_trade=RISK_PER_TRADE,
        filter_config=fc,
    )

    print_report(result, symbol=SYMBOL, tf_label=f"{TIMEFRAME_LABEL} [{label}]")

    if result.total_trades > 0:
        trades_df = trades_to_dataframe(result)
        csv_name = f"backtest_{SYMBOL}_{TIMEFRAME_LABEL}_{label}.csv"
        trades_df.to_csv(csv_name, index=False)
        print(f"[Backtest] Export trades → {csv_name}")

        print(f"\n── ตัวอย่าง 10 trades แรก ({label}) ──")
        print(trades_df.head(10).to_string(index=False))
        print()


def main() -> None:
    if not connect_mt5():
        sys.exit(1)

    try:
        df = _fetch_data()
        if df is None:
            return

        # ── สร้าง filter config จาก config.py ──
        fc_filtered = FilterConfig.from_config_module(config)
        fc_raw      = FilterConfig.disabled()

        if COMPARE_MODE:
            # เปรียบเทียบ 2 แบบ
            print("\n" + "━" * 60)
            print("  MODE: เปรียบเทียบ Raw vs Filtered")
            print("━" * 60)

            _run_and_report(df.copy(), fc_raw, "RAW")
            _run_and_report(df.copy(), fc_filtered, "FILTERED")

            print("━" * 60)
            print("  เปรียบเทียบ RAW กับ FILTERED ด้านบน")
            print("  ถ้า FILTERED มี PF สูงขึ้น + DD ต่ำลง = filter ใช้งานได้")
            print("━" * 60)
        else:
            _run_and_report(df, fc_filtered, "FILTERED")

    finally:
        disconnect_mt5()


if __name__ == "__main__":
    main()
