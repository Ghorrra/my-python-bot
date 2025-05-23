import time
import requests
import certifi
from datetime import datetime
import urllib3

# Отключаем предупреждения InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# URLs для API бирж
GATE_TICKER_URL = "https://api.gateio.ws/api/v4/futures/usdt/tickers"
GATE_ORDERBOOK_URL = "https://api.gateio.ws/api/v4/futures/usdt/order_book"
MEXC_TICKER_URL = "https://contract.mexc.com/api/v1/contract/ticker"
MEXC_ORDERBOOK_URL = "https://contract.mexc.com/api/v1/contract/depth/"
BINANCE_TICKER_URL = "https://fapi.binance.com/fapi/v1/ticker/price"
BINANCE_ORDERBOOK_URL = "https://fapi.binance.com/fapi/v1/depth"
BITGET_TICKER_URL = "https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES"
BITGET_ORDERBOOK_URL = "https://api.bitget.com/api/v2/mix/market/depth"
BYBIT_TICKER_URL = "https://api.bybit.com/v5/market/tickers?category=linear"
BYBIT_ORDERBOOK_URL = "https://api.bybit.com/v5/market/orderbook?category=linear"
KUCOIN_TICKER_URL = "https://api-futures.kucoin.com/api/v1/ticker"
KUCOIN_ORDERBOOK_URL = "https://api-futures.kucoin.com/api/v1/level2/snapshot"
OKX_TICKER_URL = "https://www.okx.com/api/v5/market/tickers?instType=SWAP"
OKX_ORDERBOOK_URL = "https://www.okx.com/api/v5/market/books"
COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/list?include_platform=true"

# Константы
MIN_PROFIT_PERCENT = 1.0
COMMISSION_PERCENT = 0.1
MIN_VOLUME_USDT = 10000
MIN_TRADE_USDT = 50
MAX_SPREAD_PERCENT = 50
SLIPPAGE_PERCENT = 2.0

# Telegram константы
BOT_TOKEN = "8047737805:AAGQS0Aby26KT-2LDplGY99dLYCPIzcm8Cc"
CHAT_ID = "459620432"

shown_opportunities = set()
token_contracts = {}
orderbook_cache = {}

def safe_float(value, default=0.0):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        response = requests.post(url, json=payload, timeout=10, verify=certifi.where())
        response.raise_for_status()
    except Exception as e:
        print(f"Ошибка отправки сообщения в Telegram: {e}")

def load_token_contracts():
    global token_contracts
    print("Загружаю адреса контрактов из CoinGecko...")
    try:
        response = requests.get(COINGECKO_URL, timeout=20, verify=certifi.where())
        response.raise_for_status()
        data = response.json()
        for coin in data:
            symbol = coin['symbol'].upper()
            platforms = coin.get("platforms", {})
            token_contracts[symbol] = {
                "gate": platforms.get("gatechain"),
                "mexc": platforms.get("ethereum"),
                "binance": platforms.get("binance-smart-chain") or platforms.get("binancecoin"),
                "bitget": platforms.get("ethereum"),
                "bybit": platforms.get("ethereum"),
                "kucoin": platforms.get("kucoin") or platforms.get("kucoin-community-chain"),
                "okx": platforms.get("okex-chain") or platforms.get("ethereum")
            }
        print(f"Загружено {len(token_contracts)} токенов с CoinGecko.")
    except Exception as e:
        print("Не удалось загрузить данные с CoinGecko:", e)

def contracts_match(symbol, exchange1, exchange2):
    contracts = token_contracts.get(symbol, {})
    contract1 = contracts.get(exchange1.lower())
    contract2 = contracts.get(exchange2.lower())
    if not contract1 or not contract2:
        return True
    return contract1.lower() == contract2.lower()

