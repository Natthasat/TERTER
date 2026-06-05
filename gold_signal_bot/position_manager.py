# ============================================================
# position_manager.py — Position Management for EA Gold Scalp
# ============================================================
# Smart Profit Taking: $10/ไม้ → ดูโอกาส → $20 ถ้า trend แรง
# Total Target: $30+ → ปิดทุกไม้
# BE, Trailing, Time Exit, Reverse Close
# ============================================================

from __future__ import annotations
import time

import MetaTrader5 as mt5
import ea_config as cfg
from order_executor import modify_sl, close_position, get_ea_positions


def manage_positions(trend_direction: str | None) -> list[dict]:
    """
    จัดการ position ทั้งหมดของ EA

    ลำดับความสำคัญ:
    1. Total Profit ≥ $30 → ปิดทุกไม้
    2. แต่ละไม้: reverse/timeout/smart-target/trail/BE

    Parameters
    ----------
    trend_direction : "BUY" / "SELL" / None
        ทิศ trend ปัจจุบัน (จาก M5)

    Returns
    -------
    list[dict]  รายการ position ที่ถูกปิด
    """
    positions = get_ea_positions(cfg.SYMBOL)
    closed_results = []

    if not positions:
        return closed_results

    # ── Total Profit Target: $30+ → ปิดทุกไม้ ─────────────
    total_profit = sum(p.profit for p in positions)
    if total_profit >= cfg.TOTAL_PROFIT_TARGET:
        print(
            f"[EA] 💰 กำไรรวม ${total_profit:.2f} ≥ "
            f"${cfg.TOTAL_PROFIT_TARGET} → ปิดทุกไม้!"
        )
        for pos in positions:
            result = _force_close(pos, "TOTAL_TARGET")
            if result:
                closed_results.append(result)
        return closed_results

    # ── จัดการแต่ละ position ───────────────────────────────
    for pos in positions:
        result = _manage_single(pos, trend_direction)
        if result:
            closed_results.append(result)

    return closed_results


def _force_close(pos, reason: str) -> dict | None:
    """ปิด position พร้อมระบุเหตุผล"""
    tick = mt5.symbol_info_tick(cfg.SYMBOL)
    if tick is None:
        return None

    is_buy = (pos.type == mt5.ORDER_TYPE_BUY)
    pos_dir = "BUY" if is_buy else "SELL"
    current_price = tick.bid if is_buy else tick.ask

    if close_position(pos.ticket):
        reason_icon = {
            "TOTAL_TARGET": "💰",
            "TARGET_20":    "🎯",
            "TARGET_10":    "🎯",
        }.get(reason, "📌")

        print(
            f"[EA] {reason_icon} ปิด #{pos.ticket} {pos_dir} "
            f"[{reason}] P/L: ${pos.profit:+.2f}"
        )
        return {
            "ticket": pos.ticket,
            "pnl": pos.profit,
            "reason": reason,
            "direction": pos_dir,
            "entry": pos.price_open,
            "exit": current_price,
        }
    return None


