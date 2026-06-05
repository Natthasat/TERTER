# ============================================================
# backtester.py — Backtest Engine สำหรับ Gold Strategy
# ============================================================
#
#  Logic:
#    - วนทีละแท่ง เช็ค signal (BUY / SELL)
#    - คำนวณ SL / TP จาก ATR
#    - วนแท่งถัดไปจนชน SL หรือ TP
#    - เก็บทุก trade แล้วคำนวณสถิติ
#
# ============================================================

from __future__ import annotations
from dataclasses import dataclass, field
import pandas as pd
from strategy import FilterConfig
from filters import apply_all_filters


# ─── Trade Record ────────────────────────────────────────────
@dataclass
class Trade:
    direction: str          # "BUY" / "SELL"
    entry_time: object
    entry_price: float
    sl: float
    tp: float
    exit_time: object = None
    exit_price: float = 0.0
    pnl: float = 0.0       # จุด (price diff) ไม่ใช่ dollar
    result: str = ""        # "WIN" / "LOSS"


# ─── Backtest Result ────────────────────────────────────────
@dataclass
class BacktestResult:
    trades: list[Trade] = field(default_factory=list)
    risk_per_trade: float = 0.0   # dollar (ใช้แสดงผลเท่านั้น)

    # ── Computed Metrics ──
    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def wins(self) -> int:
        return sum(1 for t in self.trades if t.result == "WIN")

    @property
    def losses(self) -> int:
        return sum(1 for t in self.trades if t.result == "LOSS")

    @property
    def win_rate(self) -> float:
        return (self.wins / self.total_trades * 100) if self.total_trades else 0.0

    @property
    def gross_profit(self) -> float:
        return sum(t.pnl for t in self.trades if t.pnl > 0)

    @property
    def gross_loss(self) -> float:
        return abs(sum(t.pnl for t in self.trades if t.pnl < 0))

    @property
    def profit_factor(self) -> float:
        return (self.gross_profit / self.gross_loss) if self.gross_loss else float("inf")

    @property
    def net_pnl(self) -> float:
        return sum(t.pnl for t in self.trades)

    @property
    def max_consecutive_losses(self) -> int:
        max_streak = 0
        streak = 0
        for t in self.trades:
            if t.result == "LOSS":
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        return max_streak

    @property
    def max_drawdown(self) -> float:
        """Max drawdown วัดจาก cumulative PnL (จุด)"""
        if not self.trades:
            return 0.0
        cum = 0.0
        peak = 0.0
        dd = 0.0
        for t in self.trades:
            cum += t.pnl
            if cum > peak:
                peak = cum
            drawdown = peak - cum
            if drawdown > dd:
                dd = drawdown
        return dd

    @property
    def avg_win(self) -> float:
        wins = [t.pnl for t in self.trades if t.result == "WIN"]
        return (sum(wins) / len(wins)) if wins else 0.0

    @property
    def avg_loss(self) -> float:
        losses = [t.pnl for t in self.trades if t.result == "LOSS"]
        return (sum(losses) / len(losses)) if losses else 0.0

    @property
    def reward_risk_ratio(self) -> float:
        return (self.avg_win / abs(self.avg_loss)) if self.avg_loss else float("inf")


# ─── Signal Evaluation (per-bar) ─────────────────────────────
def _raw_signal(curr: pd.Series, prev: pd.Series) -> str | None:
    """เช็ค raw signal (EMA + RSI + pullback) — ไม่มี filter"""
    price    = curr["close"]
    ema_fast = curr["ema_fast"]
    ema_slow = curr["ema_slow"]
    rsi      = curr["rsi"]

    # BUY
    if (price > ema_fast > ema_slow
            and rsi > 50
            and prev["low"] <= prev["ema_fast"]):
        return "BUY"

    # SELL
    if (price < ema_fast < ema_slow
            and rsi < 50
            and prev["high"] >= prev["ema_fast"]):
        return "SELL"

    return None


