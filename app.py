from flask import Flask, render_template, request, redirect, url_for
import threading
import time
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime

app = Flask(__name__)

# Globals for the bot
bot_thread = None
stop_bot = False
bot_logs = []

SYMBOL = "USDJPY"
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
SLIPPAGE = 5
MAX_LOT_SIZE = 0.01

current_position = None


def log(message):
    global bot_logs
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"[{timestamp}] {message}"
    bot_logs.append(formatted_message)
    print(formatted_message)


def calculate_rsi(prices, period=14):
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
    return rsi


def get_historical_data(symbol, period=mt5.TIMEFRAME_M15):
    rates = mt5.copy_rates_from_pos(symbol, period, 0, 100)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df['close'].values.tolist()


def calculate_lot_size(balance, price):
    max_lot = MAX_LOT_SIZE
    min_lot = 0.01
    lot_size = min(max_lot, balance / 100000)
    lot_size = max(lot_size, min_lot)
    return round(lot_size, 4)


def place_order(symbol, direction, lot_size):
    try:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            log("Failed to get symbol tick data.")
            return False
        price = tick.ask if direction == "BUY" else tick.bid
        if price <= 0 or lot_size <= 0:
            log("Invalid price or lot size.")
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
            log(f"Order failed: {result.retcode} - {result.comment}")
            return False
        log(f"{direction} order placed for {symbol} at {price} with lot {lot_size}")
        return True
    except Exception as e:
        log(f"Error placing order: {e}")
        return False


def close_position_by_rsi():
    global current_position
    if current_position is None:
        return False
    symbol = current_position["symbol"]
    direction = current_position["direction"]
    try:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            log("Failed to get tick data for closing.")
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
            log(f"Failed to close position: {result.retcode} - {result.comment}")
            return False
        log(f"Closed position: {direction} at {price}")
        current_position = None
        return True
    except Exception as e:
        log(f"Error closing position: {e}")
        return False


def is_position_open():
    global current_position
    if current_position is None:
        return False
    positions = mt5.positions_get(symbol=current_position["symbol"])
    if positions is None or len(positions) == 0:
        return False
    for pos in positions:
        if pos.magic == 1001:
            if (pos.type == mt5.ORDER_TYPE_BUY and current_position["direction"] == "BUY") or \
               (pos.type == mt5.ORDER_TYPE_SELL and current_position["direction"] == "SELL"):
                return True
    return False


def connect_to_mt5(login, password, server):
    # Update this path according to your MT5 terminal location
    mt5_path = "C:\\Program Files\\MetaTrader 5\\terminal64.exe"

    log("Initializing MT5...")
    initialized = mt5.initialize(path=mt5_path)
    if not initialized:
        err = mt5.last_error()
        log(f"MT5 initialization failed: {err}")
        return False

    try:
        login_int = int(login)
    except Exception:
        log(f"Invalid login account number: {login}")
        return False

    log(f"Logging in with account: {login_int}, server: {server}")
    logged_in = mt5.login(login_int, password, server)
    if not logged_in:
        err = mt5.last_error()
        log(f"MT5 login failed: {err}")
        return False

    log("MT5 connected successfully.")
    return True


def trading_bot(login, password, server):
    global current_position, stop_bot, bot_logs
    current_position = None
    bot_logs = []
    stop_bot = False

    if not connect_to_mt5(login, password, server):
        log("Could not connect to MT5. Bot stopped.")
        return

    try:
        while not stop_bot:
            if is_position_open():
                log("Position already open. Waiting...")
                time.sleep(5)
                continue

            prices = get_historical_data(SYMBOL)
            if prices is None or len(prices) < RSI_PERIOD:
                log("Not enough data to calculate RSI.")
                time.sleep(5)
                continue

            rsi_value = calculate_rsi(prices[-RSI_PERIOD:], RSI_PERIOD)
            log(f"RSI: {rsi_value:.2f}")

            account_info = mt5.account_info()
            if account_info is None:
                log("Failed to get account info.")
                time.sleep(5)
                continue

            balance = account_info.balance
            lot_size = calculate_lot_size(balance, 0)

            if rsi_value < RSI_OVERSOLD and current_position is None:
                log(f"RSI below {RSI_OVERSOLD}: BUY signal detected!")
                if place_order(SYMBOL, "BUY", lot_size):
                    current_position = {
                        "symbol": SYMBOL,
                        "direction": "BUY",
                        "lot_size": lot_size
                    }

            elif rsi_value > RSI_OVERBOUGHT and current_position is None:
                log(f"RSI above {RSI_OVERBOUGHT}: SELL signal detected!")
                if place_order(SYMBOL, "SELL", lot_size):
                    current_position = {
                        "symbol": SYMBOL,
                        "direction": "SELL",
                        "lot_size": lot_size
                    }

            # Close position if RSI crosses threshold
            if current_position is not None:
                prices = get_historical_data(SYMBOL)
                if prices and len(prices) >= RSI_PERIOD:
                    new_rsi = calculate_rsi(prices[-RSI_PERIOD:], RSI_PERIOD)
                    if (current_position["direction"] == "BUY" and new_rsi > RSI_OVERBOUGHT) or \
                       (current_position["direction"] == "SELL" and new_rsi < RSI_OVERSOLD):
                        log("RSI trigger to close position detected!")
                        close_position_by_rsi()

            time.sleep(5)

    except Exception as e:
        log(f"Bot error: {e}")
    finally:
        mt5.shutdown()
        log("MT5 shutdown. Bot stopped.")


@app.route("/", methods=["GET", "POST"])
def index():
    global bot_thread, stop_bot, bot_logs

    if request.method == "POST":
        if bot_thread and bot_thread.is_alive():
            stop_bot = True
            bot_thread.join()

        login = request.form.get("login")
        password = request.form.get("password")
        server = request.form.get("server")

        stop_bot = False
        bot_thread = threading.Thread(target=trading_bot, args=(login, password, server))
        bot_thread.start()

        return redirect(url_for("index"))

    return render_template("index.html", logs=bot_logs)


@app.route("/stop", methods=["POST"])
def stop():
    global stop_bot, bot_thread
    stop_bot = True
    if bot_thread:
        bot_thread.join()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