def check_gate_liquidity(symbol, price, trade_usdt=MIN_TRADE_USDT):
    cache_key = f"gate_{symbol}"
    if cache_key in orderbook_cache:
        data = orderbook_cache[cache_key]
    else:
        try:
            url = f"{GATE_ORDERBOOK_URL}?contract={symbol}"
            response = requests.get(url, timeout=10, verify=certifi.where())
            response.raise_for_status()
            data = response.json()
            orderbook_cache[cache_key] = data
        except Exception as e:
            print(f"Ошибка проверки ликвидности Gate для {symbol}: {e}")
            return False

    bids = data.get("bids", [])
    asks = data.get("asks", [])
    
    ask_qty = 0
    for ask in asks:
        try:
            ask_price, ask_volume = ask[0], ask[1]
            if safe_float(ask_price) <= price * (1 + SLIPPAGE_PERCENT / 100):
                ask_qty += safe_float(ask_volume) * safe_float(ask_price)
            if ask_qty >= trade_usdt:
                break
        except Exception as e:
            print(f"Ошибка обработки asks для {symbol} на Gate: {e}, данные: {ask}")
            continue
    if ask_qty < trade_usdt:
        return False

    bid_qty = 0
    for bid in bids:
        try:
            bid_price, bid_volume = bid[0], bid[1]
            if safe_float(bid_price) >= price * (1 - SLIPPAGE_PERCENT / 100):
                bid_qty += safe_float(bid_volume) * safe_float(bid_price)
            if bid_qty >= trade_usdt:
                break
        except Exception as e:
            print(f"Ошибка обработки bids для {symbol} на Gate: {e}, данные: {bid}")
            continue
    return bid_qty >= trade_usdt

def check_mexc_liquidity(symbol, price, trade_usdt=MIN_TRADE_USDT):
    cache_key = f"mexc_{symbol}"
    if cache_key in orderbook_cache:
        data = orderbook_cache[cache_key]
    else:
        try:
            url = f"{MEXC_ORDERBOOK_URL}{symbol}"
            response = requests.get(url, timeout=10, verify=certifi.where())
            response.raise_for_status()
            data = response.json()
            orderbook_cache[cache_key] = data
        except Exception as e:
            print(f"Ошибка проверки ликвидности MEXC для {symbol}: {e}")
            return False

    bids = data.get("data", {}).get("bids", [])
    asks = data.get("data", {}).get("asks", [])
    
    ask_qty = 0
    for ask in asks:
        try:
            ask_price, ask_volume = ask['price'], ask['quantity']
            if safe_float(ask_price) <= price * (1 + SLIPPAGE_PERCENT / 100):
                ask_qty += safe_float(ask_volume) * safe_float(ask_price)
            if ask_qty >= trade_usdt:
                break
        except Exception as e:
            print(f"Ошибка обработки asks для {symbol} на MEXC: {e}, данные: {ask}")
            continue
    if ask_qty < trade_usdt:
        return False

    bid_qty = 0
    for bid in bids:
        try:
            bid_price, bid_volume = bid['price'], bid['quantity']
            if safe_float(bid_price) >= price * (1 - SLIPPAGE_PERCENT / 100):
                bid_qty += safe_float(bid_volume) * safe_float(bid_price)
            if bid_qty >= trade_usdt:
                break
        except Exception as e:
            print(f"Ошибка обработки bids для {symbol} на MEXC: {e}, данные: {bid}")
            continue
    return bid_qty >= trade_usdt

def check_binance_liquidity(symbol, price, trade_usdt=MIN_TRADE_USDT):
    cache_key = f"binance_{symbol}"
    if cache_key in orderbook_cache:
        data = orderbook_cache[cache_key]
    else:
        try:
            url = f"{BINANCE_ORDERBOOK_URL}?symbol={symbol.replace('_', '')}&limit=100"
            response = requests.get(url, timeout=10, verify=certifi.where())
            response.raise_for_status()
            data = response.json()
            orderbook_cache[cache_key] = data
        except Exception as e:
            print(f"Ошибка проверки ликвидности Binance для {symbol}: {e}")
            return False

    bids = data.get("bids", [])
    asks = data.get("asks", [])
    
    ask_qty = 0
    for ask in asks:
        try:
            ask_price, ask_volume = ask[0], ask[1]
            if safe_float(ask_price) <= price * (1 + SLIPPAGE_PERCENT / 100):
                ask_qty += safe_float(ask_volume) * safe_float(ask_price)
            if ask_qty >= trade_usdt:
                break
        except Exception as e:
            print(f"Ошибка обработки asks для {symbol} на Binance: {e}, данные: {ask}")
            continue
    if ask_qty < trade_usdt:
        return False

    bid_qty = 0
    for bid in bids:
        try:
            bid_price, bid_volume = bid[0], bid[1]
            if safe_float(bid_price) >= price * (1 - SLIPPAGE_PERCENT / 100):
                bid_qty += safe_float(bid_volume) * safe_float(bid_price)
            if bid_qty >= trade_usdt:
                break
        except Exception as e:
            print(f"Ошибка обработки bids для {symbol} на Binance: {e}, данные: {bid}")
            continue
    return bid_qty >= trade_usdt

