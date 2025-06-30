import ccxt
import pandas as pd
import pandas_ta as ta
import time
import logging
import datetime
import requests
from pytz import timezone

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(symbol)s] - %(message)s')
logger = logging.getLogger(__name__)

print("Script started")  # Отладочный print

# Настройки биржи (Binance Testnet)
exchange = ccxt.binance({
    'apiKey': '4c70a16f2765599439f6af8bd3d683dfbf8153019c51ed33420ad70347bf478e',  # Замените на ваш API-ключ Binance Testnet
    'secret': '1802f3d3c1fd2615c27707ee1732d17d53c4f42f269e063a364accff8d2e954c',  # Замените на ваш секретный ключ Binance Testnet
    'enableRateLimit': True,
    'urls': {
        'api': {
            'fapi': 'https://testnet.binancefuture.com/fapi',
        }
    },
    'options': {
        'defaultType': 'future',
    }
})

# Настройки Telegram
TELEGRAM_TOKEN = '8047737805:AAGQS0Aby26KT-2LDplGY99dLYCPIzcm8Cc'
TELEGRAM_CHAT_ID = '459620432'

# Параметры стратегии
symbol = 'BTC/USDT'
timeframe_1m = '1m'
timeframe_5m = '5m'
risk_per_trade = 0.01  # 1% риска
leverage = 2
tp_percent = 0.004  # Take Profit: +0.4%
timeout_seconds = 300  # 5 минут
min_balance = 100  # Минимальный баланс
atr_threshold_percent = 0.0008  # Порог ATR: 0.08% от цены
trading_hours = [(10, 14), (15, 20)]  # Лондон: 10:00–14:00, Нью-Йорк: 15:00–20:00 EEST
bb_period = 20  # Период Bollinger Bands
bb_dev = 2  # Отклонение Bollinger Bands

# Функция отправки сообщения в Telegram
def send_telegram_message(message):
    try:
        print(f"Attempting to send Telegram message: {message}")  # Отладочный print
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message
        }
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            logger.error(f"Ошибка отправки сообщения в Telegram: {response.text}", extra={'symbol': symbol})
            print(f"Telegram error: {response.text}")  # Отладочный print
        else:
            logger.info(f"Telegram-сообщение отправлено: {message}", extra={'symbol': symbol})
            print(f"Telegram message sent: {message}")  # Отладочный print
    except Exception as e:
        logger.error(f"Ошибка при отправке Telegram-сообщения: {e}", extra={'symbol': symbol})
        print(f"Exception in send_telegram_message: {e}")  # Отладочный print

# Проверка торговых часов
def is_trading_time():
    now = datetime.datetime.now(timezone('Europe/Kiev'))
    hour = now.hour
    for start, end in trading_hours:
        if start <= hour < end:
            return True
    return False

# Установка изолированного режима и плеча
def set_leverage_and_margin_mode(symbol):
    try:
        exchange.fapiPrivate_post_marginType({'symbol': symbol.replace('/', ''), 'marginType': 'ISOLATED'})
        exchange.fapiPrivate_post_leverage({'symbol': symbol.replace('/', ''), 'leverage': leverage})
        logger.info(f"Установлен изолированный режим и плечо x{leverage}", extra={'symbol': symbol})
        send_telegram_message(f"[{symbol}] Установлен изолированный режим и плечо x{leverage}")
    except Exception as e:
        logger.error(f"Ошибка при установке режима маржи или плеча: {e}", extra={'symbol': symbol})
        send_telegram_message(f"[{symbol}] Ошибка при установке режима маржи или плеча: {e}")

# Проверка подключения к Binance Testnet
def check_exchange_connection():
    try:
        exchange.fetch_balance()
        logger.info("Успешное подключение к Binance Testnet", extra={'symbol': symbol})
        send_telegram_message(f"[{symbol}] Успешное подключение к Binance Testnet")
        return True
    except Exception as e:
        logger.error(f"Ошибка подключения к Binance Testnet: {e}", extra={'symbol': symbol})
        send_telegram_message(f"[{symbol}] Ошибка подключения к Binance Testnet: {e}")
        return False

# Получение данных OHLCV
def fetch_ohlcv(symbol, timeframe, limit=100):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        logger.info(f"Успешно получены OHLCV данные для {timeframe}", extra={'symbol': symbol})
        return df
    except Exception as e:
        logger.error(f"Ошибка при получении OHLCV: {e}", extra={'symbol': symbol})
        send_telegram_message(f"[{symbol}] Ошибка при получении OHLCV: {e}")
        return None

