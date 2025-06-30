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
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message
        }
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            logger.error(f"Ошибка отправки сообщения в Telegram: {response.text}", extra={'symbol': symbol})
        else:
            logger.info(f"Telegram-сообщение отправлено: {message}", extra={'symbol': symbol})
    except Exception as e:
        logger.error(f"Ошибка при отправке Telegram-сообщения: {e}", extra={'symbol': symbol})

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

# Управление позицией
def manage_position(symbol, side, entry_price, position_size, atr):
    try:
        tp_price = entry_price * (1 + tp_percent) if side == 'LONG' else entry_price * (1 - tp_percent)
        sl_price = entry_price * (1 - atr * 1.5 / entry_price) if side == 'LONG' else entry_price * (1 + atr * 1.5 / entry_price)
        
        # Отправка ордеров TP/SL
        exchange.create_order(
            symbol=symbol,
            type='LIMIT',
            side='sell' if side == 'LONG' else 'buy',
            amount=position_size,
            price=tp_price,
            params={'reduceOnly': True, 'positionSide': side}
        )
        exchange.create_order(
            symbol=symbol,
            type='STOP_MARKET',
            side='sell' if side == 'LONG' else 'buy',
            amount=position_size,
            params={'stopPrice': sl_price, 'reduceOnly': True, 'positionSide': side}
        )
        logger.info(f"Открыта позиция {side} по цене {entry_price}, TP: {tp_price}, SL: {sl_price}", extra={'symbol': symbol})
        send_telegram_message(f"[{symbol}] Открыта позиция {side}\nЦена: {entry_price}\nРазмер: {position_size:.6f}\nTP: {tp_price}\nSL: {sl_price}")
    except Exception as e:
        logger.error(f"Ошибка при установке TP/SL: {e}", extra={'symbol': symbol})
        send_telegram_message(f"[{symbol}] Ошибка при установке TP/SL: {e}")

# Проверка тайм-аута
def check_timeout(symbol, entry_time, position_size, side, entry_price):
    if time.time() - entry_time > timeout_seconds:
        try:
            exchange.create_market_order(
                symbol=symbol,
                side='sell' if side == 'LONG' else 'buy',
                amount=position_size,
                params={'reduceOnly': True, 'positionSide': side}
            )
            logger.info(f"Позиция закрыта по тайм-ауту ({timeout_seconds} сек)", extra={'symbol': symbol})
            send_telegram_message(f"[{symbol}] Позиция {side} закрыта по тайм-ауту\nЦена входа: {entry_price}")
        except Exception as e:
            logger.error(f"Ошибка при закрытии позиции по тайм-ауту: {e}", extra={'symbol': symbol})
            send_telegram_message(f"[{symbol}] Ошибка при закрытии позиции по тайм-ауту: {e}")

# Основной цикл
def main():
    # Сообщение о запуске бота
    start_time = datetime.datetime.now(timezone('Europe/Kiev')).strftime('%Y-%m-%d %H:%M:%S %Z')
    logger.info(f"Бот запущен в {start_time}", extra={'symbol': symbol})
    send_telegram_message(f"[{symbol}] Бот запущен в {start_time}")
    
    # Проверка подключения к Binance Testnet
    if not check_exchange_connection():
        logger.error("Прекращение работы из-за ошибки подключения", extra={'symbol': symbol})
        return
    
    set_leverage_and_margin_mode(symbol)
    position_active = False
    entry_time = 0
    position_side = None
    position_size = 0
    entry_price = 0

    while True:
        try:
            logger.info("Начало нового торгового цикла", extra={'symbol': symbol})
            # Проверка баланса
            balance = exchange.fetch_balance()['USDT']['free']
            if balance < min_balance:
                logger.error(f"Недостаточно средств: {balance} USDT", extra={'symbol': symbol})
                send_telegram_message(f"[{symbol}] Недостаточно средств: {balance} USDT")
                time.sleep(60)
                continue
            
            # Получение данных
            df_1m = fetch_ohlcv(symbol, timeframe_1m)
            df_5m = fetch_ohlcv(symbol, timeframe_5m)
            if df_1m is None or df_5m is None:
                time.sleep(60)
                continue
            df_1m = calculate_indicators(df_1m)
            df_5m = calculate_indicators(df_5m)
            if df_1m is None or df_5m is None:
                time.sleep(60)
                continue
            
            # Проверка активной позиции
            if position_active:
                check_timeout(symbol, entry_time, position_size, position_side, entry_price)
                time.sleep(10)
                continue
            
            # Проверка условий входа
            signal = check_entry_conditions(df_1m, df_5m, symbol)
            if signal:
                price = df_1m['close'].iloc[-1]
                atr = df_1m['atr'].iloc[-1]
                position_size = (balance * risk_per_trade) / (atr * 1.5 / price) * leverage
                
                # Открытие позиции
                if signal == 'LONG':
                    exchange.create_market_buy_order(symbol, position_size, params={'positionSide': 'LONG'})
                    manage_position(symbol, 'LONG', price, position_size, atr)
                    position_active = True
                    position_side = 'LONG'
                    entry_time = time.time()
                    entry_price = price
                elif signal == 'SHORT':
                    exchange.create_market_sell_order(symbol, position_size, params={'positionSide': 'SHORT'})
                    manage_position(symbol, 'SHORT', price, position_size, atr)
                    position_active = True
                    position_side = 'SHORT'
                    entry_time = time.time()
                    entry_price = price
            
            time.sleep(60)
        except Exception as e:
            logger.error(f"Ошибка в цикле: {e}", extra={'symbol': symbol})
            send_telegram_message(f"[{symbol}] Ошибка в цикле: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