def check_bitget_liquidity(symbol, price, trade_usdt=MIN_TRADE_USDT):
    cache_key = f"bitget_{symbol}"
    if cache_key in orderbook_cache:
        data = orderbook_cache[cache_key]
    else:
        try:
            url = f"{BITGET_ORDERBOOK_URL}?symbol={symbol.replace('_', '')}&limit=100"
            response = requests.get(url, timeout=10, verify=certifi.where())
            response.raise_for_status()
            data = response.json()
            orderbook_cache[cache_key] = data
        except Exception as e:
            print(f"Ошибка проверки ликвидности Bitget для {symbol}: {e}")
            return False

    bids = data.get("data", {}).get("bids", [])
    asks = data.get("data", {}).get("asks", [])
    
    ask_qty = 0
    for ask in asks:
        try:
            ask_price, ask_volume = ask[0], ask[1]
            if safe_float(ask_price) <= price * (1 + SLIPPAGE_PERCENT / 100):
                ask_qty += safe_float(ask_volume) * safe_float(ask_price)
            if ask_qty >= trade_usdt:
                break
        except Exception as e:
            print(f"Ошибка обработки asks для {symbol} на Bitget: {e}, данные: {ask}")
            continue
    if ask_qty < trade_usdt:
        return False

    bid_qty = 0
    for bid in bids:
        try:
            bid_price, bid_volume = bid[0], bid[1]
            if safe_float(bid_price) >= price * (1 - SLIPPAGE_PERCENT / 100):
                bid_qty += safe_float(bid_volume) * safe_float(bid_price)
            if bid_qty >= trade_usdt:
                break
        except Exception as e:
            print(f"Ошибка обработки bids для {symbol} на Bitget: {e}, данные: {bid}")
            continue
    return bid_qty >= trade_usdt

def check_bybit_liquidity(symbol, price, trade_usdt=MIN_TRADE_USDT):
    cache_key = f"bybit_{symbol}"
    if cache_key in orderbook_cache:
        data = orderbook_cache[cache_key]
    else:
        try:
            url = f"{BYBIT_ORDERBOOK_URL}&symbol={symbol.replace('_', '')}&limit=100"
            response = requests.get(url, timeout=10, verify=certifi.where())
            response.raise_for_status()
            data = response.json()
            orderbook_cache[cache_key] = data
        except Exception as e:
            print(f"Ошибка проверки ликвидности Bybit для {symbol}: {e}")
            return False

    bids = data.get("result", {}).get("b", [])
    asks = data.get("result", {}).get("a", [])
    
    ask_qty = 0
    for ask in asks:
        try:
            ask_price, ask_volume = ask[0], ask[1]
            if safe_float(ask_price) <= price * (1 + SLIPPAGE_PERCENT / 100):
                ask_qty += safe_float(ask_volume) * safe_float(ask_price)
            if ask_qty >= trade_usdt:
                break
        except Exception as e:
            print(f"Ошибка обработки asks для {symbol} на Bybit: {e}, данные: {ask}")
            continue
    if ask_qty < trade_usdt:
        return False

    bid_qty = 0
    for bid in bids:
        try:
            bid_price, bid_volume = bid[0], bid[1]
            if safe_float(bid_price) >= price * (1 - SLIPPAGE_PERCENT / 100):
                bid_qty += safe_float(bid_volume) * safe_float(bid_price)
            if bid_qty >= trade_usdt:
                break
        except Exception as e:
            print(f"Ошибка обработки bids для {symbol} на Bybit: {e}, данные: {bid}")
            continue
    return bid_qty >= trade_usdt

