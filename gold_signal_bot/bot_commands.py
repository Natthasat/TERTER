# ============================================================
# bot_commands.py — Telegram Command Bot (รับคำสั่งจาก user)
# ============================================================
# คำสั่งที่รองรับ:
#   /signal   — วิเคราะห์ตลาดตอนนี้ ควร BUY / SELL / รอ
#   /status   — สถานะ bot + Time Filter + ข้อมูลตลาด
#   /help     — แสดงคำสั่งทั้งหมด
# ============================================================

from __future__ import annotations
import time
import threading
import requests
from datetime import datetime, timezone, timedelta

import config
from mt5_data import connect_mt5, disconnect_mt5, get_ohlc
from indicators import add_indicators
from strategy import evaluate_signal, FilterConfig, check_mtf_trend
from chart import create_signal_chart
from trade_log import format_summary, update_results


# ─── Telegram API helpers ────────────────────────────────────
def get_updates(bot_token: str, offset: int = 0, timeout: int = 30) -> list:
    """Long-poll Telegram getUpdates API."""
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    params = {"offset": offset, "timeout": timeout, "allowed_updates": ["message"]}
    try:
        resp = requests.get(url, params=params, timeout=timeout + 5)
        if resp.status_code == 200:
            return resp.json().get("result", [])
    except requests.RequestException:
        pass
    return []


def reply_text(bot_token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=10)


def reply_photo(bot_token: str, chat_id: str, image_path: str, caption: str = "") -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    try:
        with open(image_path, "rb") as img:
            requests.post(url, data={"chat_id": chat_id, "caption": caption},
                          files={"photo": img}, timeout=15)
    except FileNotFoundError:
        reply_text(bot_token, chat_id, "⚠️ ไม่สามารถสร้างกราฟได้")


# ─── Thai time helper ────────────────────────────────────────
def thai_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=7)