def _check_signal(
    curr: pd.Series,
    prev: pd.Series,
    avg_atr: float,
    fc: FilterConfig | None = None,
) -> tuple[str | None, str]:
    """เช็ค signal + ผ่าน filter
    Returns (signal, filter_reason)
    """
    signal = _raw_signal(curr, prev)
    if signal is None:
        return None, ""

    if fc is None:
        return signal, ""

    passed, reason = apply_all_filters(
        curr, avg_atr,
        use_session_filter=fc.use_session_filter,
        use_adx_filter=fc.use_adx_filter,
        use_body_filter=fc.use_body_filter,
        use_anti_chase=fc.use_anti_chase,
        use_volatility_guard=fc.use_volatility_guard,
        session_start_utc=fc.session_start_utc,
        session_end_utc=fc.session_end_utc,
        adx_threshold=fc.adx_threshold,
        min_body_ratio=fc.min_body_ratio,
        max_distance_atr=fc.max_distance_atr,
        max_atr_ratio=fc.max_atr_ratio,
    )

    if not passed:
        return None, reason

    return signal, ""


# ─── Core Backtest ───────────────────────────────────────────
def run_backtest(
    df: pd.DataFrame,
    atr_sl_mult: float = 1.0,
    atr_tp_mult: float = 2.0,
    risk_per_trade: float = 100.0,
    filter_config: FilterConfig | None = None,
) -> BacktestResult:
    """รัน backtest บน DataFrame ที่มี indicator + ATR + ADX พร้อมแล้ว

    Parameters
    ----------
    df : pd.DataFrame
        ต้องมี: time, open, high, low, close, ema_fast, ema_slow,
        rsi, atr, adx, atr_avg
    atr_sl_mult : float       ตัวคูณ ATR สำหรับ Stop-Loss
    atr_tp_mult : float       ตัวคูณ ATR สำหรับ Take-Profit
    risk_per_trade : float    risk คงที่ต่อไม้ (สำหรับแสดงผล)
    filter_config : FilterConfig | None
        Gold-specific filters — None = ไม่ใช้ filter

    Returns
    -------
    BacktestResult
    """
    result = BacktestResult(risk_per_trade=risk_per_trade)
    filtered_counts: dict[str, int] = {}   # นับว่า filter ไหน block กี่ครั้ง
    n = len(df)

    i = 2  # เริ่มจากแท่งที่ 2 (ต้องมี prev)
    while i < n:
        curr = df.iloc[i]
        prev = df.iloc[i - 1]

        avg_atr = curr.get("atr_avg", curr["atr"])
        signal, reason = _check_signal(curr, prev, avg_atr, filter_config)

        if reason:
            filtered_counts[reason] = filtered_counts.get(reason, 0) + 1

        if signal is None:
            i += 1
            continue

        # ── คำนวณ SL / TP จาก ATR ──
        atr = curr["atr"]
        entry_price = curr["close"]

        if signal == "BUY":
            sl = entry_price - atr * atr_sl_mult
            tp = entry_price + atr * atr_tp_mult
        else:  # SELL
            sl = entry_price + atr * atr_sl_mult
            tp = entry_price - atr * atr_tp_mult

        trade = Trade(
            direction=signal,
            entry_time=curr["time"],
            entry_price=entry_price,
            sl=sl,
            tp=tp,
        )

        # ── วนแท่งถัดไป จนชน SL / TP ──
        j = i + 1
        while j < n:
            bar = df.iloc[j]

            if signal == "BUY":
                # ถ้า low ≤ SL → LOSS (เช็คก่อน เพื่อ worst-case)
                if bar["low"] <= sl:
                    trade.exit_price = sl
                    trade.pnl = sl - entry_price
                    trade.result = "LOSS"
                    trade.exit_time = bar["time"]
                    break
                # ถ้า high ≥ TP → WIN
                if bar["high"] >= tp:
                    trade.exit_price = tp
                    trade.pnl = tp - entry_price
                    trade.result = "WIN"
                    trade.exit_time = bar["time"]
                    break

            else:  # SELL
                # ถ้า high ≥ SL → LOSS
                if bar["high"] >= sl:
                    trade.exit_price = sl
                    trade.pnl = entry_price - sl
                    trade.result = "LOSS"
                    trade.exit_time = bar["time"]
                    break
                # ถ้า low ≤ TP → WIN
                if bar["low"] <= tp:
                    trade.exit_price = tp
                    trade.pnl = entry_price - tp
                    trade.result = "WIN"
                    trade.exit_time = bar["time"]
                    break

            j += 1
        else:
            # ถ้าข้อมูลหมดก่อนชน SL/TP → ปิดด้วยราคาปิดแท่งสุดท้าย
            last_bar = df.iloc[-1]
            trade.exit_time = last_bar["time"]
            trade.exit_price = last_bar["close"]
            if signal == "BUY":
                trade.pnl = last_bar["close"] - entry_price
            else:
                trade.pnl = entry_price - last_bar["close"]
            trade.result = "WIN" if trade.pnl > 0 else "LOSS"

        result.trades.append(trade)

        # ── ข้ามไปแท่งหลัง exit (ไม่เปิดซ้อน) ──
        i = j + 1

    # เก็บสถิติ filter
    result.filtered_counts = filtered_counts  # type: ignore[attr-defined]

    return result