# Расчет индикаторов с использованием pandas_ta
def calculate_indicators(df):
    try:
        df['ema21'] = ta.ema(df['close'], length=21)
        df['ema50'] = ta.ema(df['close'], length=50)
        df['rsi'] = ta.rsi(df['close'], length=14)
        df['vwap'] = ta.vwap(df['high'], df['low'], df['close'], df['volume'])
        df['avg_volume'] = df['volume'].rolling(window=5).mean()
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        bb = ta.bbands(df['close'], length=bb_period, std=bb_dev)
        df['bb_upper'] = bb[f'BBU_{bb_period}_{bb_dev}.0']
        df['bb_middle'] = bb[f'BBM_{bb_period}_{bb_dev}.0']
        df['bb_lower'] = bb[f'BBL_{bb_period}_{bb_dev}.0']
        logger.info("Индикаторы успешно рассчитаны", extra={'symbol': symbol})
        return df
    except Exception as e:
        logger.error(f"Ошибка при расчете индикаторов: {e}", extra={'symbol': symbol})
        send_telegram_message(f"[{symbol}] Ошибка при расчете индикаторов: {e}")
        return None

# Проверка условий входа
def check_entry_conditions(df_1m, df_5m, symbol):
    try:
        last_1m = df_1m.iloc[-1]
        prev_1m = df_1m.iloc[-2]
        last_5m = df_5m.iloc[-1]
        atr_threshold = last_1m['close'] * atr_threshold_percent  # 0.08% от цены
        
        # LONG
        if (last_1m['ema21'] > last_1m['ema50'] and
            last_5m['ema21'] > last_5m['ema50'] and
            prev_1m['rsi'] < 30 and last_1m['rsi'] > 30 and
            last_1m['close'] >= last_1m['vwap'] and
            last_1m['volume'] > last_1m['avg_volume'] and
            last_1m['close'] > last_1m['open'] and
            last_1m['atr'] > atr_threshold and
            last_1m['close'] <= last_1m['bb_middle'] and
            is_trading_time()):
            logger.info("Условия для LONG выполнены", extra={'symbol': symbol})
            return 'LONG'
        
        # SHORT
        if (last_1m['ema21'] < last_1m['ema50'] and
            last_5m['ema21'] < last_5m['ema50'] and
            prev_1m['rsi'] > 70 and last_1m['rsi'] < 70 and
            last_1m['close'] <= last_1m['vwap'] and
            last_1m['volume'] > last_1m['avg_volume'] and
            last_1m['close'] < last_1m['open'] and
            last_1m['atr'] > atr_threshold and
            last_1m['close'] >= last_1m['bb_middle'] and
            is_trading_time()):
            logger.info("Условия для SHORT выполнены", extra={'symbol': symbol})
            return 'SHORT'
        
        return None
    except Exception as e:
        logger.error(f"Ошибка при проверке условий входа: {e}", extra={'symbol': symbol})
        send_telegram_message(f"[{symbol}] Ошибка при проверке условий входа: {e}")
        return None

# Расчет прибыли/убытка
def calculate_pnl(side, entry_price, exit_price, position_size):
    try:
        if side == 'LONG':
            pnl = (exit_price - entry_price) * position_size
        else:  # SHORT
            pnl = (entry_price - exit_price) * position_size
        return round(pnl, 2)
    except Exception as e:
        logger.error(f"Ошибка при расчете PNL: {e}", extra={'symbol': symbol})
        return 0

# Закрытие позиции
def close_position(symbol, side, position_size, entry_price, reason):
    try:
        exit_price = exchange.fetch_ticker(symbol)['last']
        exchange.create_market_order(
            symbol=symbol,
            side='sell' if side == 'LONG' else 'buy',
            amount=position_size,
            params={'reduceOnly': True, 'positionSide': side}
        )
        pnl = calculate_pnl(side, entry_price, exit_price, position_size)
        logger.info(f"Позиция {side} закрыта ({reason})\nЦена выхода: {exit_price}\nPNL: {pnl} USDT", extra={'symbol': symbol})
        send_telegram_message(f"[{symbol}] Позиция {side} закрыта ({reason})\nЦена выхода: {exit_price}\nPNL: {pnl} USDT")
    except Exception as e:
        logger.error(f"Ошибка при закрытии позиции: {e}", extra={'symbol': symbol})
        send_telegram_message(f"[{symbol}] Ошибка при закрытии позиции: {e}")

