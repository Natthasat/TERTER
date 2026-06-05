# ============================================================
# config.py — ค่าคงที่สำหรับ Gold Signal Bot
# ============================================================

import MetaTrader5 as mt5

# ─── Symbol ─────────────────────────────────────────────────
SYMBOL = "GOLD"

# ─── Timeframe ──────────────────────────────────────────────
# M5 = Scalping ระยะสั้น | M15 = Swing สั้น | H1 = Swing
TIMEFRAME       = mt5.TIMEFRAME_M5
TIMEFRAME_LABEL = "M5"           # ใช้แสดงใน title กราฟ / ข้อความ

# ─── จำนวนแท่งย้อนหลัง ──────────────────────────────────────
NUM_BARS = 300                   # M5 ใช้แท่งมากขึ้นเพื่อ indicator เสถียร

# ─── Indicator Parameters ───────────────────────────────────
# M5 Scalping Optimized: EMA 10/30 (ชนะ M5 optimization)
EMA_FAST   = 10
EMA_SLOW   = 30
RSI_PERIOD = 14
ATR_PERIOD = 14
ADX_PERIOD = 14

# ─── MT5 Server Timezone ─────────────────────────────────────
# ⚠️ MT5 server เป็น UTC+2 (ตรวจพบอัตโนมัติ)
# session hours ด้านล่างเป็นเวลา SERVER (ไม่ใช่ UTC)
SERVER_UTC_OFFSET   = 2

# ─── SL / TP Multiplier (ATR-based) ─────────────────────────
# M5 Optimized (5,000 bars):
#   EMA 10/30 + SL 1.5 + TP 1.2 + ADX≥12
#   → WR 58.8%, PF 1.23, Net +642, DD 201, ConsL 5
ATR_SL_MULT  = 1.5      # SL = 1.5 × ATR
ATR_TP1_MULT = 1.0      # TP1 = 1.0 × ATR (ทำกำไรก่อน)
ATR_TP2_MULT = 1.5      # TP2 = 1.5 × ATR (เป้าหลัก)
ATR_TP3_MULT = 2.0      # TP3 = 2.0 × ATR (หากวิ่งได้)
ATR_TP_MULT  = 1.2      # (backward-compat สำหรับ backtester)

# ─── Multi-Timeframe (MTF) Confirmation ─────────────────────
# Backtest 5,000 bars: M15 MTF เพิ่ม WR 64→65.7%, PF 1.42→1.53
# ดูว่า M15 trend ตรงกับ M5 signal หรือไม่ ถ้าไม่ตรง → skip
USE_MTF_CONFIRMATION = True
MTF_TIMEFRAME        = mt5.TIMEFRAME_M15
MTF_TIMEFRAME_LABEL  = "M15"
MTF_NUM_BARS         = 100
MTF_EMA_FAST         = 10
MTF_EMA_SLOW         = 30

# ─── Gold-Specific Filters ──────────────────────────────────
# ADX ≥ 15 เป็น filter เดียวที่ช่วย
#   ✘ Session Filter กรอง trade ดีออก → PF ตก
#   ✘ Body/Anti-Chase/VolGuard ทำให้แย่ลง
#
# Session Filter — ปิด (ไม่ช่วยใน data ชุดนี้)
USE_SESSION_FILTER  = False
SESSION_START_UTC   = 9      # London open  (server time, UTC+2)
SESSION_END_UTC     = 22     # NY close     (server time, UTC+2)

# ADX Filter — เปิด (ช่วยกรอง sideway)
USE_ADX_FILTER      = True
ADX_THRESHOLD       = 12.0   # ADX ≥ 12 = มี trend (เหมาะ M5 ใช้ค่าต่ำกว่า M15)

# Body Filter — ปิด
USE_BODY_FILTER     = False
MIN_BODY_RATIO      = 0.25

# Anti-Chase — ปิด
USE_ANTI_CHASE      = False
MAX_DISTANCE_ATR    = 2.0

# Volatility Guard — ปิด
USE_VOLATILITY_GUARD = False
MAX_ATR_RATIO       = 2.5

# ─── Time Filter (เวลาไทย UTC+7) ──────────────────────────
# วิเคราะห์จาก backtest 5,000 bars M5:
#   Asia  (07-14 TH)  WR 65.3%  ★ ดีที่สุด
#   DeadZ (05-07 TH)  WR 77.8%  ★ volume น้อยแต่ WR สูงมาก
#   LateNY(02-05 TH)  WR 59.5%
#   NY    (20-02 TH)  WR 56.2%
#   London(14-20 TH)  WR 50.9%  ✘ แย่สุด
#
# ช่วงอันตราย: 17-20 ไทย (London open overlap) WR < 48%
# ช่วงอันตราย: 01:00 ไทย WR 37.5%
USE_TIME_FILTER = True

# ชั่วโมงที่อนุญาต (เวลาไทย UTC+7, 0-23)
# เลือกเฉพาะชั่วโมงที่ WR ≥ 55% จาก backtest
ALLOWED_HOURS_TH = [
    3, 4,           # Late NY (ดี)
    6,              # Dead Zone (WR 77.8%)
    8, 9,           # Asia (WR 68%+)
    12, 13,         # Asia (WR 63-73%)
    15, 16,         # London start (WR 60-69%)
    21, 22, 23,     # NY session (WR 57-67%)
    0,              # NY late (WR 68.8%)
]
# ★ ตัดช่วง: 17-20 ไทย (London กลาง WR < 50%), 01-02 ไทย (WR < 50%)

# ─── Telegram ───────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = "8162489453:AAHXLi65ypLqGYnqeO05Ym0UHtkdRe-od0I"

# รองรับหลาย user — เพิ่ม Chat ID ใน list ได้เลย
TELEGRAM_CHAT_IDS  = [
    "8289645291",    # Natthasat Sonwianh
    "1252300851",    # Black//.
]

# backward-compatible (code เก่าที่ใช้ TELEGRAM_CHAT_ID ตัวเดียว)
TELEGRAM_CHAT_ID = TELEGRAM_CHAT_IDS[0]

# ─── Chart Output ───────────────────────────────────────────
CHART_FILENAME = "signal_chart.png"