def check_kucoin_liquidity(symbol, price, trade_usdt=MIN_TRADE_USDT):
    cache_key = f"kucoin_{symbol}"
    if cache_key in orderbook_cache:
        data = orderbook_cache[cache_key]
    else:
        try:
            kucoin_symbol = symbol.replace("BTC_USDT", "XBTUSDTM").replace("_USDT", "USDTM").replace("_", "-")
            url = f"{KUCOIN_ORDERBOOK_URL}?symbol={kucoin_symbol}"
            response = requests.get(url, timeout=10, verify=certifi.where())
            response.raise_for_status()
            data = response.json()
            if data.get("code") != "200000":
                print(f"Ошибка KuCoin ордербук API: {data.get('msg', 'Неизвестная ошибка')}")
                return False
            orderbook_cache[cache_key] = data
        except Exception as e:
            print(f"Ошибка проверки ликвидности KuCoin для {symbol}: {e}")
            return False

    bids = data.get("data", {}).get("bids", [])
    asks = data.get("data", {}).get("asks", [])

    ask_qty = 0
    for ask in asks:
        try:
            ask_price, ask_volume = ask[0], ask[1]
            if safe_float(ask_price) <= price * (1 + SLIPPAGE_PERCENT / 100):
                ask_qty += safe_float(ask_volume) * safe_float(ask_price)
            if ask_qty >= trade_usdt:
                break
        except Exception as e:
            print(f"Ошибка обработки asks для {symbol} на KuCoin: {e}, данные: {ask}")
            continue
    if ask_qty < trade_usdt:
        return False

    bid_qty = 0
    for bid in bids:
        try:
            bid_price, bid_volume = bid[0], bid[1]
            if safe_float(bid_price) >= price * (1 - SLIPPAGE_PERCENT / 100):
                bid_qty += safe_float(bid_volume) * safe_float(bid_price)
            if bid_qty >= trade_usdt:
                break
        except Exception as e:
            print(f"Ошибка обработки bids для {symbol} на KuCoin: {e}, данные: {bid}")
            continue
    return bid_qty >= trade_usdt

def check_okx_liquidity(symbol, price, trade_usdt=MIN_TRADE_USDT):
    cache_key = f"okx_{symbol}"
    if cache_key in orderbook_cache:
        data = orderbook_cache[cache_key]
    else:
        try:
            url = f"{OKX_ORDERBOOK_URL}?instId={symbol.replace('_', '-')}"
            response = requests.get(url, timeout=10, verify=certifi.where())
            response.raise_for_status()
            data = response.json()
            orderbook_cache[cache_key] = data
        except Exception as e:
            print(f"Ошибка проверки ликвидности OKX для {symbol}: {e}")
            return False

    bids = data.get("data", [{}])[0].get("bids", [])
    asks = data.get("data", [{}])[0].get("asks", [])
    
    ask_qty = 0
    for ask in asks:
        try:
            ask_price, ask_volume = ask[0], ask[1]
            if safe_float(ask_price) <= price * (1 + SLIPPAGE_PERCENT / 100):
                ask_qty += safe_float(ask_volume) * safe_float(ask_price)
            if ask_qty >= trade_usdt:
                break
        except Exception as e:
            print(f"Ошибка обработки asks для {symbol} на OKX: {e}, данные: {ask}")
            continue
    if ask_qty < trade_usdt:
        return False

    bid_qty = 0
    for bid in bids:
        try:
            bid_price, bid_volume = bid[0], bid[1]
            if safe_float(bid_price) >= price * (1 - SLIPPAGE_PERCENT / 100):
                bid_qty += safe_float(bid_volume) * safe_float(bid_price)
            if bid_qty >= trade_usdt:
                break
        except Exception as e:
            print(f"Ошибка обработки bids для {symbol} на OKX: {e}, данные: {bid}")
            continue
    return bid_qty >= trade_usdt

def get_gate_data():
    try:
        response = requests.get(GATE_TICKER_URL, timeout=10, verify=certifi.where())
        response.raise_for_status()
        data = response.json()
        result = {}
        for item in data:
            if not item['contract'].endswith('_USDT'):
                continue
            try:
                price = safe_float(item['last'])
                if price < 0.0001:
                    continue
                volume_base = safe_float(item.get('volume_24h_base', 0))
                result[item['contract']] = {'price': price, 'volume': volume_base * price}
            except Exception as e:
                print(f"Ошибка обработки данных Gate для {item.get('contract', 'unknown')}: {e}")
        return result
    except Exception as e:
        print("Ошибка при получении данных с Gate:", e)
        return {}