# ─── Command: /signal ────────────────────────────────────────
def cmd_signal(bot_token: str, chat_id: str) -> None:
    """วิเคราะห์ตลาดแบบ real-time แล้วตอบกลับ."""
    reply_text(bot_token, chat_id, "🔍 กำลังวิเคราะห์ตลาด GOLD M5 ...")

    if not connect_mt5():
        reply_text(bot_token, chat_id, "❌ ไม่สามารถเชื่อมต่อ MT5 ได้")
        return

    try:
        df = get_ohlc(config.SYMBOL, config.TIMEFRAME, config.NUM_BARS)
        if df is None:
            reply_text(bot_token, chat_id, "❌ ไม่สามารถดึงข้อมูลได้")
            return

        df = add_indicators(df, ema_fast=config.EMA_FAST, ema_slow=config.EMA_SLOW,
                            rsi_period=config.RSI_PERIOD, atr_period=14, adx_period=14)
        last = df.iloc[-1]

        # MTF M15 data
        df_mtf = None
        mtf_trend_str = "—"
        if getattr(config, "USE_MTF_CONFIRMATION", False):
            df_mtf = get_ohlc(config.SYMBOL, config.MTF_TIMEFRAME,
                              getattr(config, "MTF_NUM_BARS", 100))
            if df_mtf is not None:
                df_mtf = add_indicators(
                    df_mtf,
                    ema_fast=getattr(config, "MTF_EMA_FAST", 10),
                    ema_slow=getattr(config, "MTF_EMA_SLOW", 30),
                    rsi_period=config.RSI_PERIOD, atr_period=14, adx_period=14,
                )
                mt = check_mtf_trend(df_mtf)
                mtf_trend_str = mt if mt else "SIDEWAY"

        # Time filter
        tn = thai_now()
        th_hour = tn.hour
        allowed = getattr(config, "ALLOWED_HOURS_TH", list(range(24)))
        use_tf = getattr(config, "USE_TIME_FILTER", False)
        in_window = (not use_tf) or (th_hour in allowed)

        # Trend — ดูทั้ง EMA order + ตำแหน่งราคา
        p = last["close"]
        ef = last["ema_fast"]
        es = last["ema_slow"]

        if p > ef > es:
            # ราคาอยู่เหนือ EMA ทั้งคู่ + EMA เรียงขึ้น → Uptrend ชัด
            trend = "🟢 UPTREND ↑"
            trend_bias = "BUY"
        elif p < ef < es:
            # ราคาอยู่ใต้ EMA ทั้งคู่ + EMA เรียงลง → Downtrend ชัด
            trend = "🔴 DOWNTREND ↓"
            trend_bias = "SELL"
        elif p < ef and p < es:
            # ราคาหลุดต่ำกว่า EMA ทั้งคู่ (EMA ยังไม่ตัด แต่ราคาร่วงแล้ว)
            trend = "🔴 BEARISH ↓ (ราคาต่ำกว่า EMA)"
            trend_bias = "SELL"
        elif p > ef and p > es:
            # ราคาอยู่เหนือ EMA ทั้งคู่ (EMA ยังไม่ตัด แต่ราคาวิ่งขึ้นแล้ว)
            trend = "🟢 BULLISH ↑ (ราคาสูงกว่า EMA)"
            trend_bias = "BUY"
        else:
            # ราคาอยู่ระหว่าง EMA สองเส้น → Sideway จริง
            trend = "⚪ SIDEWAY ─"
            trend_bias = "WAIT"

        # Signal (with MTF)
        fc = FilterConfig.from_config_module(config)
        signal, reason = evaluate_signal(df, filters=fc, df_mtf=df_mtf)

        atr_val = last["atr"]
        sl_d  = atr_val * config.ATR_SL_MULT
        tp1_d = atr_val * getattr(config, "ATR_TP1_MULT", 1.0)
        tp2_d = atr_val * getattr(config, "ATR_TP2_MULT", 1.5)
        tp3_d = atr_val * getattr(config, "ATR_TP3_MULT", 2.0)

        # ─── Determine recommendation level ────────────────
        # STRONG  = signal + in time window
        # MEDIUM  = signal + out of time window
        # LOW     = blocked by filter / trend only (no pullback)
        # WAIT    = sideway / no direction
        rsi_val = last["rsi"]
        adx_val = last["adx"]
        direction = None   # BUY / SELL / None
        conf = "WAIT"
        conf_reasons = []

        if signal and in_window:
            conf = "STRONG"
            direction = signal
            conf_reasons.append("ผ่านทุกเงื่อนไข + ช่วงเวลาดี")
        elif signal and not in_window:
            conf = "MEDIUM"
            direction = signal
            conf_reasons.append(f"สัญญาณชัด แต่ช่วง {th_hour}:00 TH WR ต่ำ")
            conf_reasons.append("→ ลด lot size ถ้าเข้า")
        elif reason and trend_bias in ("BUY", "SELL"):
            conf = "LOW"
            direction = trend_bias
            conf_reasons.append(f"สัญญาณถูก block: {reason}")
            conf_reasons.append("→ ใช้ lot เล็ก + SL เคร่ง")
        elif reason:
            conf = "WAIT"
            conf_reasons.append(f"สัญญาณถูก block: {reason}")
            conf_reasons.append("ตลาด sideway → รอให้ชัดก่อน")
        elif trend_bias in ("BUY", "SELL"):
            conf = "LOW"
            direction = trend_bias
            conf_reasons.append("Trend เริ่มเห็น แต่รอ pullback จะดีกว่า")
            # เพิ่ม risk เฉพาะ
            if direction == "BUY":
                if rsi_val > 70:
                    conf_reasons.append("RSI Overbought — อาจย่อก่อนขึ้น")
                if mtf_trend_str == "SELL":
                    conf_reasons.append("M15 เป็น SELL — สวน TF ใหญ่")
            else:
                if rsi_val < 30:
                    conf_reasons.append("RSI Oversold — อาจเด้งก่อนลง")
                if mtf_trend_str == "BUY":
                    conf_reasons.append("M15 เป็น BUY — สวน TF ใหญ่")
            if adx_val < 15:
                conf_reasons.append("ADX ต่ำ — trend ยังไม่แรง")
            if not in_window:
                conf_reasons.append(f"ช่วง {th_hour}:00 TH WR ต่ำ")
        else:
            # Sideway (ราคาอยู่ระหว่าง EMA 2 เส้น) — ดูว่าราคาใกล้ฝั่งไหน
            p = last["close"]
            ef = last["ema_fast"]
            es = last["ema_slow"]
            mid_ema = (ef + es) / 2

            if p > mid_ema:
                conf = "WAIT"
                conf_reasons.append("ตลาด Sideway — ราคาเอียงฝั่ง BUY")
                conf_reasons.append("ยังไม่ชัดพอ → รอราคาทะลุ EMA ทั้งคู่")
            elif p < mid_ema:
                conf = "WAIT"
                conf_reasons.append("ตลาด Sideway — ราคาเอียงฝั่ง SELL")
                conf_reasons.append("ยังไม่ชัดพอ → รอราคาทะลุ EMA ทั้งคู่")
            else:
                conf = "WAIT"
                conf_reasons.append("ตลาด Sideway สมบูรณ์ — ไม่มีทิศทาง")
                conf_reasons.append("รอให้ราคาทะลุ EMA ก่อน")

        # ─── Calculate SL / TP ────────────────────────────────
        sl = tp1 = tp2 = tp3 = None
        if direction:
            if direction == "BUY":
                sl  = last["close"] - sl_d
                tp1 = last["close"] + tp1_d
                tp2 = last["close"] + tp2_d
                tp3 = last["close"] + tp3_d
            else:
                sl  = last["close"] + sl_d
                tp1 = last["close"] - tp1_d
                tp2 = last["close"] - tp2_d
                tp3 = last["close"] - tp3_d

        # ─── Build Message ────────────────────────────────────
        price = last["close"]

        # === Header: ชัดเจนว่า BUY / SELL / WAIT ===
        if direction == "BUY":
            dir_icon = {"STRONG": "🟢🟢🟢", "MEDIUM": "🟡", "LOW": "🟠"}.get(conf, "🟡")
            header = f"{dir_icon} BUY GOLD 📍 {price:.0f}"
        elif direction == "SELL":
            dir_icon = {"STRONG": "🔴🔴🔴", "MEDIUM": "🟡", "LOW": "🟠"}.get(conf, "🟡")
            header = f"{dir_icon} SELL GOLD 📍 {price:.0f}"
        else:
            header = "⏸️ WAIT — รอสัญญาณ"

        # === Confidence badge ===
        conf_map = {
            "STRONG": ("✅ เข้าได้เลย!", "สูง"),
            "MEDIUM": ("⚠️ เข้าได้ แต่ลด lot", "ปานกลาง"),
            "LOW":    ("⛔ ไม่แนะนำเข้า", "ต่ำ"),
            "WAIT":   ("⏸️ รอก่อน", "—"),
        }
        conf_text, conf_label = conf_map[conf]

        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━━━",
            f"  {header}",
            "━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            conf_text,
        ]
        for r in conf_reasons:
            lines.append(f"   {r}")

        # === SL / TP (only when there's a direction) ===
        if direction and sl is not None:
            lines += [
                "",
                f"🛑 SL   : {sl:.0f}  ({abs(price - sl):.0f} pts)",
                f"🎯 TP1  : {tp1:.0f}  ({abs(tp1 - price):.0f} pts)",
                f"🎯 TP2  : {tp2:.0f}  ({abs(tp2 - price):.0f} pts)",
                f"🎯 TP3  : {tp3:.0f}  ({abs(tp3 - price):.0f} pts)",
            ]

        # === Market Info ===
        # MTF display
        m5_dir = "BUY" if trend_bias == "BUY" else ("SELL" if trend_bias == "SELL" else "—")
        mtf_dir = mtf_trend_str if mtf_trend_str != "—" else "—"

        lines += [
            "",
            "📊 ตลาด:",
            f"   {trend}",
            f"   M5 {m5_dir} / M15 {mtf_dir}",
            f"   RSI {rsi_val:.1f} | ADX {adx_val:.1f} | ATR {atr_val:.2f}",
        ]

        # === Time Filter ===
        lines.append("")
        if use_tf:
            if in_window:
                lines.append(f"🟢 เวลาเทรดที่ดี ({th_hour}:00 TH)")
            else:
                lines.append(f"🔴 นอกเวลาเทรด ({th_hour}:00 TH)")
        lines.append(f"⏰ {tn:%d/%m/%Y %H:%M} TH")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━")
        msg = "\n".join(lines)
        reply_text(bot_token, chat_id, msg)

    finally:
        disconnect_mt5()


