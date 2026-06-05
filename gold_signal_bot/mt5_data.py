# ============================================================
# mt5_data.py — เชื่อมต่อ MT5 และดึงข้อมูล OHLC
# ============================================================

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime


def connect_mt5() -> bool:
    """เชื่อมต่อ MetaTrader 5 terminal
    Returns True ถ้าเชื่อมต่อสำเร็จ, False ถ้าล้มเหลว
    """
    if not mt5.initialize():
        print(f"[MT5] initialize failed — {mt5.last_error()}")
        return False
    print("[MT5] connected ✓")
    return True


def disconnect_mt5() -> None:
    """ปิดการเชื่อมต่อ MT5"""
    mt5.shutdown()
    print("[MT5] disconnected")


def get_ohlc(symbol: str, timeframe: int, num_bars: int) -> pd.DataFrame | None:
    """ดึงข้อมูล OHLC จาก MT5 แล้วแปลงเป็น DataFrame

    Parameters
    ----------
    symbol : str        เช่น "XAUUSD"
    timeframe : int     เช่น mt5.TIMEFRAME_M15
    num_bars : int      จำนวนแท่งย้อนหลัง

    Returns
    -------
    pd.DataFrame | None
        columns: time, open, high, low, close, tick_volume
        คืน None ถ้าดึงข้อมูลไม่ได้
    """
    # เปิด symbol ใน Market Watch ก่อน (บางโบรกต้อง select ก่อนดึงข้อมูลได้)
    if not mt5.symbol_select(symbol, True):
        print(f"[MT5] symbol_select('{symbol}') ล้มเหลว — {mt5.last_error()}")
        return None

    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_bars)

    if rates is None or len(rates) == 0:
        print(f"[MT5] ดึงข้อมูล {symbol} ไม่ได้ — {mt5.last_error()}")
        return None

    df = pd.DataFrame(rates)

    # แปลง timestamp → datetime
    df["time"] = pd.to_datetime(df["time"], unit="s")

    # เลือกเฉพาะ column ที่ใช้
    df = df[["time", "open", "high", "low", "close", "tick_volume"]].copy()

    return df
