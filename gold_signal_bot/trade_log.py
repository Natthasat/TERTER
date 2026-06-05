# ============================================================
# trade_log.py — บันทึกสัญญาณจริง + ติดตามผล WIN/LOSS
# ============================================================
# - log_trade()      : บันทึกเมื่อ bot ส่งสัญญาณ
# - update_results() : เช็คราคาย้อนหลังว่า SL/TP โดนหรือยัง
# - get_summary()    : สรุป WR จริง
# ============================================================

from __future__ import annotations
import csv
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

LOG_FILE = Path(__file__).parent / "trade_log.csv"

COLUMNS = [
    "id", "signal", "entry_time", "entry_price",
    "sl", "tp1", "tp2", "tp3",
    "exit_time", "exit_price",
    "tp1_hit", "tp2_hit", "tp3_hit",
    "result", "pnl",
]


def _ensure_file() -> None:
    """สร้างไฟล์ CSV ถ้ายังไม่มี."""
    if not LOG_FILE.exists():
        with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(COLUMNS)


def log_trade(
    signal: str,
    entry_price: float,
    sl: float,
    tp1: float,
    tp2: float,
    tp3: float,
    entry_time: str = "",
) -> int:
    """บันทึกเทรดใหม่ลง CSV → return trade_id."""
    _ensure_file()

    # หา id ถัดไป
    trades = _read_all()
    next_id = max((t["id"] for t in trades), default=0) + 1

    if not entry_time:
        tn = datetime.now(timezone.utc) + timedelta(hours=7)
        entry_time = tn.strftime("%Y-%m-%d %H:%M")

    row = {
        "id": next_id,
        "signal": signal,
        "entry_time": entry_time,
        "entry_price": f"{entry_price:.2f}",
        "sl": f"{sl:.2f}",
        "tp1": f"{tp1:.2f}",
        "tp2": f"{tp2:.2f}",
        "tp3": f"{tp3:.2f}",
        "exit_time": "",
        "exit_price": "",
        "tp1_hit": "",
        "tp2_hit": "",
        "tp3_hit": "",
        "result": "OPEN",
        "pnl": "",
    }

    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writerow(row)

    print(f"[TradeLog] #{next_id} {signal} @ {entry_price:.2f} — logged ✓")
    return next_id


def _read_all() -> list[dict]:
    """อ่านเทรดทั้งหมดจาก CSV."""
    _ensure_file()
    trades = []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["id"] = int(row["id"])
            trades.append(row)
    return trades


def _write_all(trades: list[dict]) -> None:
    """เขียนทับ CSV ทั้งหมด."""
    with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(trades)


def update_results(get_ohlc_func, symbol: str, timeframe, num_bars: int = 500) -> int:
    """เช็คเทรดที่ยัง OPEN — ดูว่า SL/TP โดนหรือยัง.

    Parameters
    ----------
    get_ohlc_func : callable  (symbol, timeframe, num_bars) -> DataFrame
    symbol : str
    timeframe : MT5 timeframe constant
    num_bars : int

    Returns
    -------
    จำนวนเทรดที่อัปเดตสถานะ
    """
    trades = _read_all()
    open_trades = [t for t in trades if t["result"] == "OPEN"]
    if not open_trades:
        return 0

    df = get_ohlc_func(symbol, timeframe, num_bars)
    if df is None or df.empty:
        return 0

    updated = 0
    for t in trades:
        if t["result"] != "OPEN":
            continue

        entry_price = float(t["entry_price"])
        sl = float(t["sl"])
        tp1 = float(t["tp1"])
        tp2 = float(t["tp2"])
        tp3 = float(t["tp3"])
        sig = t["signal"]
        entry_str = t["entry_time"]

        # หาแท่งหลังจาก entry
        mask = df["time"] > entry_str
        bars_after = df[mask]
        if bars_after.empty:
            continue

        tp1_hit = False
        tp2_hit = False
        tp3_hit = False
        sl_hit = False
        exit_time = ""
        exit_price = 0.0

        for _, bar in bars_after.iterrows():
            if sig == "BUY":
                if bar["low"] <= sl:
                    sl_hit = True
                    exit_price = sl
                    exit_time = str(bar["time"])
                    break
                if bar["high"] >= tp1:
                    tp1_hit = True
                if bar["high"] >= tp2:
                    tp2_hit = True
                if bar["high"] >= tp3:
                    tp3_hit = True
                    exit_price = tp3
                    exit_time = str(bar["time"])
                    break
            else:  # SELL
                if bar["high"] >= sl:
                    sl_hit = True
                    exit_price = sl
                    exit_time = str(bar["time"])
                    break
                if bar["low"] <= tp1:
                    tp1_hit = True
                if bar["low"] <= tp2:
                    tp2_hit = True
                if bar["low"] <= tp3:
                    tp3_hit = True
                    exit_price = tp3
                    exit_time = str(bar["time"])
                    break

        # ตัดสินผล
        if sl_hit:
            t["result"] = "LOSS"
            t["exit_time"] = exit_time
            t["exit_price"] = f"{exit_price:.2f}"
            pnl = (exit_price - entry_price) if sig == "BUY" else (entry_price - exit_price)
            t["pnl"] = f"{pnl:.2f}"
            t["tp1_hit"] = "1" if tp1_hit else "0"
            t["tp2_hit"] = "0"
            t["tp3_hit"] = "0"
            updated += 1
        elif tp3_hit:
            t["result"] = "WIN"
            t["exit_time"] = exit_time
            t["exit_price"] = f"{exit_price:.2f}"
            pnl = (exit_price - entry_price) if sig == "BUY" else (entry_price - exit_price)
            t["pnl"] = f"{pnl:.2f}"
            t["tp1_hit"] = "1"
            t["tp2_hit"] = "1"
            t["tp3_hit"] = "1"
            updated += 1
        elif tp1_hit or tp2_hit:
            # TP1/TP2 hit แต่ยังไม่ถึง TP3 — ยังเปิดอยู่
            t["tp1_hit"] = "1" if tp1_hit else "0"
            t["tp2_hit"] = "1" if tp2_hit else "0"
            t["tp3_hit"] = "0"
        # else: ยังไม่มีอะไรโดน — ยัง OPEN

    if updated > 0:
        _write_all(trades)
        print(f"[TradeLog] อัปเดต {updated} เทรด")

    return updated