# ─── Command: /status ────────────────────────────────────────
def cmd_status(bot_token: str, chat_id: str) -> None:
    """แสดงสถานะ bot."""
    tn = thai_now()
    th_hour = tn.hour
    use_tf = getattr(config, "USE_TIME_FILTER", False)
    allowed = getattr(config, "ALLOWED_HOURS_TH", list(range(24)))
    in_window = (not use_tf) or (th_hour in allowed)

    # หาช่วงเวลาถัดไปที่เปิด
    next_open = "—"
    if use_tf and not in_window:
        for offset in range(1, 25):
            check_hr = (th_hour + offset) % 24
            if check_hr in allowed:
                next_open = f"{check_hr:02d}:00 TH"
                break

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        "🤖 Bot Status",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"⏰ เวลาไทย: {tn:%H:%M}",
        f"📊 Symbol : {config.SYMBOL} {config.TIMEFRAME_LABEL}",
        f"📐 EMA    : {config.EMA_FAST}/{config.EMA_SLOW}",
        f"🛑 SL     : {config.ATR_SL_MULT}x ATR",
        f"✅ TP     : {config.ATR_TP_MULT}x ATR",
        f"📈 ADX    : ≥{config.ADX_THRESHOLD}",
        "",
        f"⏰ Time Filter: {'ON' if use_tf else 'OFF'}",
    ]

    if use_tf:
        if in_window:
            lines.append(f"   🟢 ช่วงนี้เปิดรับสัญญาณ (hour {th_hour})")
        else:
            lines.append(f"   🔴 ช่วงนี้ปิด (hour {th_hour})")
            lines.append(f"   ⏳ เปิดถัดไป: {next_open}")
        hrs_str = ", ".join(f"{h:02d}" for h in sorted(allowed))
        lines.append(f"   Hours: [{hrs_str}]")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    reply_text(bot_token, chat_id, "\n".join(lines))


