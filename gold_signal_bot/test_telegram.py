"""ทดสอบส่งข้อความ + รูปไป Telegram"""
import config
from notifier import send_text, send_image
from mt5_data import connect_mt5, disconnect_mt5, get_ohlc
from indicators import add_indicators
from chart import create_signal_chart

# 1) ส่งข้อความทดสอบ
print("── ส่งข้อความทดสอบ ──")
send_text(
    config.TELEGRAM_BOT_TOKEN,
    config.TELEGRAM_CHAT_ID,
    "🟢 <b>Gold Signal Bot</b>\n\nBot เชื่อมต่อสำเร็จ!\nพร้อมส่ง signal แล้ว ✓",
)

# 2) สร้างกราฟ + ส่งรูป
print("\n── สร้างกราฟ + ส่งรูป ──")
if connect_mt5():
    df = get_ohlc(config.SYMBOL, config.TIMEFRAME, config.NUM_BARS)
    if df is not None:
        df = add_indicators(df)
        chart = create_signal_chart(
            df, "TEST", config.SYMBOL,
            config.TIMEFRAME_LABEL, "test_telegram.png",
        )
        send_image(
            config.TELEGRAM_BOT_TOKEN,
            config.TELEGRAM_CHAT_ID,
            chart,
            caption=f"📊 {config.SYMBOL} {config.TIMEFRAME_LABEL} — Test Chart",
        )
    disconnect_mt5()

print("\n✓ เสร็จ — เช็ค Telegram ได้เลย!")
