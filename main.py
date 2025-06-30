import os
import ccxt
import pandas as pd
import pandas_ta as ta
import requests
from datetime import datetime
import pytz
import logging
import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='pandas_ta')

# Настройка логирования
symbol = 'BTC/USDT'
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(symbol)s] - %(message)s')
logger = logging.getLogger(__name__)

# Инициализация Bybit Testnet
exchange = ccxt.bybit({
    'apiKey': os.getenv('BYBIT_API_KEY', 'JAOfHzcMBcdCcfuFUM'),
    'secret': os.getenv('BYBIT_SECRET_KEY', 'o3MQDfNUImJm2LzqP1JCHLiGrTNsmfUfQcFl'),
    'enableRateLimit': True,
    'urls': {
        'api': {
            'public': 'https://api-testnet.bybit.com',
            'private': 'https://api-testnet.bybit.com',
        },
        'test': {
            'public': 'https://api-testnet.bybit.com',
            'private': 'https://api-testnet.bybit.com',
        }
    },
    'options': {
        'defaultType': 'future',
        'test': True,
    }
})

# Telegram настройки
TELEGRAM_TOKEN = '8047737805:AAGQS0Aby26KT-2LDplGY99dLYCPIzcm8Cc'
TELEGRAM_CHAT_ID = '459620432'

def send_telegram_message(message):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message}
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logger.info(f"Telegram-сообщение отправлено: {message}", extra={'symbol': symbol})
    except Exception as e:
        logger.error(f"Ошибка отправки Telegram-сообщения: {e}", extra={'symbol': symbol})

def check_exchange_connection():
    try:
        print(f"Debug: Connecting to {exchange.urls['api']['public']}")
        print(f"Debug: API Key: {exchange.apiKey[:4]}...{exchange.apiKey[-4:]}")
        balance = exchange.fetch_balance()
        logger.info("Успешное подключение к Bybit Futures Testnet", extra={'symbol': symbol})
        send_telegram_message(f"[{symbol}] Успешное подключение к Bybit Futures Testnet")
        print(f"Debug: Balance: {balance['total']}")
        return True
    except Exception as e:
        logger.error(f"Ошибка подключения к Bybit Futures Testnet: {e}", extra={'symbol': symbol})
        send_telegram_message(f"[{symbol}] Ошибка подключения к Bybit Futures Testnet: {e}")
        print(f"Debug: Connection error: {e}")
        return False

def fetch_data(timeframe, limit=100):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df['rsi'] = ta.rsi(df['close'], length=14)
        df['ema21'] = ta.ema(df['close'], length=21)
        df['ema50'] = ta.ema(df['close'], length=50)
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        return df
    except Exception as e:
        logger.error(f"Ошибка получения данных: {e}", extra={'symbol': symbol})
        send_telegram_message(f"[{symbol}] Ошибка получения данных: {e}")
        return None

def check_entry_conditions(df_1m, df_5m, symbol):
    try:
        last_1m = df_1m.iloc[-1]
        prev_1m = df_1m.iloc[-2]
        last_5m = df_5m.iloc[-1]
        print(f"Debug: RSI={last_1m['rsi']:.2f}, EMA21={last_1m['ema21']:.2f}, EMA50={last_1m['ema50']:.2f}, ATR={last_1m['atr']:.2f}")
        if (last_1m['rsi'] < 30 and last_1m['ema21'] > last_1m['ema50'] and
                last_5m['rsi'] < 40 and last_1m['close'] > prev_1m['close']):
            return 'long'
        elif (last_1m['rsi'] > 70 and last_1m['ema21'] < last_1m['ema50'] and
              last_5m['rsi'] > 60 and last_1m['close'] < prev_1m['close']):
            return 'short'
        return None
    except Exception as e:
        logger.error(f"Ошибка проверки условий входа: {e}", extra={'symbol': symbol})
        send_telegram_message(f"[{symbol}] Ошибка проверки условий входа: {e}")
        return None

def main():
    print("Script started")
    logger.info(f"Бот запущен в {datetime.now(pytz.timezone('Europe/Tallinn')).strftime('%Y-%m-%d %H:%M:%S %Z')}", extra={'symbol': symbol})
    send_telegram_message(f"[{symbol}] Бот запущен в {datetime.now(pytz.timezone('Europe/Tallinn')).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    if not check_exchange_connection():
        logger.error("Прекращение работы из-за ошибки подключения", extra={'symbol': symbol})
        return

    while True:
        now = datetime.now(pytz.timezone('Europe/Tallinn'))
        if now.hour < 15 or now.hour >= 20:
            logger.info("Вне торгового окна (15:00-20:00 EEST), ожидание...", extra={'symbol': symbol})
            time.sleep(60)
            continue

        df_1m = fetch_data('1m')
        df_5m = fetch_data('5m')
        if df_1m is None or df_5m is None:
            time.sleep(60)
            continue

        signal = check_entry_conditions(df_1m, df_5m, symbol)
        if signal:
            logger.info(f"Обнаружен сигнал: {signal}", extra={'symbol': symbol})
            send_telegram_message(f"[{symbol}] Обнаружен сигнал: {signal}")
            # Здесь добавь логику размещения ордера
        time.sleep(60)

if __name__ == "__main__":
    import time
    main()
