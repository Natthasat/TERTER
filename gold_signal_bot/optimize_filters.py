# ============================================================
# optimize_filters.py — ทดสอบทุกชุด filter + SL/TP แยกกัน
# ============================================================
#  หา combination ที่ดีที่สุดสำหรับ Gold
# ============================================================

import sys
import itertools
import config
from mt5_data   import connect_mt5, disconnect_mt5, get_ohlc
from indicators import add_indicators
from backtester import run_backtest
from strategy   import FilterConfig

SYMBOL    = config.SYMBOL
TIMEFRAME = config.TIMEFRAME
TF_LABEL  = config.TIMEFRAME_LABEL
NUM_BARS  = 5000


def main() -> None:
    if not connect_mt5():
        sys.exit(1)

    try:
        df = get_ohlc(SYMBOL, TIMEFRAME, NUM_BARS)
        if df is None:
            return

        df = add_indicators(
            df,
            ema_fast=config.EMA_FAST,
            ema_slow=config.EMA_SLOW,
            rsi_period=config.RSI_PERIOD,
            atr_period=getattr(config, "ATR_PERIOD", 14),
            adx_period=getattr(config, "ADX_PERIOD", 14),
        )
        print(f"[Data] {len(df)} bars ready\n")

        # ── Parameter Grid ──────────────────────────────────
        sl_tp_combos = [
            (1.0, 2.0),
            (1.0, 2.5),
            (1.0, 3.0),
            (1.5, 2.5),
            (1.5, 3.0),
        ]

        filter_combos = {
            "NO_FILTER":        FilterConfig.disabled(),
            "SESSION_ONLY":     FilterConfig(
                use_session_filter=True, use_adx_filter=False,
                use_body_filter=False, use_anti_chase=False,
                use_volatility_guard=False,
                session_start_utc=9, session_end_utc=22,
            ),
            "ADX_ONLY":         FilterConfig(
                use_session_filter=False, use_adx_filter=True,
                use_body_filter=False, use_anti_chase=False,
                use_volatility_guard=False,
                adx_threshold=15.0,
            ),
            "SESSION+ADX":      FilterConfig(
                use_session_filter=True, use_adx_filter=True,
                use_body_filter=False, use_anti_chase=False,
                use_volatility_guard=False,
                session_start_utc=9, session_end_utc=22,
                adx_threshold=15.0,
            ),
            "SESSION+BODY":     FilterConfig(
                use_session_filter=True, use_adx_filter=False,
                use_body_filter=True, use_anti_chase=False,
                use_volatility_guard=False,
                session_start_utc=9, session_end_utc=22,
                min_body_ratio=0.25,
            ),
            "SESS+ADX+BODY":    FilterConfig(
                use_session_filter=True, use_adx_filter=True,
                use_body_filter=True, use_anti_chase=False,
                use_volatility_guard=False,
                session_start_utc=9, session_end_utc=22,
                adx_threshold=15.0, min_body_ratio=0.25,
            ),
            "ALL_FILTERS":      FilterConfig(
                use_session_filter=True, use_adx_filter=True,
                use_body_filter=True, use_anti_chase=True,
                use_volatility_guard=True,
                session_start_utc=9, session_end_utc=22,
                adx_threshold=15.0, min_body_ratio=0.25,
                max_distance_atr=2.0, max_atr_ratio=2.5,
            ),
        }

        # ── Run Grid ────────────────────────────────────────
        results = []
        for (sl_m, tp_m) in sl_tp_combos:
            for f_name, fc in filter_combos.items():
                res = run_backtest(
                    df.copy(), atr_sl_mult=sl_m, atr_tp_mult=tp_m,
                    filter_config=fc,
                )
                results.append({
                    "SL": sl_m, "TP": tp_m, "Filters": f_name,
                    "Trades": res.total_trades,
                    "WR%": round(res.win_rate, 1),
                    "PF": round(res.profit_factor, 2),
                    "RR": round(res.reward_risk_ratio, 2),
                    "Net": round(res.net_pnl, 1),
                    "DD": round(res.max_drawdown, 1),
                    "ConsecL": res.max_consecutive_losses,
                })

        # ── Print Table ─────────────────────────────────────
        import pandas as pd
        tbl = pd.DataFrame(results)
        tbl = tbl.sort_values("PF", ascending=False)

        print("=" * 95)
        print(f"  GRID TEST — {SYMBOL} {TF_LABEL}  |  {len(results)} combinations")
        print("=" * 95)
        print(tbl.to_string(index=False))
        print()

        # ── Best Pick ───────────────────────────────────────
        # เลือก: trades ≥ 30  &  PF สูงสุด
        viable = tbl[tbl["Trades"] >= 30]
        if not viable.empty:
            best = viable.iloc[0]
            print("── BEST (PF สูงสุด, trades ≥ 30) ──")
            print(best.to_string())
        print()

    finally:
        disconnect_mt5()


if __name__ == "__main__":
    main()
