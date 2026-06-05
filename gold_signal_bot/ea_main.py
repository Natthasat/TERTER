# ============================================================
# ea_main.py — Gold Speed Scalp v2 — Main EA Loop
# ============================================================
# เข้าเร็ว ออกเร็ว ถือ 1-15 นาที ทั้งวัน
# 0.02 lot × สูงสุด 5 ไม้ (ตามความมั่นใจ)
# ทุน $200 | Protection: $20/day max loss
# ============================================================

from __future__ import annotations
import time
from datetime import datetime, timezone, timedelta

import MetaTrader5 as mt5
import ea_config as cfg
import config                     # Telegram settings

from mt5_data import connect_mt5, disconnect_mt5
from notifier import broadcast_text

from ea_strategy import (
    get_data, get_trend, check_entry,
    get_session_params, calculate_confidence,
    get_latest_bar_time,
)
from order_executor import (
    open_buy, open_sell, close_all,
    get_ea_positions, get_spread, get_account_info,
    get_deal_result, price_to_usd,
)
from position_manager import manage_positions, get_min_profit
from risk_manager import RiskManager


# ─── Helpers ───────────────────────────────────────────────
def _thai_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=7)


def _notify(msg: str):
    """ส่ง Telegram แบบ fire-and-forget"""
    try:
        broadcast_text(cfg.TELEGRAM_BOT_TOKEN, cfg.TELEGRAM_CHAT_IDS, msg)
    except Exception:
        pass


# ─── Telegram Messages ────────────────────────────────────
def _msg_open(
    direction: str, price: float, sl: float, tp: float,
    confidence: int, session: str, pos_count: int,
) -> str:
    """สร้างข้อความแจ้งเปิดเทรด"""
    icon = "🟢" if direction == "BUY" else "🔴"
    conf_bar = "🟢" * confidence + "⚪" * (5 - confidence)

    sl_dist = abs(price - sl)
    tp_dist = abs(tp - price)
    sl_usd = price_to_usd(sl_dist)
    tp_usd = price_to_usd(tp_dist)

    return (
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"  {icon} EA {direction} GOLD 📍 {price:.2f}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"🎰 Lot: {cfg.LOT_SIZE} | ไม้ #{pos_count}/{cfg.MAX_POSITIONS}\n"
        f"💪 มั่นใจ: {conf_bar} ({confidence}/5)\n"
        f"🕐 Session: {session}\n"
        f"\n"
        f"🛑 SL: {sl:.2f}  (-${sl_usd:.2f})\n"
        f"🎯 TP: {tp:.2f}  (+${tp_usd:.2f})\n"
        f"\n"
        f"⏰ {_thai_now():%d/%m/%Y %H:%M:%S} TH\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━"
    )


