import os
import json
import requests
import pandas as pd
import ta
import time

# ============================================================
# CONFIGURACIÓN
# ============================================================

TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

SYMBOLS = [
    "BTC-USDT",
    "ETH-USDT",
    "SOL-USDT"
]

DISPLAY = {
    "BTC-USDT": "BTCUSDT",
    "ETH-USDT": "ETHUSDT",
    "SOL-USDT": "SOLUSDT"
}

BINANCE_SYMBOL = {
    "BTC-USDT": "BTCUSDT",
    "ETH-USDT": "ETHUSDT",
    "SOL-USDT": "SOLUSDT"
}

# Movimiento que consideraremos importante
WHALE_MOVE_USD = {
    "BTC-USDT": 900,
    "ETH-USDT": 60,
    "SOL-USDT": 8
}

STATE_FILE = "monster_state.json"

BINANCE_BASE = "https://fapi.binance.com"


# ============================================================
# ESTADO PERSISTENTE
# ============================================================

def load_state():
    try:
        if not os.path.exists(STATE_FILE):
            return {}
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error leyendo estado: {e}")
        return {}


def save_state(state):
    try:
        temp_file = STATE_FILE + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(temp_file, STATE_FILE)
    except Exception as e:
        print(f"Error guardando estado: {e}")


STATE = load_state()


# ============================================================
# OKX
# ============================================================

