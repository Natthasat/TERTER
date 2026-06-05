# ============================================================
# ea_strategy.py — Gold Speed Scalp v2 Strategy (M1 PURE)
# ============================================================
# ทุกอย่างจาก M1 ล้วน: trend + entry + confidence
# ไม่พึ่ง TF อื่น → เข้าเร็ว ออกเร็ว
# ============================================================

from __future__ import annotations
import pandas as pd
from datetime import datetime, timezone, timedelta

import MetaTrader5 as mt5
import ea_config as cfg
from indicators import add_indicators


# ─── Data Helper ───────────────────────────────────────────
def get_data(
    symbol: str, timeframe: int, num_bars: int = None
) -> pd.DataFrame | None:
    """ดึง OHLC + indicators สำหรับ EA"""
    num_bars = num_bars or cfg.NUM_BARS

    if not mt5.symbol_select(symbol, True):
        return None

    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_bars)
    if rates is None or len(rates) == 0:
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df[["time", "open", "high", "low", "close", "tick_volume"]].copy()

    # Indicators (EMA 8/21, RSI 5, ATR 14)
    df = add_indicators(
        df,
        ema_fast=cfg.EMA_FAST,
        ema_slow=cfg.EMA_SLOW,
        rsi_period=cfg.RSI_PERIOD,
        atr_period=cfg.ATR_PERIOD,
        adx_period=cfg.ATR_PERIOD,      # ไม่ใช้ ADX แต่ต้องส่ง
    )

    # เพิ่ม ATR avg + Volume avg (สำหรับ confidence)
    df["atr_sma"] = df["atr"].rolling(20).mean()
    df["vol_sma"] = df["tick_volume"].rolling(20).mean()

    df.dropna(subset=["atr_sma", "vol_sma"], inplace=True)
    df.reset_index(drop=True, inplace=True)

    return df if len(df) > 10 else None


# ─── Trend Detection (M1) ────────────────────────────
def get_trend(df: pd.DataFrame) -> str | None:
    """
    ตรวจ trend จาก M1: EMA8/21 cross + slope
    Returns: "BUY" / "SELL" / None
    """
    if df is None or len(df) < cfg.SLOPE_LOOKBACK + 2:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-(cfg.SLOPE_LOOKBACK + 1)]

    ema_f = last["ema_fast"]
    ema_s = last["ema_slow"]

    slope_up = last["ema_fast"] > prev["ema_fast"]
    slope_dn = last["ema_fast"] < prev["ema_fast"]

    # BUY: EMA8 > EMA21 + slope ขึ้น
    if ema_f > ema_s and slope_up:
        return "BUY"

    # SELL: EMA8 < EMA21 + slope ลง
    if ema_f < ema_s and slope_dn:
        return "SELL"

    return None


# ─── Entry Signal (M1 ล้วน) ─────────────────────────────
def check_entry(df_m1: pd.DataFrame, trend: str) -> str | None:
    """
    ตรวจ entry signal จาก M1
    ใช้ M1 trend เอง (ไม่พึ่ง TF อื่น)
    Returns: "BUY" / "SELL" / None
    """
    if df_m1 is None or len(df_m1) < 5 or trend is None:
        return None

    curr = df_m1.iloc[-1]
    prev = df_m1.iloc[-2]

    ema_f = curr["ema_fast"]
    price = curr["close"]
    rsi   = curr["rsi"]

    # Body ratio check
    candle_range = curr["high"] - curr["low"]
    if candle_range == 0:
        return None
    body = abs(curr["close"] - curr["open"])
    if (body / candle_range) < cfg.MIN_BODY_RATIO:
        return None

    if trend == "BUY":
        # Pullback: แท่งก่อนแตะ EMA → แท่งปัจจุบันปิดเขียวเหนือ EMA
        touched_ema = prev["low"] <= prev["ema_fast"] * 1.003   # tolerance 0.3% (เดิม 0.1%)
        closed_above = price > ema_f * 0.999                    # ผ่อนเล็กน้อย
        bullish_bar  = curr["close"] > curr["open"]
        rsi_ok       = cfg.RSI_BUY_MIN <= rsi <= cfg.RSI_BUY_MAX

        if touched_ema and closed_above and bullish_bar and rsi_ok:
            return "BUY"

    elif trend == "SELL":
        # Pullback: แท่งก่อนเด้ง EMA → แท่งปัจจุบันปิดแดงใต้ EMA
        touched_ema = prev["high"] >= prev["ema_fast"] * 0.997  # tolerance 0.3% (เดิม 0.1%)
        closed_below = price < ema_f * 1.001                    # ผ่อนเล็กน้อย
        bearish_bar  = curr["close"] < curr["open"]
        rsi_ok       = cfg.RSI_SELL_MIN <= rsi <= cfg.RSI_SELL_MAX

        if touched_ema and closed_below and bearish_bar and rsi_ok:
            return "SELL"

    return None


