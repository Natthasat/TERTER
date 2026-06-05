# ============================================================
# risk_manager.py — Risk Management for EA Gold Scalp
# ============================================================
# ทุน $200: max loss $20/วัน, แพ้ 3 ติด → พัก 15 นาที
# State บันทึกลง JSON เพื่อกัน restart
# ============================================================

from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import ea_config as cfg

STATE_FILE = Path(__file__).parent / "ea_risk_state.json"


def _thai_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=7)


class RiskManager:
    """ควบคุมความเสี่ยงทั้งหมดของ EA"""

    def __init__(self):
        self.daily_pnl: float = 0.0
        self.daily_trades: int = 0
        self.daily_wins: int = 0
        self.daily_losses: int = 0
        self.consecutive_losses: int = 0
        self.cooldown_until: datetime | None = None
        self.stopped_today: bool = False
        self.last_reset_date: str = ""
        self._load_state()

    # ─── Daily Reset ───────────────────────────────────────
    def _today_str(self) -> str:
        return _thai_now().strftime("%Y-%m-%d")

    def _check_new_day(self):
        today = self._today_str()
        if today != self.last_reset_date:
            self.reset_daily()

    def reset_daily(self):
        """รีเซ็ตสถิติวันใหม่"""
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.daily_wins = 0
        self.daily_losses = 0
        self.consecutive_losses = 0
        self.cooldown_until = None
        self.stopped_today = False
        self.last_reset_date = self._today_str()
        self._save_state()
        print(f"[Risk] 🔄 รีเซ็ตวันใหม่ {self.last_reset_date}")

    # ─── Can Trade? ────────────────────────────────────────
    def can_trade(self) -> tuple[bool, str]:
        """ตรวจว่าเปิดเทรดได้หรือไม่ → (ok, reason)"""
        self._check_new_day()

        if self.stopped_today:
            return False, "STOPPED_TODAY"

        if self.daily_pnl <= -cfg.MAX_DAILY_LOSS:
            self.stopped_today = True
            self._save_state()
            return False, f"MAX_DAILY_LOSS (-${cfg.MAX_DAILY_LOSS})"

        if self.daily_losses >= cfg.MAX_LOSSES_PER_DAY:
            self.stopped_today = True
            self._save_state()
            return False, f"MAX_LOSSES ({cfg.MAX_LOSSES_PER_DAY}/day)"

        if self.daily_trades >= cfg.MAX_DAILY_TRADES:
            return False, f"MAX_TRADES ({cfg.MAX_DAILY_TRADES}/day)"

        if self.cooldown_until:
            now = datetime.now(timezone.utc)
            if now < self.cooldown_until:
                remaining = (self.cooldown_until - now).seconds // 60 + 1
                return False, f"COOLDOWN ({remaining} min)"
            else:
                self.cooldown_until = None
                self.consecutive_losses = 0
                print("[Risk] ✅ หมดเวลาพัก — กลับมาเทรดได้")

        return True, ""

    # ─── Record Trade ──────────────────────────────────────
    def record_trade(self, pnl: float, is_win: bool):
        """บันทึกผลเทรด"""
        self._check_new_day()

        self.daily_pnl += pnl
        self.daily_trades += 1

        if is_win:
            self.daily_wins += 1
            self.consecutive_losses = 0
        else:
            self.daily_losses += 1
            self.consecutive_losses += 1

            if self.consecutive_losses >= cfg.MAX_CONSECUTIVE_LOSSES:
                self.cooldown_until = (
                    datetime.now(timezone.utc)
                    + timedelta(minutes=cfg.COOLDOWN_MINUTES)
                )
                tn = _thai_now()
                end = tn + timedelta(minutes=cfg.COOLDOWN_MINUTES)
                print(
                    f"[Risk] ⏸️ แพ้ {self.consecutive_losses} ติด "
                    f"→ พัก {cfg.COOLDOWN_MINUTES} นาที "
                    f"(ถึง {end:%H:%M} TH)"
                )

        self._save_state()

    # ─── Force Stop ────────────────────────────────────────
    def force_stop(self):
        """หยุด EA วันนี้ (จาก Telegram /ea stop)"""
        self.stopped_today = True
        self._save_state()
        print("[Risk] 🛑 EA ถูกหยุดโดยผู้ใช้")

    # ─── Status ────────────────────────────────────────────
    def get_status(self) -> dict:
        self._check_new_day()
        return {
            "daily_pnl":           round(self.daily_pnl, 2),
            "daily_trades":        self.daily_trades,
            "daily_wins":          self.daily_wins,
            "daily_losses":        self.daily_losses,
            "consecutive_losses":  self.consecutive_losses,
            "stopped":             self.stopped_today,
            "cooldown":            self.cooldown_until is not None,
            "wr": (
                round(self.daily_wins / (self.daily_wins + self.daily_losses) * 100, 1)
                if (self.daily_wins + self.daily_losses) > 0 else 0
            ),
        }

    def format_status(self) -> str:
        """สรุปสถานะเป็นข้อความ"""
        s = self.get_status()
        tn = _thai_now()

        icon = "🟢" if not s["stopped"] else "🔴"
        pnl_icon = "📈" if s["daily_pnl"] >= 0 else "📉"

        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━━━",
            f"  {icon} EA Gold Scalp Status",
            "━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            f"⏰ {tn:%d/%m/%Y %H:%M} TH",
            f"{pnl_icon} วันนี้ P/L: ${s['daily_pnl']:+.2f}",
            f"📊 เทรด: {s['daily_trades']} ไม้ "
            f"(W:{s['daily_wins']} L:{s['daily_losses']})",
            f"🎯 Win Rate: {s['wr']:.1f}%",
            "",
        ]

        if s["stopped"]:
            lines.append("🔴 EA หยุดแล้ว (จะเริ่มใหม่พรุ่งนี้)")
        elif s["cooldown"]:
            lines.append(f"⏸️ กำลังพัก (แพ้ {s['consecutive_losses']} ติด)")
        else:
            lines.append("🟢 EA กำลังทำงาน")

        lines += [
            "",
            f"💰 ทุน: ${cfg.CAPITAL}  |  Lot: {cfg.LOT_SIZE}",
            f"🛡️ Max Loss/วัน: ${cfg.MAX_DAILY_LOSS}",
            "━━━━━━━━━━━━━━━━━━━━━━━━",
        ]
        return "\n".join(lines)

    # ─── Persistence ───────────────────────────────────────
    def _save_state(self):
        data = {
            "daily_pnl":          self.daily_pnl,
            "daily_trades":       self.daily_trades,
            "daily_wins":         self.daily_wins,
            "daily_losses":       self.daily_losses,
            "consecutive_losses": self.consecutive_losses,
            "cooldown_until":     (
                self.cooldown_until.isoformat() if self.cooldown_until else None
            ),
            "stopped_today":      self.stopped_today,
            "last_reset_date":    self.last_reset_date,
        }
        try:
            STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _load_state(self):
        if not STATE_FILE.exists():
            self.last_reset_date = self._today_str()
            return
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            self.daily_pnl          = data.get("daily_pnl", 0.0)
            self.daily_trades       = data.get("daily_trades", 0)
            self.daily_wins         = data.get("daily_wins", 0)
            self.daily_losses       = data.get("daily_losses", 0)
            self.consecutive_losses = data.get("consecutive_losses", 0)
            self.stopped_today      = data.get("stopped_today", False)
            self.last_reset_date    = data.get("last_reset_date", "")
            cd = data.get("cooldown_until")
            self.cooldown_until = datetime.fromisoformat(cd) if cd else None
        except (json.JSONDecodeError, KeyError, ValueError):
            self.last_reset_date = self._today_str()
