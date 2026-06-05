# ============================================================
# main.py — Gold Signal Bot (XAUUSD)
# วิเคราะห์สัญญาณ + แจ้งเตือน Telegram
# ไม่เปิดออเดอร์ — analysis & alert เท่านั้น
# ============================================================

import time
from datetime import datetime, timezone, timedelta

import config
from mt5_data   import connect_mt5, disconnect_mt5, get_ohlc
from indicators import add_indicators
from strategy   import evaluate_signal, FilterConfig
from chart      import create_signal_chart
from notifier   import broadcast_text, broadcast_image
from trade_log  import log_trade, update_results


# ─── ตัวแปรกันสัญญาณซ้ำ ─────────────────────────────────────
_last_signal_time: datetime | None = None   # เวลาแท่งที่ส่ง signal ล่าสุด


def wait_for_bar_close(timeframe_seconds: int) -> None:
    """รอจนกว่าแท่งปัจจุบันจะปิด (คำนวณจาก timeframe เป็นวินาที)"""
    now = time.time()
    seconds_to_next = timeframe_seconds - (now % timeframe_seconds)
    wait = seconds_to_next + 2          # +2 วินาที buffer ให้แท่งปิดสนิท
    next_bar = datetime.fromtimestamp(now + seconds_to_next, tz=timezone.utc)
    print(f"[Wait] แท่งถัดไปปิดเวลา {next_bar:%Y-%m-%d %H:%M} UTC "
          f"— รอ {wait:.0f} วินาที …")
    time.sleep(wait)


def get_timeframe_seconds(tf_label: str) -> int:
    """แปลง timeframe label → จำนวนวินาที"""
    mapping = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800,
               "H1": 3600, "H4": 14400, "D1": 86400}
    return mapping.get(tf_label, 900)


def build_message(signal: str, df) -> str:
    """สร้างข้อความแจ้งเตือน พร้อม SL/TP1-TP3 แนะนำ"""
    last = df.iloc[-1]
    atr = last["atr"]
    price = last["close"]

    sl_dist  = atr * config.ATR_SL_MULT
    tp1_dist = atr * getattr(config, "ATR_TP1_MULT", 1.0)
    tp2_dist = atr * getattr(config, "ATR_TP2_MULT", 1.5)
    tp3_dist = atr * getattr(config, "ATR_TP3_MULT", 2.0)

    if signal == "BUY":
        sl  = price - sl_dist
        tp1 = price + tp1_dist
        tp2 = price + tp2_dist
        tp3 = price + tp3_dist
    else:
        sl  = price + sl_dist
        tp1 = price - tp1_dist
        tp2 = price - tp2_dist
        tp3 = price - tp3_dist

    # Direction icon
    if signal == "BUY":
        dir_icon = "🟢🟢🟢"
    else:
        dir_icon = "🔴🔴🔴"

    return (
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"  {dir_icon} {signal} GOLD 📍 {price:.0f}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"✅ เข้าได้เลย!\n"
        f"   ผ่านทุกเงื่อนไข\n"
        f"\n"
        f"🛑 SL   : {sl:.0f}  ({abs(price - sl):.0f} pts)\n"
        f"🎯 TP1  : {tp1:.0f}  ({abs(tp1 - price):.0f} pts)\n"
        f"🎯 TP2  : {tp2:.0f}  ({abs(tp2 - price):.0f} pts)\n"
        f"🎯 TP3  : {tp3:.0f}  ({abs(tp3 - price):.0f} pts)\n"
        f"\n"
        f"📊 RSI {last['rsi']:.1f} | ADX {last['adx']:.1f} | ATR {atr:.2f}\n"
        f"⏰ {last['time']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━"
    )


