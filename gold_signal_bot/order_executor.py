# ============================================================
# order_executor.py — MT5 Order Execution for EA Gold Scalp
# ============================================================
# เปิด / ปิด / แก้ไข ออเดอร์ผ่าน MT5 API
# ============================================================

from __future__ import annotations
import MetaTrader5 as mt5
from datetime import datetime, timedelta
import ea_config as cfg


# ─── Helpers ────────────────────────────────────────────────
def get_filling_type(symbol: str) -> int:
    """ตรวจ filling mode ที่โบรกรองรับ"""
    info = mt5.symbol_info(symbol)
    if info is None:
        return mt5.ORDER_FILLING_IOC

    filling = info.filling_mode

    # ใช้ค่าตัวเลขตรง กันปัญหา attribute ไม่มีในบาง version
    FILLING_FOK = getattr(mt5, "SYMBOL_FILLING_FOK", 1)
    FILLING_IOC = getattr(mt5, "SYMBOL_FILLING_IOC", 2)

    if filling & FILLING_FOK:
        return mt5.ORDER_FILLING_FOK
    elif filling & FILLING_IOC:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


def get_spread(symbol: str | None = None) -> float:
    """ดึง spread ปัจจุบัน (price distance)"""
    symbol = symbol or cfg.SYMBOL
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return 999.0
    return round(tick.ask - tick.bid, 2)


def get_contract_size(symbol: str | None = None) -> float:
    """ดึง contract size (ปกติทอง = 100 oz)"""
    symbol = symbol or cfg.SYMBOL
    info = mt5.symbol_info(symbol)
    if info is None:
        return 100.0
    return info.trade_contract_size


def price_to_usd(price_dist: float, lot: float = None) -> float:
    """แปลง price distance → USD P/L"""
    lot = lot or cfg.LOT_SIZE
    cs = get_contract_size()
    return price_dist * lot * cs


# ─── Open Orders ────────────────────────────────────────────
def open_buy(
    symbol: str, lot: float, sl: float, tp: float, comment: str = ""
) -> dict | None:
    """เปิด BUY market order"""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"[EA] ❌ ไม่สามารถดึงราคา {symbol}")
        return None

    request = {
        "action":      mt5.TRADE_ACTION_DEAL,
        "symbol":      symbol,
        "volume":      lot,
        "type":        mt5.ORDER_TYPE_BUY,
        "price":       tick.ask,
        "sl":          round(sl, 2),
        "tp":          round(tp, 2),
        "deviation":   20,
        "magic":       cfg.MAGIC_NUMBER,
        "comment":     comment or "EA Gold BUY",
        "type_time":   mt5.ORDER_TIME_GTC,
        "type_filling": get_filling_type(symbol),
    }

    result = mt5.order_send(request)
    if result is None:
        print(f"[EA] ❌ order_send failed — {mt5.last_error()}")
        return None
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[EA] ❌ BUY failed — {result.retcode}: {result.comment}")
        return None

    print(f"[EA] ✅ BUY @ {result.price:.2f}  SL={sl:.2f}  TP={tp:.2f}")
    return {
        "ticket": result.order,
        "type":   "BUY",
        "price":  result.price,
        "volume": lot,
        "sl":     sl,
        "tp":     tp,
    }


def open_sell(
    symbol: str, lot: float, sl: float, tp: float, comment: str = ""
) -> dict | None:
    """เปิด SELL market order"""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"[EA] ❌ ไม่สามารถดึงราคา {symbol}")
        return None

    request = {
        "action":      mt5.TRADE_ACTION_DEAL,
        "symbol":      symbol,
        "volume":      lot,
        "type":        mt5.ORDER_TYPE_SELL,
        "price":       tick.bid,
        "sl":          round(sl, 2),
        "tp":          round(tp, 2),
        "deviation":   20,
        "magic":       cfg.MAGIC_NUMBER,
        "comment":     comment or "EA Gold SELL",
        "type_time":   mt5.ORDER_TIME_GTC,
        "type_filling": get_filling_type(symbol),
    }

    result = mt5.order_send(request)
    if result is None:
        print(f"[EA] ❌ order_send failed — {mt5.last_error()}")
        return None
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[EA] ❌ SELL failed — {result.retcode}: {result.comment}")
        return None

    print(f"[EA] ✅ SELL @ {result.price:.2f}  SL={sl:.2f}  TP={tp:.2f}")
    return {
        "ticket": result.order,
        "type":   "SELL",
        "price":  result.price,
        "volume": lot,
        "sl":     sl,
        "tp":     tp,
    }


