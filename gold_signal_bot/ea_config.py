# ============================================================
# ea_config.py — EA Gold Speed Scalp v2 Configuration
# ============================================================
# ทุน: $63 (บัญชีจริง) | Lot: 0.01 | Max: 1 ไม้
# Conservative overnight mode
# ============================================================

import MetaTrader5 as mt5
import config as _cfg   # Telegram + symbol settings

# ─── Symbol ─────────────────────────────────────────────────
SYMBOL = _cfg.SYMBOL                      # "GOLD"

# ─── Lot & Position ─────────────────────────────────────────
LOT_SIZE       = 0.01                     # 0.01 lot = $1/point (เล็กสุด)
MAX_POSITIONS  = 1                        # ★ 1 ไม้เท่านั้น! ทุนน้อยห้ามเปิดหลายไม้
MAGIC_NUMBER   = 789456                   # แยกจาก manual trade

# ─── Capital & Risk ($63 REAL) ──────────────────────────────
CAPITAL                = 63.0
MAX_DAILY_LOSS         = 3.0              # ★ ขาดทุนสูงสุด $3/วัน (~9% ของ $32)
MAX_DAILY_TRADES       = 15               # จำกัด 15 เทรด/วัน
MAX_CONSECUTIVE_LOSSES = 2                # ★ แพ้ 2 ติด → พักทันที (เข้มสุด)
COOLDOWN_MINUTES       = 30               # ★ พัก 30 นาที (ให้ตลาดเปลี่ยนจริง)
MAX_LOSSES_PER_DAY     = 4                # ★ แพ้สูงสุด 4 ครั้ง/วัน → หยุด

# ─── Timeframe ──────────────────────────────────────────────
TF_ENTRY   = mt5.TIMEFRAME_M1            # สัญญาณเข้า
TF_TREND   = mt5.TIMEFRAME_M5            # Trend สั้น
TF_CONFIRM = mt5.TIMEFRAME_M15           # ยืนยัน Trend
NUM_BARS   = 200

# ─── Indicator Periods ──────────────────────────────────────
EMA_FAST   = 8
EMA_SLOW   = 21
RSI_PERIOD = 5
ATR_PERIOD = 14

# ─── Entry Filters (เข้มขึ้น → เทรดน้อยลงแต่ quality สูงขึ้น) ──
MIN_BODY_RATIO = 0.30                     # body > 30% (กรอง doji ออก)
RSI_BUY_MIN    = 45                       # RSI > 45 ถึงจะ BUY (momentum ชัดกว่า)
RSI_BUY_MAX    = 70                       # ไม่ BUY ตอน overbought
RSI_SELL_MIN   = 30                       # ไม่ SELL ตอน oversold  
RSI_SELL_MAX   = 55                       # RSI < 55 ถึงจะ SELL
MAX_SPREAD     = 0.55                     # $0.55 (XM spread ~$0.47-0.49)

# ─── Profit Targets (USD) ───────────────────────────────────
# เป้าหมายกำไรต่อไม้ & รวม (0.01 lot = $1/point)
TARGET_PROFIT_USD    = 2.0                # ★ +$2 → ปิดทันที!
EXTENDED_PROFIT_USD  = 2.0                # ★ เท่ากัน = ปิดเลยที่ $2
TOTAL_PROFIT_TARGET  = 4.0                # กำไรรวม $4+ → ปิดทุกไม้

# TP ส่งให้โบรก (safety net) — price distance
# $2 USD / (0.01 × 100) = $2 price distance
BROKER_TP_DISTANCE = 2.0                  # ★ TP $2 price = +$2 USD ปิดเลย!

# ─── SL ต่อ Session (price distance $) ──────────────────────
# ขยาย SL ให้กว้างขึ้น → ลดโดน SL hit จากสัญญาณรบกวน
# 0.01 lot = $1/point → SL $3.50 = ขาดทุน $3.50/ไม้
#              SL       Loss per trade (0.01 lot)
# Asia        $3.50    $3.50
# London      $3.50    $3.50
# NY          $4.00    $4.00
# Late        $3.00    $3.00
ASIA_SL   = 3.50
LONDON_SL = 3.50
NY_SL     = 4.00
LATE_SL   = 3.00

# ─── Trade Management ──────────────────────────────────────
BE_TRIGGER       = 1.50                   # กำไร $1.50 price → SL = Entry (ให้ห้องหายใจมากขึ้น)
BE_OFFSET        = 0.20                   # buffer +$0.20
TRAIL_TRIGGER    = 2.50                   # กำไร $2.50 price ($2.50 USD) → trail
TRAIL_LOCK       = 1.50                   # ล็อก $1.50 price ($1.50 USD)
TRAIL_STEP       = 0.80                   # trail ทุก $0.80 price
MAX_HOLD_MINUTES = 30                     # ลดจาก 45 → 30 นาที (ออกเร็วขึ้น M1)
AGGR_TRAIL_PCT   = 0.60                   # ล็อก 60% ของกำไร
AGGR_TRAIL_ROOM  = 0.30                   # ห้องหายใจ $0.30 price

# ─── Confidence System (1-5) ───────────────────────────────
# ★ MIN_CONFIDENCE = 4 → เข้าเฉพาะสัญญาณที่มั่นใจสูงเท่านั้น!
MIN_CONFIDENCE          = 4               # ★ ต้องมั่นใจ 4/5 ขึ้นไปถึงเข้าเทรด
SLOPE_LOOKBACK          = 5               # ดู EMA slope 5 แท่ง (ยืนยัน trend ชัดขึ้น)
MIN_ATR_RATIO           = 1.2             # ATR > 1.2× avg → +conf (ตลาดเคลื่อนจริง)
MIN_VOL_RATIO           = 1.8             # Volume > 1.8× → +conf (volume ชัดกว่า)
MIN_EMA_GAP_RATIO       = 0.5             # EMA gap > 0.5× ATR → +conf (trend ชัด)
MOMENTUM_BARS           = 3               # ดูย้อน 3 แท่ง สำหรับ momentum check
ADD_POSITION_MIN_PROFIT = 1.0             # ไม้เก่ากำไร $1.0+ ก่อนเปิดไม้ 2
ADD_POS_45_MIN_PROFIT   = 2.0             # กำไร $2.0+ ก่อนเปิดไม้ 3+

# ─── Telegram (ดึงจาก config.py) ───────────────────────────
TELEGRAM_BOT_TOKEN = _cfg.TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_IDS  = _cfg.TELEGRAM_CHAT_IDS

# ─── Server ────────────────────────────────────────────────
SERVER_UTC_OFFSET = getattr(_cfg, "SERVER_UTC_OFFSET", 2)