def get_mexc_data():
    try:
        response = requests.get(MEXC_TICKER_URL, timeout=10, verify=certifi.where())
        response.raise_for_status()
        data = response.json()
        result = {}
        for item in data['data']:
            if not item['symbol'].endswith('_USDT'):
                continue
            try:
                price = safe_float(item['lastPrice'])
                if price < 0.0001:
                    continue
                volume = safe_float(item.get('volume24', 0))
                result[item['symbol']] = {'price': price, 'volume': volume * price}
            except Exception as e:
                print(f"Ошибка обработки данных MEXC для {item.get('symbol', 'unknown')}: {e}")
        return result
    except Exception as e:
        print("Ошибка при получении данных с MEXC:", e)
        return {}

def get_binance_data():
    try:
        response = requests.get(BINANCE_TICKER_URL, timeout=10, verify=certifi.where())
        response.raise_for_status()
        data = response.json()
        result = {}
        for item in data:
            if not item["symbol"].endswith("USDT"):
                continue
            try:
                price = safe_float(item["price"])
                if price < 0.0001:
                    continue
                result[item["symbol"].replace("USDT", "_USDT")] = {'price': price, 'volume': 0}
            except Exception as e:
                print(f"Ошибка обработки данных Binance для {item.get('symbol', 'unknown')}: {e}")
        return result
    except Exception as e:
        print("Ошибка при получении данных с Binance:", e)
        return {}

def get_bitget_data():
    try:
        response = requests.get(BITGET_TICKER_URL, timeout=10, verify=certifi.where())
        response.raise_for_status()
        data = response.json()
        result = {}
        for item in data.get('data', []):
            if not item['symbol'].endswith('USDT'):
                continue
            try:
                price = safe_float(item['lastPr'])
                if price < 0.0001:
                    continue
                volume = safe_float(item.get('quoteVolume', 0))
                result[item['symbol'].replace("USDT", "_USDT").upper()] = {'price': price, 'volume': volume}
            except Exception as e:
                print(f"Ошибка обработки данных Bitget для {item.get('symbol', 'unknown')}: {e}")
        return result
    except Exception as e:
        print("Ошибка при получении данных с Bitget:", e)
        return {}

def get_bybit_data():
    try:
        response = requests.get(BYBIT_TICKER_URL, timeout=10, verify=certifi.where())
        response.raise_for_status()
        data = response.json()
        result = {}
        for item in data.get('result', {}).get('list', []):
            if not item['symbol'].endswith('USDT'):
                continue
            try:
                price = safe_float(item['lastPrice'])
                if price < 0.0001:
                    continue
                volume = safe_float(item.get('volume24h', 0))
                result[item['symbol'].replace("USDT", "_USDT").upper()] = {'price': price, 'volume': volume * price}
            except Exception as e:
                print(f"Ошибка обработки данных Bybit для {item.get('symbol', 'unknown')}: {e}")
        return result
    except Exception as e:
        print("Ошибка при получении данных с Bybit:", e)
        return {}

def get_kucoin_data():
    try:
        response = requests.get(KUCOIN_TICKER_URL, timeout=10, verify=certifi.where())
        response.raise_for_status()
        data = response.json()
        if data.get("code") != "200000":
            print(f"Ошибка KuCoin API: {data.get('msg', 'Неизвестная ошибка')}")
            return {}
        result = {}
        for item in data.get("data", []):
            if not item["symbol"].endswith("USDTM"):
                continue
            try:
                price = safe_float(item["lastTradePrice"])
                if price < 0.0001:
                    continue
                volume = safe_float(item.get("volValue", 0))
                symbol = item["symbol"].replace("XBT", "BTC").replace("-", "_").replace("USDTM", "_USDT").upper()
                result[symbol] = {"price": price, "volume": volume}
            except Exception as e:
                print(f"Ошибка обработки данных KuCoin для {item.get('symbol', 'unknown')}: {e}")
        return result
    except Exception as e:
        print(f"Ошибка при получении данных с KuCoin: {e}")
        return {}

def get_okx_data():
    try:
        response = requests.get(OKX_TICKER_URL, timeout=10, verify=certifi.where())
        response.raise_for_status()
        data = response.json()
        result = {}
        for item in data["data"]:
            if not item["instId"].endswith("USDT-SWAP"):
                continue
            try:
                price = safe_float(item["last"])
                if price < 0.0001:
                    continue
                volume = safe_float(item.get('volCcy24h', 0))
                result[item["instId"].replace("-", "_").upper()] = {'price': price, 'volume': volume}
            except Exception as e:
                print(f"Ошибка обработки данных OKX для {item.get('instId', 'unknown')}: {e}")
        return result
    except Exception as e:
        print("Ошибка при получении данных с OKX:", e)
        return {}

