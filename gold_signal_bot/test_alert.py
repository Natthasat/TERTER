"""Test alert with Time Filter status."""
import sys; sys.path.insert(0, '.')
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5
import config
from mt5_data import connect_mt5, disconnect_mt5, get_ohlc
from indicators import add_indicators
from strategy import evaluate_signal, FilterConfig
from notifier import broadcast_text

connect_mt5()
df = get_ohlc(config.SYMBOL, config.TIMEFRAME, config.NUM_BARS)
df = add_indicators(df, ema_fast=config.EMA_FAST, ema_slow=config.EMA_SLOW,
                    rsi_period=config.RSI_PERIOD, atr_period=14, adx_period=14)

last = df.iloc[-1]

# Time filter check
thai_now = datetime.now(timezone.utc) + timedelta(hours=7)
thai_hour = thai_now.hour
in_window = thai_hour in config.ALLOWED_HOURS_TH
time_status = "✅ ALLOWED" if in_window else "❌ BLOCKED"

# Trend
if last["close"] > last["ema_fast"] > last["ema_slow"]:
    trend = "UPTREND ↑"
elif last["close"] < last["ema_fast"] < last["ema_slow"]:
    trend = "DOWNTREND ↓"
else:
    trend = "SIDEWAY ─"

# Signal
fc = FilterConfig.from_config_module(config)
signal, reason = evaluate_signal(df, filters=fc)

atr_val = last["atr"]
sl_d = atr_val * config.ATR_SL_MULT
tp_d = atr_val * config.ATR_TP_MULT

if signal == "BUY":
    sl = last["close"] - sl_d
    tp = last["close"] + tp_d
elif signal == "SELL":
    sl = last["close"] + sl_d
    tp = last["close"] - tp_d
else:
    sl = tp = 0

sig_icon = "🟢 BUY" if signal == "BUY" else ("🔴 SELL" if signal == "SELL" else "⚪ NO SIGNAL")
block_text = f" (blocked: {reason})" if reason else ""

lines = [
    "━━━━━━━━━━━━━━━━━━━━━━",
    "🏆 GOLD M5 Scalping Test",
    "━━━━━━━━━━━━━━━━━━━━━━",
    "",
    f"⏰ Time Filter: {time_status}",
    f"   เวลาไทย: {thai_now:%H:%M} (hour {thai_hour})",
    "",
    f"📊 Trend  : {trend}",
    f"📡 Signal : {sig_icon}{block_text}",
    f"💰 Price  : {last['close']:.2f}",
    f"   EMA{config.EMA_FAST}  : {last['ema_fast']:.2f}",
    f"   EMA{config.EMA_SLOW}  : {last['ema_slow']:.2f}",
    f"   RSI    : {last['rsi']:.1f}",
    f"   ADX    : {last['adx']:.1f}",
    f"   ATR    : {atr_val:.2f}",
]

if signal:
    lines += [
        "",
        f"🎯 Entry  : {last['close']:.2f}",
        f"🛑 SL     : {sl:.2f}  ({sl_d:.1f} pts)",
        f"✅ TP     : {tp:.2f}  ({tp_d:.1f} pts)",
        f"📐 R:R    : 1:{tp_d/sl_d:.1f}",
    ]

if not in_window:
    lines += ["", "⚠️ Time Filter BLOCKED", f"   ช่วง {thai_hour}:00 TH มี WR ต่ำ — bot จะไม่ส่ง signal"]

lines += ["", "━━━━━━━━━━━━━━━━━━━━━━"]

msg = "\n".join(lines)
print(msg)
broadcast_text(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_IDS, msg)
disconnect_mt5()
