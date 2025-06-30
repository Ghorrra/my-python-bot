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
    'apiKey': 'YOUR_TESTNET_API_KEY',  # Замените на ваш API-ключ Binance Testnet
    'secret': 'YOUR_TESTNET_SECRET_KEY',  # Замените на ваш секретный ключ Binance Testnet
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
        exchange