def calculate_profit(long_price, short_price):
    if long_price == 0:
        return 0
    raw_profit = (short_price / long_price - 1) * 100
    net_profit = raw_profit - COMMISSION_PERCENT
    return net_profit

def find_arbitrage():
    global orderbook_cache
    orderbook_cache = {}  # Очищаем кэш ордербуков

    # Получаем данные с бирж
    gate_prices = get_gate_data()
    mexc_prices = get_mexc_data()
    binance_prices = get_binance_data()
    bitget_prices = get_bitget_data()
    bybit_prices = get_bybit_data()
    kucoin_prices = get_kucoin_data()
    okx_prices = get_okx_data()

    if not any([gate_prices, mexc_prices, binance_prices, bitget_prices, bybit_prices, kucoin_prices, okx_prices]):
        print("Не удалось получить данные ни с одной биржи.")
        return

    all_exchanges = [
        ("Gate", gate_prices, check_gate_liquidity),
        ("MEXC", mexc_prices, check_mexc_liquidity),
        ("Binance", binance_prices, check_binance_liquidity),
        ("Bitget", bitget_prices, check_bitget_liquidity),
        ("Bybit", bybit_prices, check_bybit_liquidity),
        ("KuCoin", kucoin_prices, check_kucoin_liquidity),
        ("OKX", okx_prices, check_okx_liquidity)
    ]

    opportunities = []

    for i, (long_exchange, long_prices, long_liquidity_check) in enumerate(all_exchanges):
        for short_exchange, short_prices, short_liquidity_check in all_exchanges[i+1:]:
            common_pairs = set(long_prices.keys()) & set(short_prices.keys())
            
            for pair in common_pairs:
                symbol = pair.split("_")[0]
                if not contracts_match(symbol, long_exchange, short_exchange):
                    continue

                try:
                    long_price = long_prices[pair]['price']
                    short_price = short_prices[pair]['price']
                    long_volume = long_prices[pair]['volume']
                    short_volume = short_prices[pair]['volume']
                except Exception as e:
                    print(f"Ошибка доступа к данным для {pair} ({long_exchange}/{short_exchange}): {e}")
                    continue

                if long_price == 0 or short_price == 0:
                    continue

                if long_volume < MIN_VOLUME_USDT and long_volume != 0:
                    continue
                if short_volume < MIN_VOLUME_USDT and short_volume != 0:
                    continue

                max_price = max(long_price, short_price)
                min_price = min(long_price, short_price)
                if max_price / min_price > 5:
                    continue

                raw_profit = (short_price / long_price - 1) * 100
                if raw_profit > MAX_SPREAD_PERCENT:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Подозрительно высокий спред для {pair}: {raw_profit:.2f}% "
                          f"(long: {long_price} на {long_exchange}, short: {short_price} на {short_exchange})")
                    continue

                profit = calculate_profit(long_price, short_price)
                if profit <= MIN_PROFIT_PERCENT:
                    continue

                if not long_liquidity_check(pair, long_price):
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Недостаточная ликвидность для {pair} на {long_exchange}")
                    continue
                if not short_liquidity_check(pair, short_price):
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Недостаточная ликвидность для {pair} на {short_exchange}")
                    continue

                opportunities.append((pair, long_exchange, long_price, short_exchange, short_price, profit))

    opportunities.sort(key=lambda x: x[5], reverse=True)

    for pair, long_exchange, long_price, short_exchange, short_price, profit in opportunities:
        key = f"{pair}_{long_exchange}_{short_exchange}"
        if key not in shown_opportunities:
            shown_opportunities.add(key)
            message = (
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [НОВОЕ] {pair}: "
                f"Long на {long_exchange} по {long_price}, "
                f"Short на {short_exchange} по {short_price} — чистый спред: {profit:.2f}%"
            )
            print(message)
            send_telegram_message(message)

if __name__ == "__main__":
    load_token_contracts()
    while True:
        try:
            find_arbitrage()
            time.sleep(60)
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Ошибка в основном цикле: {e}")
            time.sleep(60)