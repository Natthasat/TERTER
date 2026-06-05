# ============================================================
# filters.py — Gold-Specific Filters (ลด false signal)
# ============================================================
#
#  Filter ทั้งหมดออกแบบมาเฉพาะพฤติกรรม XAUUSD:
#
#    1. Session Filter    — เทรดเฉพาะ London/NY (ทองเคลื่อนไหวแรง)
#    2. ADX Filter        — กรอง sideway (ADX ต่ำ = ไม่มี trend)
#    3. Spread Guard      — ไม่เข้าถ้าแท่ง body เล็กเกิน (doji/indecision)
#    4. Anti-Chase        — ไม่ไล่ราคา ถ้าห่าง EMA มากเกิน ATR
#    5. Volatility Guard  — ข้ามถ้า ATR พุ่งผิดปกติ (ข่าวแรง/spike)
#
# ============================================================

from __future__ import annotations
import pandas as pd


# ─── 1. Session Filter ──────────────────────────────────────
#
#  Gold เคลื่อนไหวแรงช่วง London open → NY close
#  Asian session (00:00–07:00 UTC) มักเป็น sideway → false signal เยอะ
#
#  London  : 07:00 – 16:00 UTC
#  New York: 13:00 – 21:00 UTC
#  Overlap : 13:00 – 16:00 UTC  ← ช่วง volatility สูงสุด
#
def is_active_session(
    bar_time: pd.Timestamp,
    session_start_utc: int = 7,
    session_end_utc: int = 20,
) -> bool:
    """ตรวจว่าแท่งอยู่ในช่วงเวลาที่ Gold active หรือไม่

    Parameters
    ----------
    bar_time : pd.Timestamp
    session_start_utc : int   ชั่วโมงเริ่ม (UTC, default 7 = London open)
    session_end_utc   : int   ชั่วโมงสิ้นสุด (UTC, default 20 = NY close)

    Returns
    -------
    bool  True = อยู่ใน active session
    """
    hour = bar_time.hour
    return session_start_utc <= hour < session_end_utc


# ─── 2. ADX Filter (Trend Strength) ─────────────────────────
#
#  ADX < 20  → ตลาด sideway      → ห้ามเข้า
#  ADX 20-25 → trend อ่อน         → ระวัง
#  ADX > 25  → trend แข็งแรง      → เข้าได้
#
def is_trending(adx_value: float, adx_threshold: float = 20.0) -> bool:
    """ตรวจว่าตลาดมี trend เพียงพอหรือไม่

    Parameters
    ----------
    adx_value : float       ค่า ADX ปัจจุบัน
    adx_threshold : float   ค่าขั้นต่ำ (default 20)

    Returns
    -------
    bool  True = มี trend
    """
    return adx_value >= adx_threshold


# ─── 3. Spread / Body Filter ────────────────────────────────
#
#  Gold มี spread สูง + แท่ง doji เยอะในช่วง sideway
#  ถ้า body เล็กกว่า 30% ของ range → ไม่มี conviction → ข้าม
#
def has_meaningful_body(
    open_price: float,
    close_price: float,
    high_price: float,
    low_price: float,
    min_body_ratio: float = 0.3,
) -> bool:
    """ตรวจว่าแท่งมี body ใหญ่พอ (ไม่ใช่ doji/spinning top)

    Parameters
    ----------
    min_body_ratio : float  สัดส่วน body/range ขั้นต่ำ (default 0.3)

    Returns
    -------
    bool  True = body มี conviction
    """
    candle_range = high_price - low_price
    if candle_range == 0:
        return False
    body = abs(close_price - open_price)
    return (body / candle_range) >= min_body_ratio


# ─── 4. Anti-Chase Filter ───────────────────────────────────
#
#  Gold วิ่งแรงแล้วชอบ pullback — ถ้าราคาห่าง EMA มาก = ไล่ราคา
#  กฎ: |price − ema_fast| ต้อง ≤ N × ATR
#
def is_not_chasing(
    price: float,
    ema_fast: float,
    atr: float,
    max_distance_atr: float = 1.5,
) -> bool:
    """ตรวจว่าราคาไม่ห่างจาก EMA fast มากเกินไป

    Parameters
    ----------
    max_distance_atr : float  ระยะห่างสูงสุด คิดเป็นเท่าของ ATR (default 1.5)

    Returns
    -------
    bool  True = ราคาอยู่ในระยะที่เข้าได้
    """
    if atr == 0:
        return False
    distance = abs(price - ema_fast)
    return distance <= (atr * max_distance_atr)


# ─── 5. Volatility Guard ────────────────────────────────────
#
#  ถ้า ATR ปัจจุบัน > 2× ค่าเฉลี่ย ATR 50 แท่ง → ข่าวแรง/spike
#  ไม่เข้าเพราะ SL จะกว้างเกินไป + whipsaw สูง
#
def is_normal_volatility(
    current_atr: float,
    avg_atr: float,
    max_atr_ratio: float = 2.0,
) -> bool:
    """ตรวจว่า volatility ไม่พุ่งผิดปกติ

    Parameters
    ----------
    current_atr : float   ATR ปัจจุบัน
    avg_atr : float       ค่าเฉลี่ย ATR (เช่น 50-bar average)
    max_atr_ratio : float  เท่าตัวสูงสุดเมื่อเทียบกับ avg (default 2.0)

    Returns
    -------
    bool  True = volatility ปกติ
    """
    if avg_atr == 0:
        return False
    return current_atr <= (avg_atr * max_atr_ratio)


# ─── Combined Filter ────────────────────────────────────────
def apply_all_filters(
    bar: pd.Series,
    avg_atr: float,
    *,
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
) -> tuple[bool, str]:
    """ตรวจ filter ทั้งหมดพร้อมกัน

    Parameters
    ----------
    bar : pd.Series    แท่งปัจจุบัน (ต้องมี time, open, high, low, close,
                        ema_fast, atr, adx)
    avg_atr : float    ค่าเฉลี่ย ATR (50-bar)

    Returns
    -------
    (pass: bool, reason: str)
        pass = True  → ผ่านทุก filter, reason = ""
        pass = False → ไม่ผ่าน, reason = ชื่อ filter ที่ block
    """
    # 1) Session
    if use_session_filter:
        if not is_active_session(bar["time"], session_start_utc, session_end_utc):
            return False, "SESSION_FILTER"

    # 2) ADX
    if use_adx_filter and "adx" in bar.index:
        if not is_trending(bar["adx"], adx_threshold):
            return False, "ADX_FILTER"

    # 3) Body
    if use_body_filter:
        if not has_meaningful_body(
            bar["open"], bar["close"], bar["high"], bar["low"],
            min_body_ratio,
        ):
            return False, "BODY_FILTER"

    # 4) Anti-Chase
    if use_anti_chase:
        if not is_not_chasing(
            bar["close"], bar["ema_fast"], bar["atr"],
            max_distance_atr,
        ):
            return False, "ANTI_CHASE"

    # 5) Volatility
    if use_volatility_guard:
        if not is_normal_volatility(bar["atr"], avg_atr, max_atr_ratio):
            return False, "VOLATILITY_GUARD"

    return True, ""