def get_df(symbol):
    try:
        url = (
            "https://www.okx.com/api/v5/market/candles"
            f"?instId={symbol}&bar=1H&limit=200"
        )
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15
        )
        r.raise_for_status()
        data = r.json().get("data", [])

        if len(data) < 150:
            return None

        data = data[::-1]
        df = pd.DataFrame(
            data,
            columns=[
                "ts", "o", "h", "l", "c",
                "vol", "volCcy", "volCcyQuote", "confirm"
            ]
        )

        for col in ["o", "h", "l", "c", "vol"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna()
        return df

    except Exception as e:
        print(f"Error OKX {symbol}: {e}")
        return None


# ============================================================
# BINANCE REQUEST
# ============================================================

def binance_get(endpoint, params=None):
    try:
        r = requests.get(
            BINANCE_BASE + endpoint,
            params=params or {},
            headers={"User-Agent": "BTC-Ultra-Monster/2.0"},
            timeout=10
        )
        r.raise_for_status()
        data = r.json()

        if isinstance(data, dict):
            if "code" in data and data["code"] < 0:
                print(f"Binance API: {data}")
                return None
        return data

    except Exception as e:
        print(f"Binance error {endpoint}: {e}")
        return None


# ============================================================
# PRECIO BINANCE
# ============================================================

def get_binance_price(symbol):
    data = binance_get("/fapi/v1/ticker/price", {"symbol": symbol})
    if not data:
        return None
    try:
        return float(data["price"])
    except Exception:
        return None


# ============================================================
# KLINES BINANCE 5M
# ============================================================

def get_binance_klines(symbol):
    data = binance_get(
        "/fapi/v1/klines",
        {"symbol": symbol, "interval": "5m", "limit": 25}
    )
    if not data:
        return None

    try:
        rows = []
        for x in data:
            rows.append({
                "open": float(x[1]),
                "high": float(x[2]),
                "low": float(x[3]),
                "close": float(x[4]),
                "volume": float(x[5])
            })
        return rows
    except Exception as e:
        print(f"Error Klines {symbol}: {e}")
        return None


# ============================================================
# VARIACIÓN VOLUMEN
# ============================================================

def calculate_volume_variation(klines):
    if not klines or len(klines) < 21:
        return None

    current = klines[-2]
    previous = klines[-22:-2]
    avg_volume = sum(x["volume"] for x in previous) / len(previous)

    if avg_volume <= 0:
        return None

    ratio = current["volume"] / avg_volume
    variation = ((current["volume"] - avg_volume) / avg_volume) * 100

    return {
        "volume": current["volume"],
        "average": avg_volume,
        "ratio": ratio,
        "variation": variation
    }


# ============================================================
# VELA ANORMAL
# ============================================================

def candle_detector(klines):
    if not klines or len(klines) < 22:
        return None

    candle = klines[-2]
    open_price = candle["open"]
    close_price = candle["close"]
    high = candle["high"]
    low = candle["low"]

    body = abs(close_price - open_price)
    range_price = high - low

    if range_price <= 0:
        return None

    body_percent = (body / range_price) * 100
    movement = close_price - open_price

    return {
        "movement": movement,
        "body_percent": body_percent,
        "bullish": close_price > open_price,
        "bearish": close_price < open_price,
        "range": range_price
    }


# ============================================================
# OPEN INTEREST
# ============================================================

def get_oi_history(symbol):
    data = binance_get(
        "/futures/data/openInterestHist",
        {"symbol": symbol, "period": "5m", "limit": 12}
    )
    if not data:
        return None

    try:
        values = [float(item["sumOpenInterest"]) for item in data]
        return values
    except Exception:
        return None


def calculate_oi_change(symbol):
    values = get_oi_history(symbol)
    if not values or len(values) < 2:
        return None

    old = values[0]
    new = values[-1]
    if old <= 0:
        return None

    return ((new - old) / old) * 100


# ============================================================
# TAKER BUY / SELL
# ============================================================

def get_taker_data(symbol):
    data = binance_get(
        "/futures/data/takerBuySellVol",
        {"symbol": symbol, "period": "5m", "limit": 1}
    )
    if not data:
        return None

    try:
        item = data[-1]
        buy = float(item["takerBuyVol"])
        sell = float(item["takerSellVol"])
        total = buy + sell

        if total <= 0:
            return None

        return {
            "buy": buy,
            "sell": sell,
            "buy_pct": (buy / total) * 100,
            "sell_pct": (sell / total) * 100
        }
    except Exception as e:
        print(f"Taker error {symbol}: {e}")
        return None


# ============================================================
# LONG / SHORT GLOBAL
# ============================================================

def get_long_short(symbol):
    data = binance_get(
        "/futures/data/globalLongShortAccountRatio",
        {"symbol": symbol, "period": "5m", "limit": 1}
    )
    if not data:
        return None

    try:
        item = data[-1]
        return {
            "ratio": float(item["longShortRatio"]),
            "long": float(item["longAccount"]) * 100,
            "short": float(item["shortAccount"]) * 100
        }
    except Exception:
        return None


# ============================================================
# TOP TRADERS
# ============================================================

def get_top_trader_ratio(symbol):
    data = binance_get(
        "/futures/data/topLongShortAccountRatio",
        {"symbol": symbol, "period": "5m", "limit": 1}
    )
    if not data:
        return None

    try:
        item = data[-1]
        return {
            "ratio": float(item["longShortRatio"]),
            "long": float(item["longAccount"]) * 100,
            "short": float(item["shortAccount"]) * 100
        }
    except Exception:
        return None


# ============================================================
# ORDER BOOK
# ============================================================

def get_orderbook(symbol):
    data = binance_get(
        "/fapi/v1/depth",
        {"symbol": symbol, "limit": 50}
    )
    if not data:
        return None

    try:
        bids = data.get("bids", [])
        asks = data.get("asks", [])

        bid_volume = sum(float(x[1]) for x in bids)
        ask_volume = sum(float(x[1]) for x in asks)
        total = bid_volume + ask_volume

        if total <= 0:
            return None

        imbalance = ((bid_volume - ask_volume) / total) * 100

        return {
            "bid": bid_volume,
            "ask": ask_volume,
            "imbalance": imbalance
        }
    except Exception:
        return None


# ============================================================
# DETECTOR MONSTER
# ============================================================

def whale_detector(symbol, price, volume_data, candle, oi_change,
                   taker, long_short, top_trader, orderbook):

    score = 0
    reasons = []
    long_points = 0
    short_points = 0

    # VOLUMEN
    if volume_data:
        ratio = volume_data["ratio"]
        if ratio >= 1.5:
            score += 2
            reasons.append(f"Volumen x{ratio:.2f}")
        if ratio >= 2.0:
            score += 1
            reasons.append("Volumen EXTREMO")

    # VELA
    if candle:
        if candle["body_percent"] >= 60:
            score += 1
            if candle["bullish"]:
                long_points += 1
            else:
                short_points += 1
            reasons.append(f"Vela fuerte {candle['movement']:+.2f}")

    # OPEN INTEREST
    if oi_change is not None:
        if abs(oi_change) >= 1.5:
            score += 2
            reasons.append(f"OI {oi_change:+.2f}%")

    # TAKER
    if taker:
        if taker["buy_pct"] >= 65:
            score += 2
            long_points += 2
            reasons.append(f"Taker Buy {taker['buy_pct']:.1f}%")
        elif taker["sell_pct"] >= 65:
            score += 2
            short_points += 2
            reasons.append(f"Taker Sell {taker['sell_pct']:.1f}%")

    # LONG / SHORT
    if long_short:
        ratio = long_short["ratio"]
        if ratio >= 1.8:
            score += 1
            long_points += 1
            reasons.append(f"Long/Short {ratio:.2f}")
        elif ratio <= 0.55:
            score += 1
            short_points += 1
            reasons.append(f"Long/Short {ratio:.2f}")

    # TOP TRADERS
    if top_trader:
        ratio = top_trader["ratio"]
        if ratio >= 1.7:
            score += 2
            long_points += 2
            reasons.append(f"Top traders LONG {ratio:.2f}")
        elif ratio <= 0.60:
            score += 2
            short_points += 2
            reasons.append(f"Top traders SHORT {ratio:.2f}")

    # ORDER BOOK
    if orderbook:
        imbalance = orderbook["imbalance"]
        if imbalance >= 20:
            score += 1
            long_points += 1
            reasons.append(f"Order Book comprador +{imbalance:.1f}%")
        elif imbalance <= -20:
            score += 1
            short_points += 1
            reasons.append(f"Order Book vendedor {imbalance:.1f}%")

    # DIRECCIÓN
    if long_points >= short_points + 2:
        direction = "LONG"
    elif short_points >= long_points + 2:
        direction = "SHORT"
    else:
        direction = "NEUTRAL"

    # NIVEL
    if score >= 8 and direction != "NEUTRAL":
        level = 3
    elif score >= 5 and direction != "NEUTRAL":
        level = 2
    elif score >= 3:
        level = 1
    else:
        level = 0

    return {
        "score": score,
        "level": level,
        "direction": direction,
        "reasons": reasons
    }


# ============================================================
# ANÁLISIS PRINCIPAL
# ============================================================

def check(symbol):
    df = get_df(symbol)
    if df is None:
        return

    close = df["c"]
    high = df["h"]
    low = df["l"]
    vol = df["vol"]

    price = float(close.iloc[-1])

    # INDICADORES
    ema9 = float(ta.trend.EMAIndicator(close, 9).ema_indicator().iloc[-1])
    ema21 = float(ta.trend.EMAIndicator(close, 21).ema_indicator().iloc[-1])
    ema50 = float(ta.trend.EMAIndicator(close, 50).ema_indicator().iloc[-1])
    sma50 = float(ta.trend.SMAIndicator(close, 50).sma_indicator().iloc[-1])
    sma100 = float(ta.trend.SMAIndicator(close, 100).sma_indicator().iloc[-1])
    sma200 = float(ta.trend.SMAIndicator(close, 200).sma_indicator().iloc[-1])
    rsi = float(ta.momentum.RSIIndicator(close, 14).rsi().iloc[-1])
    stoch = float(ta.momentum.StochRSIIndicator(close, 14).stochrsi_k().iloc[-1] * 100)
    atr = float(ta.volatility.AverageTrueRange(high, low, close, 14).average_true_range().iloc[-1])
    sar = float(ta.trend.PSARIndicator(high, low, close).psar().iloc[-1])

    bb = ta.volatility.BollingerBands(close, 20, 2)
    bb_high = float(bb.bollinger_hband().iloc[-1])
    bb_mid = float(bb.bollinger_mavg().iloc[-1])
    bb_low = float(bb.bollinger_lband().iloc[-1])

    vol_sma20 = float(vol.rolling(20).mean().iloc[-1])
    vol_ratio = float(vol.iloc[-1] / vol_sma20) if vol_sma20 > 0 else 1.0
    macd_diff = float(ta.trend.MACD(close).macd_diff().iloc[-1])

    # SCORE ORIGINAL
    long = 0
    short = 0

    if ema9 > ema21:
        long += 15
    else:
        short += 15

    if price > ema50:
        long += 15
    else:
        short += 15

    if price > sma200:
        long += 15
    else:
        short += 15

    if 50 < rsi < 70:
        long += 20
    if 30 < rsi < 50:
        short += 20

    if macd_diff > 0:
        long += 15
    else:
        short += 15

    if vol_ratio > 1.2:
        if long > short:
            long += 10
        else:
            short += 10

    score = max(long, short)

    if long > short:
        signal = "LONG"
        emoji = "🟢"
        sl = price - (atr * 1.5)
        tp1 = price + (atr * 1.5)
        tp2 = price + (atr * 2.5)
        tp3 = price + (atr * 3.5)
    else:
        signal = "SHORT"
        emoji = "🔴"
        sl = price + (atr * 1.5)
        tp1 = price - (atr * 1.5)
        tp2 = price - (atr * 2.5)
        tp3 = price - (atr * 3.5)

    # FILTRO
    if score < 75:
        print(f"{DISPLAY[symbol]} sin señal {score}")
        return

    # R:R
    risk = abs(price - sl)
    rr1 = abs(tp1 - price) / risk if risk else 0
    rr2 = abs(tp2 - price) / risk if risk else 0
    rr3 = abs(tp3 - price) / risk if risk else 0

    # CONFIRMACIONES
    conf = []
    if ema9 > ema21:
        conf.append("• EMA9 > EMA21")
    if price > ema50:
        conf.append("• Precio > EMA50")
    if price > sma50:
        conf.append("• Precio > SMA50")
    if price > sma100:
        conf.append("• Precio > SMA100")
    if price > sma200:
        conf.append("• Precio > SMA200")
    if 40 < rsi < 75:
        conf.append(f"• RSI favorable {rsi:.2f}")
    if (signal == "LONG" and price > sar) or (signal == "SHORT" and price < sar):
        conf.append("• SAR confirmado")
    if vol_ratio > 1.2:
        conf.append(f"• Volumen x{vol_ratio:.2f}")

    # BINANCE DATA
    bsymbol = BINANCE_SYMBOL[symbol]
    binance_price = get_binance_price(bsymbol)
    klines = get_binance_klines(bsymbol)
    volume_data = calculate_volume_variation(klines)
    candle = candle_detector(klines)
    oi_change = calculate_oi_change(bsymbol)
    taker = get_taker_data(bsymbol)
    long_short = get_long_short(bsymbol)
    top_trader = get_top_trader_ratio(bsymbol)
    orderbook = get_orderbook(bsymbol)

    # MOVIMIENTO DESDE ÚLTIMA EJECUCIÓN
    old_price = STATE.get(symbol, {}).get("price")

    if binance_price is not None:
        if old_price is not None:
            price_change = binance_price - float(old_price)
        else:
            price_change = 0

        STATE[symbol] = {
            "price": binance_price,
            "timestamp": int(time.time())
        }
        save_state(STATE)
    else:
        price_change = 0

    # MONSTER
    monster = whale_detector(
        symbol=symbol,
        price=binance_price if binance_price else price,
        volume_data=volume_data,
        candle=candle,
        oi_change=oi_change,
        taker=taker,
        long_short=long_short,
        top_trader=top_trader,
        orderbook=orderbook
    )

    # MOVIMIENTO $ THRESHOLD
    move_threshold = WHALE_MOVE_USD[symbol]
    movement_alert = abs(price_change) >= move_threshold

    if movement_alert:
        monster["score"] += 2
        if price_change > 0:
            monster["direction"] = "LONG"
            monster["reasons"].append(f"Movimiento +{price_change:.2f}")
        else:
            monster["direction"] = "SHORT"
            monster["reasons"].append(f"Movimiento {price_change:.2f}")

    # NIVEL FINAL
    if monster["score"] >= 8 and monster["direction"] != "NEUTRAL":
        level = 3
    elif monster["score"] >= 5:
        level = 2
    elif monster["score"] >= 3:
        level = 1
    else:
        level = 0

    monster["level"] = level

    # MONSTER SCORE
    monster_score = min(100, int(score * 0.60 + monster["score"] * 5))

    # ESTADO BALLENA
    if level == 3:
        whale_status = "🐋🐋🐋 NIVEL 3\nACTIVIDAD GRANDE CONFIRMADA"
    elif level == 2:
        whale_status = "🐋🐋 NIVEL 2\nPRESIÓN FUERTE"
    elif level == 1:
        whale_status = "🐋 NIVEL 1\nACTIVIDAD DETECTADA"
    else:
        whale_status = "⚪ SIN ACTIVIDAD GRANDE CONFIRMADA"

    # DIRECCIÓN
    if monster["direction"] == "LONG":
        whale_direction = "🟢 PRESIÓN COMPRADORA"
    elif monster["direction"] == "SHORT":
        whale_direction = "🔴 PRESIÓN VENDEDORA"
    else:
        whale_direction = "⚪ DIRECCIÓN NO CONFIRMADA"

    # TEXTOS
    volume_text = (
        f"x{volume_data['ratio']:.2f}\nVariación: {volume_data['variation']:+.1f}%"
        if volume_data else "No disponible"
    )

    taker_text = (
        f"🟢 Buy: {taker['buy_pct']:.1f}%\n🔴 Sell: {taker['sell_pct']:.1f}%"
        if taker else "No disponible"
    )

    oi_text = f"{oi_change:+.2f}%" if oi_change is not None else "No disponible"

    ls_text = (
        f"Ratio: {long_short['ratio']:.2f}\n"
        f"Long: {long_short['long']:.1f}%\n"
        f"Short: {long_short['short']:.1f}%"
        if long_short else "No disponible"
    )

    top_text = (
        f"Ratio: {top_trader['ratio']:.2f}\n"
        f"Long: {top_trader['long']:.1f}%\n"
        f"Short: {top_trader['short']:.1f}%"
        if top_trader else "No disponible"
    )

    book_text = (
        f"Bid: {orderbook['bid']:.2f}\n"
        f"Ask: {orderbook['ask']:.2f}\n"
        f"Imbalance: {orderbook['imbalance']:+.1f}%"
        if orderbook else "No disponible"
    )

    reasons_text = (
        "\n".join("• " + x for x in monster["reasons"])
        if monster["reasons"] else "• Sin anomalías suficientes"
    )

    # MENSAJE
    msg = f"""{emoji} ULTRA PRO — {DISPLAY[symbol]}

SEÑAL: {signal}

🔥 SCORE ORIGINAL: {score}/100
🐉 MONSTER SCORE: {monster_score}/100

💰 ENTRADA
{price:.2f}

━━━━━━━━━━━━━━━━━━

🐋 WHALE MONSTER

{whale_status}

{whale_direction}

Puntuación ballena:
{monster["score"]}

Movimiento Binance:
{price_change:+.2f}

Señales detectadas:
{reasons_text}

━━━━━━━━━━━━━━━━━━

📊 VARIACIÓN DE VOLUMEN

{volume_text}

━━━━━━━━━━━━━━━━━━

⚡ TAKER BUY / SELL

{taker_text}

━━━━━━━━━━━━━━━━━━

📈 OPEN INTEREST

Variación:
{oi_text}

━━━━━━━━━━━━━━━━━━

⚖️ LONG / SHORT

{ls_text}

━━━━━━━━━━━━━━━━━━

👑 TOP TRADERS

{top_text}

━━━━━━━━━━━━━━━━━━

📖 ORDER BOOK

{book_text}

━━━━━━━━━━━━━━━━━━

🎯 STOP LOSS / TAKE PROFIT

SL: {sl:.2f}
TP1: {tp1:.2f}  (R:R {rr1:.2f})
TP2: {tp2:.2f}  (R:R {rr2:.2f})
TP3: {tp3:.2f}  (R:R {rr3:.2f})

━━━━━━━━━━━━━━━━━━

✅ CONFIRMACIONES

{chr(10).join(conf) if conf else "• Sin confirmaciones adicionales"}
"""

    # Enviar a Telegram
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": msg,
            "parse_mode": "HTML"
        }
        requests.post(url, json=payload, timeout=15)
        print(f"{DISPLAY[symbol]} → SEÑAL ENVIADA | Score {score} | Monster {monster_score}")
    except Exception as e:
        print(f"Error enviando Telegram {symbol}: {e}")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("INICIANDO ULTRA PRO 75...")
    
    for symbol in SYMBOLS:
        try:
            check(symbol)
        except Exception as e:
            print(f"Error procesando {symbol}: {e}")
    
    print("Ciclo completado.")
