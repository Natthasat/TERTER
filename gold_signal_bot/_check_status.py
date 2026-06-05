"""Quick EA health check"""
import MetaTrader5 as mt5
import pandas as pd

mt5.initialize()
info = mt5.account_info()
tick = mt5.symbol_info_tick("GOLD")
pos = mt5.positions_get(symbol="GOLD")
rates = mt5.copy_rates_from_pos("GOLD", mt5.TIMEFRAME_M1, 0, 5)

print(f"Balance: ${info.balance}  Equity: ${info.equity}")
print(f"Bid: {tick.bid}  Ask: {tick.ask}  Spread: {tick.ask - tick.bid:.2f}")

n = len(pos) if pos else 0
print(f"Open positions: {n}")
if pos:
    for p in pos:
        direction = "BUY" if p.type == 0 else "SELL"
        print(f"  #{p.ticket} {direction} @ {p.price_open} P/L: ${p.profit:.2f}")

print("Last 5 M1 bars:")
for r in rates:
    t = pd.Timestamp(r["time"], unit="s")
    print(f"  {t}  O:{r['open']:.2f} H:{r['high']:.2f} L:{r['low']:.2f} C:{r['close']:.2f}")

mt5.shutdown()