def _msg_close(info: dict, risk: RiskManager = None) -> str:
    """สร้างข้อความแจ้งปิดเทรด พร้อมสรุปยอดรวม"""
    pnl = info["pnl"]
    icon = "✅" if pnl >= 0 else "❌"
    reason_th = {
        "REVERSE": "🔄 trend กลับทิศ",
        "TIMEOUT": "⏰ ถือเกินเวลา",
        "SL_HIT":  "🛑 SL โดน",
        "TP_HIT":  "🎯 TP โดน",
        "MANUAL":  "👤 ปิดเอง",
        "TARGET_10":    "🎯 ถึงเป้า $10",
        "TARGET_20":    "🎯 ถึงเป้า $20",
        "TOTAL_TARGET": "💰 กำไรรวม $30+",
    }.get(info.get("reason", ""), info.get("reason", ""))

    msg = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{icon} ปิด {info.get('direction', '?')} GOLD\n"
        f"   Entry: {info.get('entry', 0):.2f} → Exit: {info.get('exit', 0):.2f}\n"
        f"   P/L: ${pnl:+.2f}  ({reason_th})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    # เพิ่มสรุปยอดรวม
    if risk is not None:
        s = risk.get_status()
        acct = get_account_info()
        balance = acct.get("balance", 0)
        equity = acct.get("equity", balance)
        pnl_icon = "📈" if s["daily_pnl"] >= 0 else "📉"
        msg += (
            f"\n\n"
            f"{pnl_icon} สรุปวันนี้:\n"
            f"   เทรด: {s['daily_trades']} ไม้ "
            f"(✅{s['daily_wins']} ❌{s['daily_losses']})\n"
            f"   P/L วันนี้: ${s['daily_pnl']:+.2f}\n"
            f"   WR: {s['wr']:.1f}%\n"
            f"\n"
            f"💰 Balance: ${balance:.2f}\n"
            f"💎 Equity: ${equity:.2f}\n"
            f"   ⏰ {_thai_now():%H:%M:%S} TH\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    else:
        msg += f"\n   ⏰ {_thai_now():%H:%M:%S} TH"

    return msg


def _msg_daily_summary(risk: RiskManager) -> str:
    """สรุปผลประจำวัน"""
    s = risk.get_status()
    tn = _thai_now()
    icon = "📈" if s["daily_pnl"] >= 0 else "📉"

    return (
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"  {icon} สรุปวัน {tn:%d/%m/%Y}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"💰 P/L: ${s['daily_pnl']:+.2f}\n"
        f"📊 เทรด: {s['daily_trades']} ไม้\n"
        f"✅ ชนะ: {s['daily_wins']}  ❌ แพ้: {s['daily_losses']}\n"
        f"🎯 WR: {s['wr']:.1f}%\n"
        f"\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━"
    )


# ─── Main EA Loop ─────────────────────────────────────────
def run_ea() -> None:
    """Main loop ของ EA Gold Speed Scalp v2"""

    if not connect_mt5():
        print("[EA] ❌ เชื่อมต่อ MT5 ไม่ได้")
        return

    risk = RiskManager()
    last_bar_time: int | None = None
    cached_trend: str | None = None
    known_tickets: set[int] = set()
    last_entry_time: float = 0              # ★ กันเปิดถี่เกินไป

    # ── Startup banner ──
    tn = _thai_now()
    acct = get_account_info()
    balance = acct.get("balance", cfg.CAPITAL)

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🤖 EA Gold Speed Scalp v2 — เริ่มทำงาน")
    print(f"   Symbol : {cfg.SYMBOL}")
    print(f"   Mode   : M1 Pure (ไม่พึ่ง TF อื่น)")
    print(f"   Lot    : {cfg.LOT_SIZE} × max {cfg.MAX_POSITIONS} ไม้")
    print(f"   Balance: ${balance:.2f}")
    print(f"   Max Loss: ${cfg.MAX_DAILY_LOSS}/day")
    print(f"   เวลา  : {tn:%H:%M} TH")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    _notify(
        f"🤖 EA Gold Scalp v2 เริ่มทำงาน\n"
        f"   Lot: {cfg.LOT_SIZE} × max {cfg.MAX_POSITIONS}\n"
        f"   Balance: ${balance:.2f}\n"
        f"   ⏰ {tn:%d/%m/%Y %H:%M} TH"
    )

    try:
        while True:
            time.sleep(1)

            # ── A) Manage existing positions (ทุกวินาที) ────
            closed = manage_positions(cached_trend)
            for c in closed:
                risk.record_trade(c["pnl"], c["pnl"] >= 0)
                _notify(_msg_close(c, risk))
                known_tickets.discard(c["ticket"])

            # ── B) Detect broker-closed positions (SL/TP) ──
            current_positions = get_ea_positions(cfg.SYMBOL)
            current_tickets = {p.ticket for p in current_positions}
            broker_closed = known_tickets - current_tickets

            for ticket in broker_closed:
                deal = get_deal_result(ticket)
                if deal:
                    pnl = deal["pnl"]
                    is_win = pnl >= 0
                    risk.record_trade(pnl, is_win)

                    reason = "TP_HIT" if is_win else "SL_HIT"
                    icon = "🎯" if is_win else "🛑"
                    print(
                        f"[EA] {icon} #{ticket} ปิดโดยโบรก "
                        f"({reason}) P/L: ${pnl:+.2f}"
                    )

                    # สร้าง info dict แล้วใช้ _msg_close เดียวกัน
                    broker_info = {
                        "pnl": pnl,
                        "direction": deal.get("direction", "?"),
                        "entry": deal.get("entry", 0),
                        "exit": deal.get("exit", 0),
                        "reason": reason,
                        "ticket": ticket,
                    }
                    _notify(_msg_close(broker_info, risk))

            known_tickets = current_tickets.copy()

            # ── C) New M1 bar? ─────────────────────────────
            bar_time = get_latest_bar_time(cfg.SYMBOL, cfg.TF_ENTRY)
            if bar_time is None or bar_time == last_bar_time:
                continue
            last_bar_time = bar_time
            tn = _thai_now()
            print(f"[{tn:%H:%M:%S}] ── New M1 bar: {bar_time} ──")

            # ── D) Risk check ──────────────────────────────
            can, reason = risk.can_trade()
            if not can:
                print(f"  ✘ Risk block: {reason}")
                continue

            # ── E) Spread check ────────────────────────────
            spread = get_spread()
            if spread > cfg.MAX_SPREAD:
                print(f"  ✘ Spread too high: {spread:.2f} > {cfg.MAX_SPREAD}")
                continue
            print(f"  Spread: {spread:.2f} ✓")

            # ── E2) Min gap between entries (3 นาที) ───────
            gap = time.time() - last_entry_time
            if gap < 180:
                print(f"  ✘ Entry gap: {gap:.0f}s < 180s")
                continue

            # ── F) Get M1 data only ─────────────────────
            df_m1 = get_data(cfg.SYMBOL, cfg.TF_ENTRY, cfg.NUM_BARS)

            if df_m1 is None:
                print(f"  ✘ No M1 data")
                continue

            # ── G) M1 trend ────────────────────────────────
            cached_trend = get_trend(df_m1)
            if cached_trend is None:
                print(f"  ✘ No trend (EMA flat/cross)")
                continue
            print(f"  Trend: {cached_trend}")

            # ── I) Check M1 entry signal ───────────────────
            signal = check_entry(df_m1, cached_trend)
            if signal is None:
                # แสดงเหตุผลที่ไม่มี signal
                last = df_m1.iloc[-1]
                prev = df_m1.iloc[-2]
                rsi = last['rsi']
                body_ratio = abs(last['close'] - last['open']) / max(last['high'] - last['low'], 0.01)
                print(f"  ✘ No entry signal (RSI={rsi:.1f}, body={body_ratio:.2f}, trend={cached_trend})")
                continue
            print(f"  ★ Signal: {signal}!")

            # ── J) Confidence level (M1 pure) ──────────────
            session_tp, session_sl, session_name = get_session_params()
            confidence = calculate_confidence(
                cached_trend, signal,
                df_m1, session_name,
            )

            min_conf = getattr(cfg, "MIN_CONFIDENCE", 4)
            if confidence < min_conf:
                print(f"  ✘ Confidence {confidence}/5 < {min_conf} — ข้ามสัญญาณ")
                continue

            # ── K) Position count check ────────────────────
            positions = get_ea_positions(cfg.SYMBOL)
            current_count = len(positions)
            max_allowed = min(confidence, cfg.MAX_POSITIONS)

            if current_count >= max_allowed:
                continue

            # ── L) Adding check (ไม้เก่าต้องกำไรก่อน) ─────
            if current_count > 0:
                # ต้องไม่มีไม้ฝั่งตรงข้าม
                opposite = [
                    p for p in positions
                    if (p.type == mt5.ORDER_TYPE_BUY and signal == "SELL")
                    or (p.type == mt5.ORDER_TYPE_SELL and signal == "BUY")
                ]
                if opposite:
                    continue   # รอ position_manager ปิดฝั่งเก่าก่อน

                # ไม้เก่าต้องกำไรขั้นต่ำ
                min_profit = get_min_profit()
                required = (
                    cfg.ADD_POS_45_MIN_PROFIT
                    if current_count >= 2
                    else cfg.ADD_POSITION_MIN_PROFIT
                )
                if min_profit < required:
                    continue

            # ── M) Calculate SL / TP ──────────────────────
            tick = mt5.symbol_info_tick(cfg.SYMBOL)
            if tick is None:
                continue

            if signal == "BUY":
                entry = tick.ask
                sl = round(entry - session_sl, 2)
                tp = round(entry + cfg.BROKER_TP_DISTANCE, 2)
            else:
                entry = tick.bid
                sl = round(entry + session_sl, 2)
                tp = round(entry - cfg.BROKER_TP_DISTANCE, 2)

            # ── N) Open position ──────────────────────────
            if signal == "BUY":
                result = open_buy(
                    cfg.SYMBOL, cfg.LOT_SIZE, sl, tp,
                    f"Scalp #{current_count + 1} C{confidence}",
                )
            else:
                result = open_sell(
                    cfg.SYMBOL, cfg.LOT_SIZE, sl, tp,
                    f"Scalp #{current_count + 1} C{confidence}",
                )

            if result:
                known_tickets.add(result["ticket"])
                last_entry_time = time.time()        # ★ บันทึกเวลาเปิดล่าสุด

                tn = _thai_now()
                print(
                    f"[EA] {tn:%H:%M:%S} "
                    f"{'🟢' if signal == 'BUY' else '🔴'} "
                    f"{signal} @ {result['price']:.2f}  "
                    f"SL={sl:.2f} TP={tp:.2f}  "
                    f"Conf={confidence} [{session_name}] "
                    f"ไม้ #{current_count + 1}"
                )

                msg = _msg_open(
                    signal, result["price"], sl, tp,
                    confidence, session_name, current_count + 1,
                )
                _notify(msg)

    except KeyboardInterrupt:
        print("\n[EA] หยุดทำงาน (Ctrl+C)")

        # สรุปผลวันนี้
        positions = get_ea_positions(cfg.SYMBOL)
        if positions:
            print(f"[EA] ⚠️ ยังมี {len(positions)} position เปิดอยู่")
            print("     (ไม่ปิดอัตโนมัติ — จัดการเองใน MT5)")

        status = risk.get_status()
        print(
            f"[EA] 📊 วันนี้: {status['daily_trades']} trades | "
            f"W:{status['daily_wins']} L:{status['daily_losses']} | "
            f"P/L: ${status['daily_pnl']:+.2f}"
        )

        _notify(_msg_daily_summary(risk))

    except Exception as e:
        print(f"[EA] ❌ Error: {e}")
        _notify(f"❌ EA Error: {e}")

    finally:
        disconnect_mt5()


# ─── Entry Point ──────────────────────────────────────────
if __name__ == "__main__":
    run_ea()