# Открытие позиции с выставлением TP и SL
def open_position(symbol, side, balance, entry_price):
    try:
        # Рассчитаем позиционный размер (усреднённо, 2.5% от баланса)
        position_size = round((balance * 0.025) / entry_price, 5)
        if position_size <= 0:
            logger.warning("Размер позиции равен 0, позиция не открыта", extra={'symbol': symbol})
            return None, None

        params = {'positionSide': side}
        order_side = 'buy' if side == 'LONG' else 'sell'

        order = exchange.create_market_order(symbol, order_side, position_size, params=params)
        logger.info(f"Позиция {side} открыта по цене {entry_price}, размер {position_size}", extra={'symbol': symbol})

        # Установка TP и SL
        if side == 'LONG':
            tp_price = entry_price * (1 + tp_percent)
            sl_price = entry_price * (1 - tp_percent)
        else:
            tp_price = entry_price * (1 - tp_percent)
            sl_price = entry_price * (1 + tp_percent)

        # Параметры для TP и SL ордеров (Binance Futures)
        # Здесь можно использовать условные ордера (STOP_MARKET и TAKE_PROFIT_MARKET)
        # Но для упрощения можно делать контроль вручную в основном цикле

        send_telegram_message(f"[{symbol}] Открыта позиция {side}\nЦена: {entry_price}\nTP: {tp_price}\nSL: {sl_price}")

        return position_size, (tp_price, sl_price)
    except Exception as e:
        logger.error(f"Ошибка при открытии позиции: {e}", extra={'symbol': symbol})
        send_telegram_message(f"[{symbol}] Ошибка при открытии позиции: {e}")
        return None, None

# Основной цикл торговли
def main():
    if not check_exchange_connection():
        logger.error("Не удалось подключиться к бирже, выход", extra={'symbol': symbol})
        return

    set_leverage_and_margin_mode(symbol)

    current_position = None
    position_size = 0
    tp_price = None
    sl_price = None
    entry_price = 0
    position_side = None
    last_entry_time = None

    while True:
        try:
            # Получаем баланс USDT
            balance_info = exchange.fetch_balance()
            usdt_balance = balance_info['total'].get('USDT', 0)
            logger.info(f"Баланс USDT: {usdt_balance}", extra={'symbol': symbol})

            if usdt_balance < min_balance:
                logger.warning("Баланс ниже минимального порога, торговля приостановлена", extra={'symbol': symbol})
                send_telegram_message(f"[{symbol}] Баланс ниже минимального порога ({min_balance} USDT). Торговля приостановлена.")
                time.sleep(60)
                continue

            # Получаем данные для 1m и 5m
            df_1m = fetch_ohlcv(symbol, timeframe_1m)
            df_5m = fetch_ohlcv(symbol, timeframe_5m)

            if df_1m is None or df_5m is None:
                time.sleep(30)
                continue

            df_1m = calculate_indicators(df_1m)
            df_5m = calculate_indicators(df_5m)

            if df_1m is None or df_5m is None:
                time.sleep(30)
                continue

            signal = check_entry_conditions(df_1m, df_5m, symbol)
            last_price = df_1m.iloc[-1]['close']

            if current_position is None and signal is not None:
                # Открываем позицию
                position_size, (tp_price, sl_price) = open_position(symbol, signal, usdt_balance, last_price)
                if position_size:
                    current_position = signal
                    entry_price = last_price
                    position_side = signal
                    last_entry_time = time.time()
            elif current_position is not None:
                # Следим за тейк профитом и стоп лоссом
                now_price = last_price
                elapsed = time.time() - last_entry_time

                if (current_position == 'LONG' and (now_price >= tp_price or now_price <= sl_price)) or \
                   (current_position == 'SHORT' and (now_price <= tp_price or now_price >= sl_price)):
                    close_position(symbol, current_position, position_size, entry_price, reason='TP/SL reached')
                    current_position = None
                    position_size = 0
                    tp_price = None
                    sl_price = None
                    entry_price = 0
                    position_side = None
                    last_entry_time = None

                # Тайм-аут выхода из позиции
                elif elapsed > timeout_seconds:
                    close_position(symbol, current_position, position_size, entry_price, reason='Timeout')
                    current_position = None
                    position_size = 0
                    tp_price = None
                    sl_price = None
                    entry_price = 0
                    position_side = None
                    last_entry_time = None

            time.sleep(10)
        except Exception as e:
            logger.error(f"Ошибка в основном цикле: {e}", extra={'symbol': symbol})
            send_telegram_message(f"[{symbol}] Ошибка в основном цикле: {e}")
            time.sleep(30)

if __name__ == '__main__':
    main()