# ─── Command: /log ────────────────────────────────────────
def cmd_log(bot_token: str, chat_id: str) -> None:
    """สรุปผลเทรดจริง + อัปเดตสถานะเทรดที่ OPEN."""
    # อัปเดตเทรดที่ยังเปิดอยู่ก่อน
    if connect_mt5():
        try:
            update_results(get_ohlc, config.SYMBOL, config.TIMEFRAME)
        finally:
            disconnect_mt5()
    msg = format_summary()
    reply_text(bot_token, chat_id, msg)


# ─── Command: /help ──────────────────────────────────────────
def cmd_help(bot_token: str, chat_id: str) -> None:
    msg = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📋 คำสั่ง Bot\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "/signal — วิเคราะห์ตอนนี้ ควร B หรือ S?\n"
        "/log    — สรุปผลเทรดจริง + Win Rate\n"
        "/status — สถานะ bot + Time Filter\n"
        "/help   — แสดงคำสั่งทั้งหมด\n"
        "\n"
        "พิมพ์ข้อความก็ได้:\n"
        "  'ตอนนี้' / 'เข้าอะไร' / 'now'\n"
        "  → จะตอบเหมือน /signal\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    reply_text(bot_token, chat_id, msg)


# ─── Allowed users check ────────────────────────────────────
def is_allowed(chat_id: str) -> bool:
    return str(chat_id) in config.TELEGRAM_CHAT_IDS