def _manage_single(pos, trend_direction: str | None) -> dict | None:
    """จัดการ position เดี่ยว — return dict ถ้าปิดแล้ว"""

    tick = mt5.symbol_info_tick(cfg.SYMBOL)
    if tick is None:
        return None

    is_buy      = (pos.type == mt5.ORDER_TYPE_BUY)
    pos_dir     = "BUY" if is_buy else "SELL"
    entry_price = pos.price_open
    profit_usd  = pos.profit

    # ราคาปัจจุบัน (สำหรับคำนวณ distance)
    current_price = tick.bid if is_buy else tick.ask
    if is_buy:
        profit_dist = current_price - entry_price
    else:
        profit_dist = entry_price - current_price

    # trend ยังตรงทิศหรือไม่
    trend_aligned = (trend_direction is not None and trend_direction == pos_dir)

    # ── 1) Reverse Close — trend กลับทิศ ──────────────────
    if trend_direction and trend_direction != pos_dir:
        if close_position(pos.ticket):
            print(
                f"[EA] 🔄 ปิด #{pos.ticket} {pos_dir} "
                f"— trend กลับเป็น {trend_direction} "
                f"P/L: ${profit_usd:+.2f}"
            )
            return {
                "ticket": pos.ticket,
                "pnl": profit_usd,
                "reason": "REVERSE",
                "direction": pos_dir,
                "entry": entry_price,
                "exit": current_price,
            }

    # ── 2) Time Exit — ถือเกิน MAX_HOLD_MINUTES ──────────
    hold_seconds = time.time() - pos.time
    hold_minutes = hold_seconds / 60

    if hold_minutes >= cfg.MAX_HOLD_MINUTES:
        if close_position(pos.ticket):
            print(
                f"[EA] ⏰ ปิด #{pos.ticket} {pos_dir} "
                f"— ถือเกิน {cfg.MAX_HOLD_MINUTES} นาที "
                f"P/L: ${profit_usd:+.2f}"
            )
            return {
                "ticket": pos.ticket,
                "pnl": profit_usd,
                "reason": "TIMEOUT",
                "direction": pos_dir,
                "entry": entry_price,
                "exit": current_price,
            }

    # ── 3) Smart Profit Taking ────────────────────────────

    # 3a) ถึงเป้า $20 (extended) → ปิดทันที
    if profit_usd >= cfg.EXTENDED_PROFIT_USD:
        return _force_close(pos, "TARGET_20")

    # 3b) ถึงเป้า $10 แล้ว: ดูโอกาส
    if profit_usd >= cfg.TARGET_PROFIT_USD:
        if not trend_aligned:
            # Trend อ่อนหรือไม่ตรงทิศ → เก็บกำไร $10
            return _force_close(pos, "TARGET_10")
        else:
            # Trend ยังแรง → ปล่อยไปต่อถึง $20
            # ล็อกกำไร 70% ด้วย aggressive trailing
            lock_dist = profit_dist * cfg.AGGR_TRAIL_PCT
            if is_buy:
                aggr_sl = entry_price + lock_dist
                if pos.sl < aggr_sl:
                    if modify_sl(pos.ticket, round(aggr_sl, 2)):
                        lock_usd = lock_dist * cfg.LOT_SIZE * 100
                        print(
                            f"[EA] 🚀 #{pos.ticket} Aggressive Trail "
                            f"→ {aggr_sl:.2f} (lock ${lock_usd:.1f}, "
                            f"P/L: ${profit_usd:.1f}, รอถึง $20)"
                        )
            else:
                aggr_sl = entry_price - lock_dist
                if pos.sl == 0 or pos.sl > aggr_sl:
                    if modify_sl(pos.ticket, round(aggr_sl, 2)):
                        lock_usd = lock_dist * cfg.LOT_SIZE * 100
                        print(
                            f"[EA] 🚀 #{pos.ticket} Aggressive Trail "
                            f"→ {aggr_sl:.2f} (lock ${lock_usd:.1f}, "
                            f"P/L: ${profit_usd:.1f}, รอถึง $20)"
                        )
            return None   # ปล่อยไปต่อ

    # ── 4) Trailing Stop (ปกติ) ───────────────────────────
    if profit_dist >= cfg.TRAIL_TRIGGER:
        if is_buy:
            min_sl = entry_price + cfg.TRAIL_LOCK
            trail_sl = current_price - (cfg.TRAIL_STEP * 2)
            new_sl = max(trail_sl, min_sl)
            if pos.sl < new_sl:
                if modify_sl(pos.ticket, round(new_sl, 2)):
                    print(
                        f"[EA] 📈 #{pos.ticket} Trail SL → {new_sl:.2f} "
                        f"(lock ${new_sl - entry_price:.2f})"
                    )
        else:
            min_sl = entry_price - cfg.TRAIL_LOCK
            trail_sl = current_price + (cfg.TRAIL_STEP * 2)
            new_sl = min(trail_sl, min_sl)
            if pos.sl == 0 or pos.sl > new_sl:
                if modify_sl(pos.ticket, round(new_sl, 2)):
                    print(
                        f"[EA] 📉 #{pos.ticket} Trail SL → {new_sl:.2f} "
                        f"(lock ${entry_price - new_sl:.2f})"
                    )

    # ── 5) Breakeven ──────────────────────────────────────
    elif profit_dist >= cfg.BE_TRIGGER:
        if is_buy:
            be_level = entry_price + cfg.BE_OFFSET
            if pos.sl < be_level:
                if modify_sl(pos.ticket, round(be_level, 2)):
                    print(f"[EA] 🔒 #{pos.ticket} BE → {be_level:.2f}")
        else:
            be_level = entry_price - cfg.BE_OFFSET
            if pos.sl == 0 or pos.sl > be_level:
                if modify_sl(pos.ticket, round(be_level, 2)):
                    print(f"[EA] 🔒 #{pos.ticket} BE → {be_level:.2f}")

    return None


def count_positions_by_direction(direction: str) -> int:
    """นับจำนวน position ตามทิศ (BUY/SELL)"""
    positions = get_ea_positions(cfg.SYMBOL)
    mt5_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
    return sum(1 for p in positions if p.type == mt5_type)


def get_min_profit() -> float:
    """ดึงกำไรต่ำสุดจาก position ทั้งหมด"""
    positions = get_ea_positions(cfg.SYMBOL)
    if not positions:
        return 0.0
    return min(p.profit for p in positions)


def get_total_profit() -> float:
    """ดึงกำไรรวมทุก position"""
    positions = get_ea_positions(cfg.SYMBOL)
    return sum(p.profit for p in positions)
