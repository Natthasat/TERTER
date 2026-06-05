# ============================================================
# test_now.py — ทดสอบ signal ทันที (ไม่รอแท่งปิด / ไม่ส่ง Telegram)
# ============================================================

import config
from datetime import datetime, timezone, timedelta
from mt5_data   import connect_mt5, disconnect_mt5, get_ohlc
from indicators import add_indicators
from strategy   import evaluate_signal, FilterConfig, check_mtf_trend
from chart      import create_signal_chart


def main() -> None:
    if not connect_mt5():
        return

    try:
        # 1) ดึงข้อมูล
        df = get_ohlc(config.SYMBOL, config.TIMEFRAME, config.NUM_BARS)
        if df is None:
            return

        print(f"[Data] {config.SYMBOL} {config.TIMEFRAME_LABEL} — "
              f"{len(df)} bars ({df['time'].iloc[0]} → {df['time'].iloc[-1]})")

        # 2) คำนวณ Indicator
        df = add_indicators(
            df,
            ema_fast=config.EMA_FAST,
            ema_slow=config.EMA_SLOW,
            rsi_period=config.RSI_PERIOD,
            atr_period=getattr(config, "ATR_PERIOD", 14),
            adx_period=getattr(config, "ADX_PERIOD", 14),
        )

        # 3) แสดงค่าปัจจุบัน
        last = df.iloc[-1]
        print(f"\n── แท่งล่าสุด ──")
        print(f"  Time   : {last['time']}")
        print(f"  Close  : {last['close']:.2f}")
        print(f"  EMA{config.EMA_FAST:<3}: {last['ema_fast']:.2f}")
        print(f"  EMA{config.EMA_SLOW:<3}: {last['ema_slow']:.2f}")
        print(f"  RSI    : {last['rsi']:.1f}")
        print(f"  ADX    : {last['adx']:.1f}")
        print(f"  ATR    : {last['atr']:.2f}")

        # Trend status
        if last['close'] > last['ema_fast'] > last['ema_slow']:
            trend = "UPTREND ↑"
        elif last['close'] < last['ema_fast'] < last['ema_slow']:
            trend = "DOWNTREND ↓"
        else:
            trend = "MIXED / SIDEWAY ─"
        print(f"  Trend  : {trend}")

        # Time Filter check
        if getattr(config, "USE_TIME_FILTER", False):
            thai_now = datetime.now(timezone.utc) + timedelta(hours=7)
            thai_hour = thai_now.hour
            allowed = getattr(config, "ALLOWED_HOURS_TH", list(range(24)))
            in_window = thai_hour in allowed
            print(f"\n── Time Filter ──")
            print(f"  เวลาไทย : {thai_now:%H:%M}")
            print(f"  Hour     : {thai_hour}")
            print(f"  Status   : {'✅ ALLOWED' if in_window else '❌ BLOCKED (ช่วง WR ต่ำ)'}")
        else:
            in_window = True
            print(f"\n── Time Filter: OFF ──")

        # 4) MTF Confirmation
        df_mtf = None
        mtf_label = "—"
        if getattr(config, "USE_MTF_CONFIRMATION", False):
            df_mtf = get_ohlc(
                config.SYMBOL, config.MTF_TIMEFRAME,
                getattr(config, "MTF_NUM_BARS", 100),
            )
            if df_mtf is not None:
                df_mtf = add_indicators(
                    df_mtf,
                    ema_fast=getattr(config, "MTF_EMA_FAST", 10),
                    ema_slow=getattr(config, "MTF_EMA_SLOW", 30),
                    rsi_period=config.RSI_PERIOD,
                    atr_period=getattr(config, "ATR_PERIOD", 14),
                    adx_period=getattr(config, "ADX_PERIOD", 14),
                )
                mt = check_mtf_trend(df_mtf)
                mtf_label = mt if mt else "SIDEWAY"
            print(f"\n── MTF {config.MTF_TIMEFRAME_LABEL} ──")
            print(f"  Trend  : {mtf_label}")
            if df_mtf is not None:
                m_last = df_mtf.iloc[-1]
                print(f"  EMA{config.MTF_EMA_FAST}/{config.MTF_EMA_SLOW}: {m_last['ema_fast']:.2f} / {m_last['ema_slow']:.2f}")

        # 5) ประเมินสัญญาณ
        fc = FilterConfig.from_config_module(config)
        signal, reason = evaluate_signal(df, filters=fc, df_mtf=df_mtf)

        print(f"\n── Signal ──")
        if signal:
            atr = last["atr"]
            sl_dist  = atr * config.ATR_SL_MULT
            tp1_dist = atr * getattr(config, "ATR_TP1_MULT", 1.0)
            tp2_dist = atr * getattr(config, "ATR_TP2_MULT", 1.5)
            tp3_dist = atr * getattr(config, "ATR_TP3_MULT", 2.0)
            if signal == "BUY":
                sl  = last["close"] - sl_dist
                tp1 = last["close"] + tp1_dist
                tp2 = last["close"] + tp2_dist
                tp3 = last["close"] + tp3_dist
            else:
                sl  = last["close"] + sl_dist
                tp1 = last["close"] - tp1_dist
                tp2 = last["close"] - tp2_dist
                tp3 = last["close"] - tp3_dist

            print(f"\n  XAUUSD {signal} {last['close']:.0f}")
            print(f"  \u26b0\ufe0f SL (Stop Loss): {sl:.0f}")
            print(f"  \U0001f5e1\ufe0f TP1 (Take Profit): {tp1:.0f}")
            print(f"  \U0001f5e1\ufe0f TP2 (Take Profit): {tp2:.0f}")
            print(f"  \U0001f5e1\ufe0f TP3 (Take Profit): {tp3:.0f}")

            # สร้างกราฟ
            chart_path = create_signal_chart(
                df, signal, config.SYMBOL,
                config.TIMEFRAME_LABEL, "test_chart.png",
            )
            print(f"\n  กราฟ  : {chart_path}")
        elif reason:
            print(f"  ⚠️  Raw signal มี แต่ถูก block โดย: {reason}")
        else:
            print(f"  — ไม่มี signal ในแท่งนี้")

        # 5) ดูย้อนหลัง 5 แท่ง
        print(f"\n── ย้อนหลัง 5 แท่ง ──")
        fc_check = FilterConfig.from_config_module(config)
        for i in range(-5, 0):
            sub = df.iloc[:len(df)+i+1].copy()
            sig, rsn = evaluate_signal(sub, filters=fc_check)
            bar = df.iloc[i]
            status = sig if sig else (f"blocked:{rsn}" if rsn else "—")
            print(f"  {bar['time']}  close={bar['close']:.2f}  "
                  f"rsi={bar['rsi']:.1f}  adx={bar['adx']:.1f}  → {status}")

    finally:
        disconnect_mt5()


if __name__ == "__main__":
    main()
