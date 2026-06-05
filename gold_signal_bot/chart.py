# ============================================================
# chart.py — วาดกราฟราคา + EMA แล้วบันทึกเป็น PNG
# ============================================================

from __future__ import annotations
import matplotlib
matplotlib.use("Agg")  # ไม่ต้องเปิดหน้าต่าง GUI

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd


def create_signal_chart(
    df: pd.DataFrame,
    signal: str | None,
    symbol: str,
    timeframe_label: str,
    filename: str = "signal_chart.png",
    last_n: int = 80,
) -> str:
    """วาดกราฟ Price + EMA20 + EMA50 แล้ว save เป็นไฟล์

    Parameters
    ----------
    df : pd.DataFrame          ต้องมี time, close, ema_fast, ema_slow
    signal : str | None        "BUY" / "SELL" / None
    symbol : str               เช่น "XAUUSD"
    timeframe_label : str      เช่น "M15"
    filename : str             ชื่อไฟล์ output
    last_n : int               จำนวนแท่งที่จะแสดง (ย้อนหลัง)

    Returns
    -------
    str   path ของรูปที่ save แล้ว
    """
    plot_df = df.tail(last_n).copy()

    fig, ax = plt.subplots(figsize=(12, 5))

    # ── Price line ──
    ax.plot(plot_df["time"], plot_df["close"], label="Price", color="white", linewidth=1.2)

    # ── EMA lines ──
    ax.plot(plot_df["time"], plot_df["ema_fast"], label="EMA 20", color="cyan",   linewidth=1)
    ax.plot(plot_df["time"], plot_df["ema_slow"], label="EMA 50", color="orange", linewidth=1)

    # ── Title & Labels ──
    signal_text = signal if signal else "NO SIGNAL"
    color_map = {"BUY": "#00e676", "SELL": "#ff1744"}
    title_color = color_map.get(signal, "gray")

    ax.set_title(
        f"{symbol} {timeframe_label}  |  Signal: {signal_text}",
        fontsize=14, fontweight="bold", color=title_color,
    )
    ax.set_xlabel("Time")
    ax.set_ylabel("Price")

    # ── Style ──
    ax.set_facecolor("#1e1e2f")
    fig.patch.set_facecolor("#1e1e2f")
    ax.tick_params(colors="white")
    ax.xaxis.label.set_color("white")
    ax.yaxis.label.set_color("white")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    fig.autofmt_xdate()
    ax.legend(loc="upper left")
    ax.grid(alpha=0.2)

    # ── Save ──
    fig.savefig(filename, dpi=120, bbox_inches="tight")
    plt.close(fig)

    print(f"[Chart] saved → {filename}")
    return filename
