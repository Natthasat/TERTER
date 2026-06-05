# ============================================================
# strategy.py — Gold-Optimized Signal (Trend + Pullback + Filters)
# ============================================================
#
#  ── Core Logic (เหมือนเดิม) ──
#  BUY  : price > EMA20 > EMA50  AND  RSI > 50
#          + แท่งก่อนหน้า pullback (low แตะ EMA20)
#
#  SELL : price < EMA20 < EMA50  AND  RSI < 50
#          + แท่งก่อนหน้า pullback (high แตะ EMA20)
#
#  ── Gold-Specific Filters (ใหม่) ──
#  1. Session Filter    — เทรดเฉพาะ London/NY
#  2. ADX Filter        — ADX ≥ 20 (มี trend)
#  3. Body Filter       — แท่ง confirm ต้องไม่ใช่ doji
#  4. Anti-Chase        — ราคาไม่ห่าง EMA เกิน 1.5× ATR
#  5. Volatility Guard  — ATR ไม่พุ่งเกิน 2× average (ข่าวแรง)
#
# ============================================================

from __future__ import annotations
import pandas as pd
from filters import apply_all_filters


# ─── Filter Config ───────────────────────────────────────────
class FilterConfig:
    """เก็บค่า filter ทั้งหมดไว้ใน object เดียว"""

    def __init__(
        self,
        use_session_filter: bool = True,
        use_adx_filter: bool = True,
        use_body_filter: bool = True,
        use_anti_chase: bool = True,
        use_volatility_guard: bool = True,
        session_start_utc: int = 7,
        session_end_utc: int = 20,
        adx_threshold: float = 20.0,
        min_body_ratio: float = 0.3,
        max_distance_atr: float = 1.5,
        max_atr_ratio: float = 2.0,
    ):
        self.use_session_filter = use_session_filter
        self.use_adx_filter = use_adx_filter
        self.use_body_filter = use_body_filter
        self.use_anti_chase = use_anti_chase
        self.use_volatility_guard = use_volatility_guard
        self.session_start_utc = session_start_utc
        self.session_end_utc = session_end_utc
        self.adx_threshold = adx_threshold
        self.min_body_ratio = min_body_ratio
        self.max_distance_atr = max_distance_atr
        self.max_atr_ratio = max_atr_ratio

    @classmethod
    def from_config_module(cls, cfg) -> "FilterConfig":
        """สร้างจาก config module โดยอัตโนมัติ"""
        return cls(
            use_session_filter=getattr(cfg, "USE_SESSION_FILTER", True),
            use_adx_filter=getattr(cfg, "USE_ADX_FILTER", True),
            use_body_filter=getattr(cfg, "USE_BODY_FILTER", True),
            use_anti_chase=getattr(cfg, "USE_ANTI_CHASE", True),
            use_volatility_guard=getattr(cfg, "USE_VOLATILITY_GUARD", True),
            session_start_utc=getattr(cfg, "SESSION_START_UTC", 7),
            session_end_utc=getattr(cfg, "SESSION_END_UTC", 20),
            adx_threshold=getattr(cfg, "ADX_THRESHOLD", 20.0),
            min_body_ratio=getattr(cfg, "MIN_BODY_RATIO", 0.3),
            max_distance_atr=getattr(cfg, "MAX_DISTANCE_ATR", 1.5),
            max_atr_ratio=getattr(cfg, "MAX_ATR_RATIO", 2.0),
        )

    @classmethod
    def disabled(cls) -> "FilterConfig":
        """ปิด filter ทั้งหมด (สำหรับเปรียบเทียบ backtest)"""
        return cls(
            use_session_filter=False,
            use_adx_filter=False,
            use_body_filter=False,
            use_anti_chase=False,
            use_volatility_guard=False,
        )