# ─── Session Parameters ──────────────────────────────────
def get_session_params() -> tuple[float, float, str]:
    """
    คืน (TP distance, SL distance, session name) ตามเวลาไทย
    TP ใช้ BROKER_TP_DISTANCE (safety net) — จัดการจริงโดย position_manager
    """
    th = datetime.now(timezone.utc) + timedelta(hours=7)
    h = th.hour

    if 6 <= h < 14:
        return cfg.BROKER_TP_DISTANCE, cfg.ASIA_SL,   "Asia"
    elif 14 <= h < 17:
        return cfg.BROKER_TP_DISTANCE, cfg.LONDON_SL,  "London"
    elif 17 <= h < 20:
        return cfg.BROKER_TP_DISTANCE, cfg.LONDON_SL,  "Overlap"
    elif 20 <= h < 23:
        return cfg.BROKER_TP_DISTANCE, cfg.NY_SL,      "NY"
    else:
        return cfg.BROKER_TP_DISTANCE, cfg.LATE_SL,    "Late"


# ─── Confidence Level (1-5) ──────────────────────────────
def calculate_confidence(
    trend_m1: str | None,
    signal: str | None,
    df_m1: pd.DataFrame | None,
    session: str,
    # backward-compat (ignored)
    trend_m5: str | None = None,
    trend_m15: str | None = None,
    df_m5: pd.DataFrame | None = None,
) -> int:
    """
    คำนวณความมั่นใจ 1-5 จาก M1 ล้วน (v2 — เข้มขึ้น)

    Score (7 factors, cap at 5):
      M1 signal + trend   : +1 (base)
      RSI momentum         : +1
      Active session       : +1
      ATR สูง              : +1
      Volume สูง           : +1
      EMA gap กว้าง        : +1 (trend ชัดเจน)
      Multi-bar momentum   : +1 (แท่งไปทิศเดียวกัน)
    """
    if signal is None:
        return 0

    score = 1  # base: มี signal + trend ตรงกัน
    reasons = ["base"]

    if df_m1 is None or len(df_m1) < 5:
        return score

    last = df_m1.iloc[-1]
    rsi = last["rsi"]

    # 1) RSI momentum ดี (BUY: RSI อยู่ 50-70, SELL: RSI อยู่ 30-50)
    if signal == "BUY" and 50 <= rsi <= 70:
        score += 1
        reasons.append("RSI")
    elif signal == "SELL" and 30 <= rsi <= 50:
        score += 1
        reasons.append("RSI")

    # 2) Session ดี (London / NY)
    if session in ("London", "Overlap", "NY"):
        score += 1
        reasons.append("session")

    # 3) ATR สูง (ตลาดเคลื่อนไหวจริง)
    atr     = last["atr"]
    atr_avg = last.get("atr_sma", atr)
    if atr_avg > 0 and atr >= atr_avg * cfg.MIN_ATR_RATIO:
        score += 1
        reasons.append("ATR")

    # 4) Volume สูง
    vol     = last["tick_volume"]
    vol_avg = last.get("vol_sma", vol)
    if vol_avg > 0 and vol >= vol_avg * cfg.MIN_VOL_RATIO:
        score += 1
        reasons.append("volume")

    # 5) EMA gap กว้าง → trend ชัดเจน
    ema_gap = abs(last["ema_fast"] - last["ema_slow"])
    min_gap = atr * getattr(cfg, "MIN_EMA_GAP_RATIO", 0.5)
    if ema_gap >= min_gap:
        score += 1
        reasons.append("EMA_gap")

    # 6) Multi-bar momentum (แท่งล่าสุด N แท่งไปทิศเดียวกัน)
    momentum_bars = getattr(cfg, "MOMENTUM_BARS", 3)
    if len(df_m1) >= momentum_bars + 1:
        recent = df_m1.iloc[-(momentum_bars + 1):-1]  # N แท่งก่อนแท่งปัจจุบัน
        if signal == "BUY":
            bullish_count = (recent["close"] > recent["open"]).sum()
            if bullish_count >= momentum_bars - 1:  # อย่างน้อย N-1 แท่งเขียว
                score += 1
                reasons.append("momentum")
        elif signal == "SELL":
            bearish_count = (recent["close"] < recent["open"]).sum()
            if bearish_count >= momentum_bars - 1:  # อย่างน้อย N-1 แท่งแดง
                score += 1
                reasons.append("momentum")

    final = min(score, 5)
    print(f"  📊 Confidence: {final}/5 ({'+'.join(reasons)})")
    return final


# ─── Quick bar time check (ไม่ต้องดึง 200 bars) ──────────
def get_latest_bar_time(symbol: str, timeframe: int) -> int | None:
    """ดึงเวลาแท่งล่าสุด (lightweight)"""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 1)
    if rates is None or len(rates) == 0:
        return None
    return int(rates[0]["time"])