# ─── Natural language detection ──────────────────────────────
SIGNAL_KEYWORDS = [
    "ตอนนี้", "เข้าอะไร", "ควรเข้า", "buy", "sell", "signal",
    "วิเคราะห์", "สัญญาณ", "now", "เทรด", "trade", "b or s",
    "b หรือ s", "ซื้อ", "ขาย", "long", "short", "เข้า",
]

STATUS_KEYWORDS = ["status", "สถานะ", "bot"]
HELP_KEYWORDS = ["help", "คำสั่ง", "ช่วย", "วิธีใช้"]
LOG_KEYWORDS = ["log", "ผลเทรด", "สถิติ", "stat", "wr", "winrate", "win rate", "ประวัติ"]


def detect_command(text: str) -> str | None:
    """ตรวจข้อความธรรมดาว่าต้องการคำสั่งอะไร."""
    t = text.lower().strip()
    if t.startswith("/log"):
        return "log"
    if t.startswith("/signal"):
        return "signal"
    if t.startswith("/status"):
        return "status"
    if t.startswith("/help") or t.startswith("/start"):
        return "help"
    for kw in SIGNAL_KEYWORDS:
        if kw in t:
            return "signal"
    for kw in STATUS_KEYWORDS:
        if kw in t:
            return "status"
    for kw in HELP_KEYWORDS:
        if kw in t:
            return "help"
    for kw in LOG_KEYWORDS:
        if kw in t:
            return "log"
    return None


# ─── Main polling loop ───────────────────────────────────────
def run_command_bot() -> None:
    """Long-poll Telegram สำหรับรับคำสั่งจาก user."""
    token = config.TELEGRAM_BOT_TOKEN
    offset = 0

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🤖 Telegram Command Bot — เริ่มทำงาน")
    print(f"   Allowed users: {config.TELEGRAM_CHAT_IDS}")
    print("   คำสั่ง: /signal /status /help")
    print("   หรือพิมพ์ 'ตอนนี้', 'เข้าอะไร', 'now'")
    print("   กด Ctrl+C เพื่อหยุด")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    while True:
        try:
            updates = get_updates(token, offset=offset, timeout=30)
            for upd in updates:
                offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text = msg.get("text", "")
                user_name = msg.get("from", {}).get("first_name", "unknown")

                if not chat_id or not text:
                    continue

                # ตรวจสิทธิ์
                if not is_allowed(chat_id):
                    reply_text(token, chat_id, "⛔ คุณไม่ได้อยู่ในรายชื่อผู้ใช้\nติดต่อ admin เพื่อเพิ่มสิทธิ์")
                    print(f"[CMD] ⛔ Unauthorized: {user_name} (chat={chat_id})")
                    continue

                cmd = detect_command(text)
                if cmd is None:
                    reply_text(token, chat_id, "❓ ไม่เข้าใจคำสั่ง\nพิมพ์ /help เพื่อดูคำสั่งทั้งหมด")
                    continue

                tn = thai_now()
                print(f"[{tn:%H:%M}] 📩 {user_name}: '{text}' → /{cmd}")

                if cmd == "signal":
                    cmd_signal(token, chat_id)
                elif cmd == "status":
                    cmd_status(token, chat_id)
                elif cmd == "log":
                    cmd_log(token, chat_id)
                elif cmd == "help":
                    cmd_help(token, chat_id)

        except KeyboardInterrupt:
            print("\n[Bot] หยุดทำงาน")
            break
        except Exception as e:
            print(f"[Bot] error: {e}")
            time.sleep(5)


# ─── Entry Point ─────────────────────────────────────────────
if __name__ == "__main__":
    run_command_bot()
