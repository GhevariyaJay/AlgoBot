import time
import pandas as pd
import numpy as np
import MetaTrader5 as mt5

# === CONFIGURATION ===
SYMBOL = "USDJPY"  # Change to your symbol
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

# Trading Parameters
SLIPPAGE = 5
MAX_LOT_SIZE = 0.01  # Max lot size (adjust as needed)

# === MT5 API CONNECTION ===
def connect_to_mt5(login, password, server):
    """
    Connect to MetaTrader 5.
    """
    try:
        if not mt5.initialize():
            print("Failed to initialize MT5")
            return False

        if not mt5.login(login, password, server):
            print(f"Failed to login to MT5. Error: {mt5.last_error()}")
            return False

        print("✅ Connected to MT5 successfully.")
        return True
    except Exception as e:
        print(f"Error connecting to MT5: {e}")
        return False

# === HELPER: Calculate Lot Size (based on account balance) ===
def calculate_lot_size(balance, price):
    """
    Calculate lot size based on account balance and price.
    Simple rule: max lot size = 0.01, or based on balance.
    """
    max_lot = MAX_LOT_SIZE  # Maximum lot size (from config)
    min_lot = 0.01  # Minimum lot size

    # Adjust based on balance (e.g., 0.1% of balance)
    lot_size = min(max_lot, balance / 100000)  # e.g., 0.1% of balance
    lot_size = max(lot_size, min_lot)

    return round(lot_size, 4)  # Round to 4 decimal places

# === HELPER: Get Historical Data (OHLC) ===
def get_historical_data(symbol, period=mt5.TIMEFRAME_M15):
    """
    Fetch historical data for a symbol.
    Returns a list of close prices.
    """
    try:
        rates = mt5.copy_rates_from_pos(symbol, period, 0, 100)  # 100 bars
        if rates is None or len(rates) == 0:
            print("⚠️ No data fetched.")
            return None

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')  # corrected unit to seconds
        df.set_index('time', inplace=True)
        return df['close'].values.tolist()  # Return close prices as list

    except Exception as e:
        print(f"Error fetching data: {e}")
        return None

# === HELPER: Calculate RSI ===
def calculate_rsi(prices, period=14):
    """
    Calculate RSI from a list of close prices.
    """
    if len(prices) < period:
        return 0.0

    deltas = np.diff(prices)
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period

    if down == 0:
        return 100.0

    rs = up / down
    rsi = 100 - (100 / (1 + rs))
    print("RSI:", rsi)
    a = rsi


    return rsi

# === HELPER: Check if there's an open position (with magic 1001) ===
def is_position_open():
    """
    Check if any open position exists with magic number 1001.
    """
    global current_position
    if current_position is None:
        return False

    positions = mt5.positions_get(symbol=current_position["symbol"])
    if positions is None or len(positions) == 0:
        return False

    for pos in positions:
        if pos.magic == 1001:
            # Check if position matches direction
            if (pos.type == mt5.ORDER_TYPE_BUY and current_position["direction"] == "BUY") or \
               (pos.type == mt5.ORDER_TYPE_SELL and current_position["direction"] == "SELL"):
                return True
    return False

# === PLACE ORDER FUNCTION ===
def place_order(symbol, direction, lot_size):
    """
    Place a buy or sell order with proper validation.
    """
    try:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            print("❌ Failed to get symbol tick data.")
            return False

        price = tick.ask if direction == "BUY" else tick.bid

        if price <= 0:
            print("❌ Invalid price.")
            return False

        if lot_size <= 0:
            print("❌ Invalid lot size.")
            return False

        order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot_size,
            "type": order_type,
            "price": price,
            "deviation": SLIPPAGE,
            "magic": 1001,
            "comment": f"RSI Trade - {direction}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"❌ Order failed: {result.retcode} - {result.comment}")
            return False

        print(f"✅ {direction} order placed for {symbol} at {price} with lot {lot_size}")
        return True

    except Exception as e:
        print(f"Error placing order: {e}")
        return False

# === CLOSE POSITION FUNCTION (triggered by RSI) ===
def close_position_by_rsi():
    """
    Close a position if RSI triggers a close.
    """
    global current_position
    if current_position is None:
        return False

    symbol = current_position["symbol"]
    direction = current_position["direction"]

    try:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            print("❌ Failed to get tick data for closing.")
            return False

        price = tick.ask if direction == "BUY" else tick.bid

        order_type = mt5.ORDER_TYPE_SELL if direction == "BUY" else mt5.ORDER_TYPE_BUY
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": current_position["lot_size"],
            "type": order_type,
            "price": price,
            "deviation": SLIPPAGE,
            "magic": 1001,
            "comment": "RSI Close Trigger",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"❌ Failed to close position: {result.retcode} - {result.comment}")
            return False

        print(f"✅ Closed position: {direction} at {price}")
        current_position = None
        return True

    except Exception as e:
        print(f"Error closing position: {e}")
        return False

# === MAIN LOOP ===
def main():
    print("🚀 Starting RSI Trading Bot...")

    # Get user input (replace with your credentials)
    login =      # Replace with your MT5 login
    password = ""  # Replace with your password
    server = ""     # Replace with your MT5 server

    if not connect_to_mt5(login, password, server):
        print("❌ Failed to connect to MT5. Exiting.")
        return

    global current_position
    current_position = None

    try:
        while True:
            if is_position_open():
                print("✅ Position already open. Waiting for it to close...")
                # print(a)
                
                time.sleep(1)  # Wait 10 seconds before checking again
                continue

            prices = get_historical_data(SYMBOL)
            if prices is None or len(prices) < RSI_PERIOD:
                print("⚠️ Not enough data to calculate RSI.")
                time.sleep(1)
                continue

            rsi_value = calculate_rsi(prices[-RSI_PERIOD:], RSI_PERIOD)

            account_info = mt5.account_info()
            if account_info is None:
                print("❌ Failed to get account info.")
                time.sleep(1)
                continue

            balance = account_info.balance
            lot_size = calculate_lot_size(balance, 0)

            if rsi_value < RSI_OVERSOLD and current_position is None:
                print(f"🔔 RSI below {RSI_OVERSOLD}: BUY signal detected!")
                if place_order(SYMBOL, "BUY", lot_size):
                    current_position = {
                        "symbol": SYMBOL,
                        "direction": "BUY",
                        "lot_size": lot_size
                    }

            elif rsi_value > RSI_OVERBOUGHT and current_position is None:
                print(f"🔔 RSI above {RSI_OVERBOUGHT}: SELL signal detected!")
                if place_order(SYMBOL, "SELL", lot_size):
                    current_position = {
                        "symbol": SYMBOL,
                        "direction": "SELL",
                        "lot_size": lot_size
                    }

            # Close position if RSI crosses back over threshold
            if current_position is not None:
                # Fetch fresh prices for checking exit condition
                prices = get_historical_data(SYMBOL)
                if prices and len(prices) >= RSI_PERIOD:
                    new_rsi = calculate_rsi(prices[-RSI_PERIOD:], RSI_PERIOD)
                    if (current_position["direction"] == "BUY" and new_rsi > RSI_OVERBOUGHT) or \
                       (current_position["direction"] == "SELL" and new_rsi < RSI_OVERSOLD):
                        print("🔔 RSI trigger to close position detected!")
                        close_position_by_rsi()

            time.sleep(1)  # Sleep to avoid spamming and allow new bars

    except KeyboardInterrupt:
        print("\n🛑 User interrupted the bot.")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        mt5.shutdown()

# === RUN THE BOT ===
if __name__ == "__main__":
    main()