def get_summary() -> dict:
    """สรุปผลเทรดทั้งหมด."""
    trades = _read_all()
    total = len(trades)
    if total == 0:
        return {"total": 0, "open": 0, "closed": 0, "wins": 0, "losses": 0,
                "wr": 0, "net_pnl": 0, "tp1_rate": 0, "tp2_rate": 0, "trades": []}

    open_t = sum(1 for t in trades if t["result"] == "OPEN")
    wins = sum(1 for t in trades if t["result"] == "WIN")
    losses = sum(1 for t in trades if t["result"] == "LOSS")
    closed = wins + losses
    wr = wins / closed * 100 if closed > 0 else 0

    net_pnl = sum(float(t["pnl"]) for t in trades if t["pnl"])

    # TP hit rates (จากเทรดที่ปิดแล้ว)
    closed_trades = [t for t in trades if t["result"] in ("WIN", "LOSS")]
    tp1_hits = sum(1 for t in closed_trades if t.get("tp1_hit") == "1")
    tp2_hits = sum(1 for t in closed_trades if t.get("tp2_hit") == "1")
    tp1_rate = tp1_hits / closed * 100 if closed > 0 else 0
    tp2_rate = tp2_hits / closed * 100 if closed > 0 else 0

    return {
        "total": total,
        "open": open_t,
        "closed": closed,
        "wins": wins,
        "losses": losses,
        "wr": wr,
        "net_pnl": net_pnl,
        "tp1_rate": tp1_rate,
        "tp2_rate": tp2_rate,
        "trades": trades,
    }


def format_summary() -> str:
    """สรุปผลเป็นข้อความสำหรับ Telegram."""
    s = get_summary()

    if s["total"] == 0:
        return "📋 ยังไม่มีเทรดในระบบ"

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        "📋 Trade Log — ผลเทรดจริง",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📊 รวม     : {s['total']} เทรด",
        f"🟡 OPEN    : {s['open']}",
        f"✅ WIN     : {s['wins']}",
        f"❌ LOSS    : {s['losses']}",
    ]

    if s["closed"] > 0:
        lines += [
            "",
            f"🎯 Win Rate : {s['wr']:.1f}%",
            f"💰 Net P/L  : {s['net_pnl']:+.1f} pts",
            f"📈 TP1 Hit  : {s['tp1_rate']:.0f}%",
            f"📈 TP2 Hit  : {s['tp2_rate']:.0f}%",
        ]

    # แสดง 5 เทรดล่าสุด
    recent = s["trades"][-5:]
    if recent:
        lines += ["", "── 5 เทรดล่าสุด ──"]
        for t in reversed(recent):
            icon = "✅" if t["result"] == "WIN" else ("❌" if t["result"] == "LOSS" else "🟡")
            pnl_str = f" {float(t['pnl']):+.0f}" if t["pnl"] else ""
            lines.append(
                f"{icon} #{t['id']} {t['signal']} @ {float(t['entry_price']):.0f}"
                f" → {t['result']}{pnl_str}"
            )

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)