# ─── Close Orders ──────────────────────────────────────────
def close_position(ticket: int) -> bool:
    """ปิด position ด้วย ticket number"""
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        return False
    pos = positions[0]

    tick = mt5.symbol_info_tick(pos.symbol)
    if tick is None:
        return False

    if pos.type == mt5.ORDER_TYPE_BUY:
        price = tick.bid
        order_type = mt5.ORDER_TYPE_SELL
    else:
        price = tick.ask
        order_type = mt5.ORDER_TYPE_BUY

    request = {
        "action":      mt5.TRADE_ACTION_DEAL,
        "symbol":      pos.symbol,
        "volume":      pos.volume,
        "type":        order_type,
        "position":    ticket,
        "price":       price,
        "deviation":   20,
        "magic":       cfg.MAGIC_NUMBER,
        "comment":     "EA Close",
        "type_time":   mt5.ORDER_TIME_GTC,
        "type_filling": get_filling_type(pos.symbol),
    }

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[EA] ❌ ปิด #{ticket} ล้มเหลว — {result}")
        return False
    return True


def close_all(symbol: str | None = None) -> int:
    """ปิดทุก position ของ EA"""
    symbol = symbol or cfg.SYMBOL
    positions = get_ea_positions(symbol)
    closed = 0
    for pos in positions:
        if close_position(pos.ticket):
            closed += 1
    if closed:
        print(f"[EA] ปิดทั้งหมด {closed} positions")
    return closed


# ─── Modify SL/TP ──────────────────────────────────────────
def modify_sl(ticket: int, new_sl: float) -> bool:
    """แก้ไข SL ของ position"""
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        return False
    pos = positions[0]

    request = {
        "action":   mt5.TRADE_ACTION_SLTP,
        "symbol":   pos.symbol,
        "position": ticket,
        "sl":       round(new_sl, 2),
        "tp":       pos.tp,
    }

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        return False
    return True


def modify_tp(ticket: int, new_tp: float) -> bool:
    """แก้ไข TP ของ position"""
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        return False
    pos = positions[0]

    request = {
        "action":   mt5.TRADE_ACTION_SLTP,
        "symbol":   pos.symbol,
        "position": ticket,
        "sl":       pos.sl,
        "tp":       round(new_tp, 2),
    }

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        return False
    return True


# ─── Query Positions ───────────────────────────────────────
def get_ea_positions(symbol: str | None = None) -> list:
    """ดึง position ทั้งหมดของ EA (filter by magic number)"""
    symbol = symbol or cfg.SYMBOL
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return []
    return [p for p in positions if p.magic == cfg.MAGIC_NUMBER]


def get_account_info() -> dict:
    """ดึงข้อมูลบัญชี"""
    info = mt5.account_info()
    if info is None:
        return {}
    return {
        "balance":     info.balance,
        "equity":      info.equity,
        "profit":      info.profit,
        "margin":      info.margin,
        "margin_free": info.margin_free,
    }


def get_deal_result(position_id: int) -> dict | None:
    """ดึงผลเทรดที่ปิดแล้ว (SL/TP โดนโดยโบรก)"""
    now = datetime.now()
    since = now - timedelta(hours=2)

    deals = mt5.history_deals_get(since, now)
    if deals is None:
        return None

    for d in deals:
        if d.position_id == position_id and d.entry == mt5.DEAL_ENTRY_OUT:
            pnl = d.profit + d.commission + d.swap
            direction = "SELL" if d.type == mt5.DEAL_TYPE_SELL else "BUY"
            # entry deal
            entry_price = 0.0
            for ed in deals:
                if ed.position_id == position_id and ed.entry == mt5.DEAL_ENTRY_IN:
                    entry_price = ed.price
                    direction = "BUY" if ed.type == mt5.DEAL_TYPE_BUY else "SELL"
                    break
            return {
                "ticket":     position_id,
                "pnl":        round(pnl, 2),
                "close_price": d.price,
                "entry":      entry_price,
                "exit":       d.price,
                "direction":  direction,
            }
    return None