# ─── Core Signal Logic ──────────────────────────────────────
def _raw_signal(curr: pd.Series, prev: pd.Series) -> str | None:
    """ตรวจ raw signal (EMA crossover + RSI + pullback) — ไม่มี filter"""
    price    = curr["close"]
    ema_fast = curr["ema_fast"]
    ema_slow = curr["ema_slow"]
    rsi      = curr["rsi"]

    # ── BUY ──
    uptrend      = price > ema_fast > ema_slow
    rsi_bullish  = rsi > 50
    buy_pullback = prev["low"] <= prev["ema_fast"]

    if uptrend and rsi_bullish and buy_pullback:
        return "BUY"

    # ── SELL ──
    downtrend     = price < ema_fast < ema_slow
    rsi_bearish   = rsi < 50
    sell_pullback = prev["high"] >= prev["ema_fast"]

    if downtrend and rsi_bearish and sell_pullback:
        return "SELL"

    return None


# ─── MTF Confirmation ────────────────────────────────────────
def check_mtf_trend(df_mtf: pd.DataFrame) -> str | None:
    """เช็ค trend ของ timeframe ที่สูงกว่า (M15/H1)
    Returns: 'BUY' / 'SELL' / None (sideway)"""
    if df_mtf is None or len(df_mtf) < 2:
        return None
    last = df_mtf.iloc[-1]
    if last["ema_fast"] > last["ema_slow"]:
        return "BUY"
    elif last["ema_fast"] < last["ema_slow"]:
        return "SELL"
    return None


# ─── Evaluate Signal (with Filters) ─────────────────────────
def evaluate_signal(
    df: pd.DataFrame,
    filters: FilterConfig | None = None,
    df_mtf: pd.DataFrame | None = None,
) -> tuple[str | None, str]:
    """วิเคราะห์สัญญาณจากแท่งล่าสุด พร้อม Gold-specific filters

    Parameters
    ----------
    df : pd.DataFrame
        ต้องมีคอลัมน์: time, open, high, low, close,
        ema_fast, ema_slow, rsi, atr, adx, atr_avg
    filters : FilterConfig | None
        ถ้า None จะใช้ค่า default ทั้งหมด

    Returns
    -------
    (signal, filter_reason)
        signal = "BUY" | "SELL" | None
        filter_reason = "" ถ้าผ่าน, หรือชื่อ filter ที่ block
    """
    if len(df) < 3:
        return None, ""

    if filters is None:
        filters = FilterConfig()

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    # ── Step 1: ตรวจ raw signal ก่อน ──
    signal = _raw_signal(curr, prev)
    if signal is None:
        return None, ""

    # ── Step 1.5: MTF Confirmation ──
    if df_mtf is not None:
        mtf_trend = check_mtf_trend(df_mtf)
        if mtf_trend is not None and mtf_trend != signal:
            return None, f"MTF({mtf_trend})"

    # ── Step 2: ผ่าน filter ──
    avg_atr = curr.get("atr_avg", curr["atr"])

    passed, reason = apply_all_filters(
        curr, avg_atr,
        use_session_filter=filters.use_session_filter,
        use_adx_filter=filters.use_adx_filter,
        use_body_filter=filters.use_body_filter,
        use_anti_chase=filters.use_anti_chase,
        use_volatility_guard=filters.use_volatility_guard,
        session_start_utc=filters.session_start_utc,
        session_end_utc=filters.session_end_utc,
        adx_threshold=filters.adx_threshold,
        min_body_ratio=filters.min_body_ratio,
        max_distance_atr=filters.max_distance_atr,
        max_atr_ratio=filters.max_atr_ratio,
    )

    if not passed:
        return None, reason

    return signal, ""


# ─── Backward-compatible wrapper ─────────────────────────────
def evaluate_signal_simple(df: pd.DataFrame) -> str | None:
    """เวอร์ชันเดิม — return signal อย่างเดียว (ไม่มี filter)
    ใช้สำหรับ code เก่าที่เรียก evaluate_signal(df) แบบเดิม
    """
    signal, _ = evaluate_signal(df, filters=FilterConfig.disabled())
    return signal