# ─── Pretty Print ────────────────────────────────────────────
def print_report(res: BacktestResult, symbol: str = "", tf_label: str = "") -> None:
    """พิมพ์สรุปผล backtest"""
    header = f"BACKTEST REPORT  {symbol} {tf_label}".strip()
    print()
    print("=" * 60)
    print(f"  {header}")
    print("=" * 60)
    print(f"  Total Trades        : {res.total_trades}")
    print(f"  Wins / Losses       : {res.wins} / {res.losses}")
    print(f"  Win Rate            : {res.win_rate:.1f} %")
    print(f"  Profit Factor       : {res.profit_factor:.2f}")
    print(f"  Reward:Risk Ratio   : {res.reward_risk_ratio:.2f}")
    print(f"  Avg Win  (pts)      : {res.avg_win:.2f}")
    print(f"  Avg Loss (pts)      : {res.avg_loss:.2f}")
    print(f"  Net PnL  (pts)      : {res.net_pnl:.2f}")
    print(f"  Max Drawdown (pts)  : {res.max_drawdown:.2f}")
    print(f"  Max Consec. Losses  : {res.max_consecutive_losses}")
    print("=" * 60)

    # ── Filter Statistics ──
    fc = getattr(res, "filtered_counts", {})
    if fc:
        print("\n  ── Signals Blocked by Filters ──")
        for name, count in sorted(fc.items(), key=lambda x: -x[1]):
            print(f"     {name:20s} : {count}")
        total_blocked = sum(fc.values())
        print(f"     {'TOTAL':20s} : {total_blocked}")

    # ── สรุปความเห็น ──
    print()
    if res.total_trades < 30:
        print("  ⚠️  จำนวน trade น้อย (<30) — ยังไม่มี statistical significance")
    if res.win_rate >= 45 and res.profit_factor >= 1.3:
        print("  ✅  Strategy มี edge — Win Rate + PF อยู่ในเกณฑ์ดี")
    elif res.profit_factor >= 1.0:
        print("  🟡  Strategy พอใช้ได้ — แต่ควรปรับ SL/TP หรือเพิ่ม filter")
    else:
        print("  ❌  Strategy ยังไม่มี edge — PF < 1.0 ขาดทุนสุทธิ")

    if res.max_consecutive_losses >= 6:
        print("  ⚠️  Loss ติดกัน ≥6 — ต้องระวังเรื่อง psychology / position sizing")
    if res.max_drawdown > 0:
        print(f"  📉  Max Drawdown = {res.max_drawdown:.2f} pts"
              f" — ควรรับได้ก่อนใช้จริง")

    print()
    print("  💡 คำแนะนำ:")
    print("     1. ลองปรับ ATR multiplier (SL/TP) เช่น 1.5×/2.5×")
    print("     2. เพิ่ม filter เช่น กรอง session (London/NY)")
    print("     3. ทดสอบ H1 vs M15 เพื่อลด noise")
    print("     4. ใช้ Walk-forward test ก่อน live")
    print()


def trades_to_dataframe(res: BacktestResult) -> pd.DataFrame:
    """แปลง list ของ Trade เป็น DataFrame เพื่อวิเคราะห์เพิ่ม"""
    rows = []
    for t in res.trades:
        rows.append({
            "direction":   t.direction,
            "entry_time":  t.entry_time,
            "entry_price": t.entry_price,
            "sl":          t.sl,
            "tp":          t.tp,
            "exit_time":   t.exit_time,
            "exit_price":  t.exit_price,
            "pnl":         t.pnl,
            "result":      t.result,
        })
    return pd.DataFrame(rows)