# ─── Main Loop ──────────────────────────────────────────────
def run() -> None:
    global _last_signal_time

    if not connect_mt5():
        return

    tf_sec = get_timeframe_seconds(config.TIMEFRAME_LABEL)
    fc = FilterConfig.from_config_module(config)

    print(f"[Bot] เริ่มทำงาน — {config.SYMBOL} {config.TIMEFRAME_LABEL}")
    print(f"[Bot] Filters: session={fc.use_session_filter} "
          f"adx={fc.use_adx_filter} body={fc.use_body_filter} "
          f"anti-chase={fc.use_anti_chase} vol-guard={fc.use_volatility_guard}")
    if getattr(config, "USE_MTF_CONFIRMATION", False):
        print(f"[Bot] MTF Confirmation: ON — {config.MTF_TIMEFRAME_LABEL} EMA{config.MTF_EMA_FAST}/{config.MTF_EMA_SLOW}")
    else:
        print(f"[Bot] MTF Confirmation: OFF")
    if getattr(config, "USE_TIME_FILTER", False):
        print(f"[Bot] Time Filter: ON — allowed hours (TH): {config.ALLOWED_HOURS_TH}")
    else:
        print(f"[Bot] Time Filter: OFF — trade all hours")
    print("=" * 50)

    try:
        while True:
            # 1) รอแท่งปิด
            wait_for_bar_close(tf_sec)

            # 2) ดึงข้อมูล OHLC
            df = get_ohlc(config.SYMBOL, config.TIMEFRAME, config.NUM_BARS)
            if df is None:
                continue

            # 3) คำนวณ Indicator
            df = add_indicators(
                df,
                ema_fast=config.EMA_FAST,
                ema_slow=config.EMA_SLOW,
                rsi_period=config.RSI_PERIOD,
                atr_period=getattr(config, "ATR_PERIOD", 14),
                adx_period=getattr(config, "ADX_PERIOD", 14),
            )

            # 4) Time Filter — เช็คว่าช่วงเวลานี้ WR ดีพอมั้ย
            if getattr(config, "USE_TIME_FILTER", False):
                thai_now = datetime.now(timezone.utc) + timedelta(hours=7)
                thai_hour = thai_now.hour
                allowed = getattr(config, "ALLOWED_HOURS_TH", list(range(24)))
                if thai_hour not in allowed:
                    print(f"[{thai_now:%H:%M} TH] Time filter: hour {thai_hour} not in allowed list — skip")
                    continue

            # 4.5) MTF Confirmation — ดึง M15 data
            df_mtf = None
            if getattr(config, "USE_MTF_CONFIRMATION", False):
                df_mtf = get_ohlc(
                    config.SYMBOL,
                    config.MTF_TIMEFRAME,
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

            # 5) ประเมินสัญญาณ (พร้อม Gold filters + MTF)
            signal, filter_reason = evaluate_signal(df, filters=fc, df_mtf=df_mtf)
            bar_time = df.iloc[-1]["time"]

            if filter_reason:
                print(f"[{bar_time}] raw signal blocked by {filter_reason}")
            else:
                print(f"[{bar_time}] signal = {signal}")

            # 6) กันซ้ำ — ถ้าแท่งเดิมเคยส่งแล้ว ข้าม
            if signal and bar_time == _last_signal_time:
                print("[Skip] สัญญาณซ้ำในแท่งเดียวกัน")
                continue

            # 7) ส่ง Telegram เมื่อมี signal
            if signal:
                _last_signal_time = bar_time

                msg = build_message(signal, df)
                broadcast_text(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_IDS, msg)

                # บันทึก Trade Log
                last = df.iloc[-1]
                atr = last["atr"]
                p = last["close"]
                sl_d  = atr * config.ATR_SL_MULT
                tp1_d = atr * getattr(config, "ATR_TP1_MULT", 1.0)
                tp2_d = atr * getattr(config, "ATR_TP2_MULT", 1.5)
                tp3_d = atr * getattr(config, "ATR_TP3_MULT", 2.0)
                if signal == "BUY":
                    log_trade(signal, p, p - sl_d, p + tp1_d, p + tp2_d, p + tp3_d, str(bar_time))
                else:
                    log_trade(signal, p, p + sl_d, p - tp1_d, p - tp2_d, p - tp3_d, str(bar_time))

            # 8) อัปเดตผลเทรดที่ยัง OPEN
            update_results(get_ohlc, config.SYMBOL, config.TIMEFRAME)

    except KeyboardInterrupt:
        print("\n[Bot] หยุดทำงาน")
    finally:
        disconnect_mt5()


# ─── Entry Point ─────────────────────────────────────────────
if __name__ == "__main__":
    run()
