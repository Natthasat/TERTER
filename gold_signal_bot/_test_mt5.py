import MetaTrader5 as mt5

mt5.initialize()
info = mt5.account_info()
if info is None:
    print("ERROR: Cannot connect to MT5")
    print(f"Error code: {mt5.last_error()}")
else:
    print(f"Login  : {info.login}")
    print(f"Server : {info.server}")
    print(f"Balance: ${info.balance}")
    print(f"Equity : ${info.equity}")
    print(f"Name   : {info.name}")
    print(f"Type   : {'Demo' if info.trade_mode == 0 else 'Real' if info.trade_mode == 2 else info.trade_mode}")

    tick = mt5.symbol_info_tick("GOLD")
    if tick:
        print(f"\nGOLD Bid: {tick.bid}  Ask: {tick.ask}  Spread: {tick.ask - tick.bid:.2f}")
    else:
        print("\nGOLD symbol not found, trying XAUUSD...")
        tick = mt5.symbol_info_tick("XAUUSD")
        if tick:
            print(f"XAUUSD Bid: {tick.bid}  Ask: {tick.ask}  Spread: {tick.ask - tick.bid:.2f}")
        else:
            print("Neither GOLD nor XAUUSD found!")

mt5.shutdown()
