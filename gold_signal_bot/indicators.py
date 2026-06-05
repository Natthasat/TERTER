# ============================================================
# indicators.py — คำนวณ Technical Indicators (EMA / RSI)
# ============================================================

import pandas as pd
from ta.trend import EMAIndicator, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange


def add_indicators(
    df: pd.DataFrame,
    ema_fast: int = 20,
    ema_slow: int = 50,
    rsi_period: int = 14,
    atr_period: int = 14,
    adx_period: int = 14,
) -> pd.DataFrame:
    """เพิ่ม EMA fast/slow, RSI, ATR และ ADX ลงใน DataFrame

    Parameters
    ----------
    df : pd.DataFrame   ต้องมีคอลัมน์ 'high', 'low', 'close'
    ema_fast : int       period ของ EMA เร็ว  (default 20)
    ema_slow : int       period ของ EMA ช้า   (default 50)
    rsi_period : int     period ของ RSI       (default 14)
    atr_period : int     period ของ ATR       (default 14)
    adx_period : int     period ของ ADX       (default 14)

    Returns
    -------
    pd.DataFrame  พร้อมคอลัมน์ ema_fast, ema_slow, rsi, atr, adx
    """
    # ── EMA ──
    df["ema_fast"] = EMAIndicator(
        close=df["close"], window=ema_fast
    ).ema_indicator()

    df["ema_slow"] = EMAIndicator(
        close=df["close"], window=ema_slow
    ).ema_indicator()

    # ── RSI ──
    df["rsi"] = RSIIndicator(
        close=df["close"], window=rsi_period
    ).rsi()

    # ── ATR ──
    df["atr"] = AverageTrueRange(
        high=df["high"], low=df["low"], close=df["close"],
        window=atr_period,
    ).average_true_range()

    # ── ADX (trend strength) ──
    adx_ind = ADXIndicator(
        high=df["high"], low=df["low"], close=df["close"],
        window=adx_period,
    )
    df["adx"] = adx_ind.adx()

    # ── ATR moving average (สำหรับ volatility guard) ──
    df["atr_avg"] = df["atr"].rolling(window=50, min_periods=20).mean()

    # ── ลบแถวที่ indicator ยังไม่พร้อม ──
    df.dropna(subset=["ema_fast", "ema_slow", "rsi", "atr", "adx", "atr_avg"],
              inplace=True)
    df.reset_index(drop=True, inplace=True)

    return df
