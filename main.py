import os
import time
import math
import threading
import requests
from flask import Flask

# =========================================================
# CONFIGURACIÓN
# =========================================================

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

INTERVAL = "15m"
LIMIT = 250
CHECK_EVERY = 60

MIN_SCORE = 70

ATR_PERIOD = 14

SL_ATR = 1.5
TP1_ATR = 1.5
TP2_ATR = 2.5
TP3_ATR = 3.5

# =========================================================
# SERVIDOR PARA RENDER
# =========================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "BTC Ultra Pro Bot funcionando"


@app.route("/health")
def health():
    return "OK"


# =========================================================
# TELEGRAM
# =========================================================
def send_telegram(message):
    if not TOKEN or not CHAT_ID:
        print("Falta las variables de Telegram")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message
    }
    try:
        r = requests.post(url, data=data, timeout=10)
        print("Telegram:", r.status_code, r.text)
    except Exception as e:
        print("Error Telegram:", e)

# =========================================================
# BINANCE FUTURES
# =========================================================

def get_klines(symbol):

    url = "https://api.binance.com/fapi/v1/klines"

    params = {
        "symbol": symbol,
        "interval": INTERVAL,
        "limit": LIMIT
    }

    try:

        response = requests.get(
            url,
            params=params,
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(data, list):
            return None

        return data

    except Exception as e:

        print(
            f"Error Binance {symbol}:",
            e
        )

        return None


# =========================================================
# SMA
# =========================================================

def sma(values, period):

    if len(values) < period:
        return None

    return sum(
        values[-period:]
    ) / period


# =========================================================
# EMA
# =========================================================

def ema(values, period):

    if len(values) < period:
        return None

    multiplier = 2 / (period + 1)

    result = sum(
        values[:period]
    ) / period

    for price in values[period:]:

        result = (
            (price - result)
            * multiplier
        ) + result

    return result


# =========================================================
# RSI
# =========================================================

def calculate_rsi(values, period=14):

    if len(values) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(1, len(values)):

        change = (
            values[i]
            - values[i - 1]
        )

        gains.append(
            max(change, 0)
        )

        losses.append(
            max(-change, 0)
        )

    avg_gain = (
        sum(gains[:period])
        / period
    )

    avg_loss = (
        sum(losses[:period])
        / period
    )

    for i in range(
        period,
        len(gains)
    ):

        avg_gain = (
            (
                avg_gain * (period - 1)
            )
            + gains[i]
        ) / period

        avg_loss = (
            (
                avg_loss * (period - 1)
            )
            + losses[i]
        ) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss

    return 100 - (
        100 / (1 + rs)
    )


# =========================================================
# RSI SERIES
# =========================================================

def rsi_series(values, period=14):

    result = []

    if len(values) < period + 2:
        return result

    for i in range(
        period + 1,
        len(values) + 1
    ):

        rsi = calculate_rsi(
            values[:i],
            period
        )

        if rsi is not None:
            result.append(rsi)

    return result


# =========================================================
# STOCH RSI
# =========================================================

def calculate_stoch_rsi(
    values,
    rsi_period=14,
    stoch_period=14
):

    rsis = rsi_series(
        values,
        rsi_period
    )

    if len(rsis) < stoch_period:
        return None

    window = rsis[-stoch_period:]

    current_rsi = rsis[-1]

    lowest = min(window)
    highest = max(window)

    if highest == lowest:
        return 50.0

    return (
        (current_rsi - lowest)
        / (highest - lowest)
    ) * 100


# =========================================================
# BOLLINGER
# =========================================================

def bollinger(
    values,
    period=20,
    deviations=2
):

    if len(values) < period:
        return None, None, None

    window = values[-period:]

    middle = sum(window) / period

    variance = sum(
        (x - middle) ** 2
        for x in window
    ) / period

    std = math.sqrt(variance)

    upper = (
        middle
        + deviations * std
    )

    lower = (
        middle
        - deviations * std
    )

    return upper, middle, lower


# =========================================================
# ATR
# =========================================================

def calculate_atr(
    highs,
    lows,
    closes,
    period=14
):

    if len(closes) < period + 1:
        return None

    true_ranges = []

    for i in range(1, len(closes)):

        high = highs[i]
        low = lows[i]
        previous_close = closes[i - 1]

        tr = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close)
        )

        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    atr = (
        sum(true_ranges[:period])
        / period
    )

    for tr in true_ranges[period:]:

        atr = (
            (
                atr * (period - 1)
            )
            + tr
        ) / period

    return atr


# =========================================================
# PARABOLIC SAR
# =========================================================

def calculate_psar(
    highs,
    lows,
    step=0.02,
    maximum=0.2
):

    if len(highs) < 3:
        return None, None

    bull = True

    sar = lows[0]
    extreme = highs[0]
    acceleration = step

    for i in range(1, len(highs)):

        previous_sar = sar

        if bull:

            sar = (
                previous_sar
                + acceleration
                * (
                    extreme
                    - previous_sar
                )
            )

            if i >= 2:

                sar = min(
                    sar,
                    lows[i - 1],
                    lows[i - 2]
                )

            else:

                sar = min(
                    sar,
                    lows[i - 1]
                )

            if lows[i] < sar:

                bull = False

                sar = extreme
                extreme = lows[i]
                acceleration = step

            elif highs[i] > extreme:

                extreme = highs[i]

                acceleration = min(
                    acceleration + step,
                    maximum
                )

        else:

            sar = (
                previous_sar
                + acceleration
                * (
                    extreme
                    - previous_sar
                )
            )

            if i >= 2:

                sar = max(
                    sar,
                    highs[i - 1],
                    highs[i - 2]
                )

            else:

                sar = max(
                    sar,
                    highs[i - 1]
                )

            if highs[i] > sar:

                bull = True

                sar = extreme
                extreme = highs[i]
                acceleration = step

            elif lows[i] < extreme:

                extreme = lows[i]

                acceleration = min(
                    acceleration + step,
                    maximum
                )

    return sar, bull


# =========================================================
# NIVELES LONG / SHORT
# =========================================================

def calculate_trade_levels(
    signal,
    entry,
    atr
):

    if signal == "LONG":

        stop_loss = (
            entry
            - SL_ATR * atr
        )

        tp1 = (
            entry
            + TP1_ATR * atr
        )

        tp2 = (
            entry
            + TP2_ATR * atr
        )

        tp3 = (
            entry
            + TP3_ATR * atr
        )

    elif signal == "SHORT":

        stop_loss = (
            entry
            + SL_ATR * atr
        )

        tp1 = (
            entry
            - TP1_ATR * atr
        )

        tp2 = (
            entry
            - TP2_ATR * atr
        )

        tp3 = (
            entry
            - TP3_ATR * atr
        )

    else:

        return None

    risk = abs(
        entry - stop_loss
    )

    return {
        "entry": entry,
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "rr1": abs(tp1 - entry) / risk,
        "rr2": abs(tp2 - entry) / risk,
        "rr3": abs(tp3 - entry) / risk
    }


# =========================================================
# ANÁLISIS
# =========================================================

def analyze(symbol):

    data = get_klines(symbol)

    if not data or len(data) < 220:
        return None

    # Ignoramos la vela todavía abierta
    closed = data[:-1]

    opens = [float(x[1]) for x in closed]
    highs = [float(x[2]) for x in closed]
    lows = [float(x[3]) for x in closed]
    closes = [float(x[4]) for x in closed]
    volumes = [float(x[5]) for x in closed]

    price = closes[-1]

    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    ema50 = ema(closes, 50)

    sma50 = sma(closes, 50)
    sma100 = sma(closes, 100)
    sma200 = sma(closes, 200)

    rsi = calculate_rsi(closes, 14)

    stoch_rsi = calculate_stoch_rsi(
        closes,
        14,
        14
    )

    upper, middle, lower = bollinger(
        closes,
        20,
        2
    )

    atr = calculate_atr(
        highs,
        lows,
        closes,
        14
    )

    psar, psar_bull = calculate_psar(
        highs,
        lows
    )

    average_volume = sma(
        volumes[:-1],
        20
    )

    current_volume = volumes[-1]

    if average_volume:
        volume_ratio = (
            current_volume
            / average_volume
        )
    else:
        volume_ratio = 1

    # =====================================================
    # SCORE
    # =====================================================

    long_score = 0
    short_score = 0

    long_reasons = []
    short_reasons = []

    # EMA 9/21
    if ema9 > ema21:

        long_score += 10
        long_reasons.append(
            "EMA9 > EMA21"
        )

    elif ema9 < ema21:

        short_score += 10
        short_reasons.append(
            "EMA9 < EMA21"
        )

    # EMA50
    if price > ema50:

        long_score += 10
        long_reasons.append(
            "Precio > EMA50"
        )

    elif price < ema50:

        short_score += 10
        short_reasons.append(
            "Precio < EMA50"
        )

    # SMA50
    if price > sma50:

        long_score += 5
        long_reasons.append(
            "Precio > SMA50"
        )

    elif price < sma50:

        short_score += 5
        short_reasons.append(
            "Precio < SMA50"
        )

    # SMA100
    if price > sma100:

        long_score += 5
        long_reasons.append(
            "Precio > SMA100"
        )

    elif price < sma100:

        short_score += 5
        short_reasons.append(
            "Precio < SMA100"
        )

    # SMA200
    if price > sma200:

        long_score += 15
        long_reasons.append(
            "Precio > SMA200"
        )

    elif price < sma200:

        short_score += 15
        short_reasons.append(
            "Precio < SMA200"
        )

    # RSI
    if 50 <= rsi <= 70:

        long_score += 10
        long_reasons.append(
            f"RSI favorable {rsi:.1f}"
        )

    elif 30 <= rsi < 50:

        short_score += 10
        short_reasons.append(
            f"RSI favorable {rsi:.1f}"
        )

    # StochRSI
    if stoch_rsi <= 25:

        long_score += 10
        long_reasons.append(
            f"StochRSI bajo {stoch_rsi:.1f}"
        )

    elif stoch_rsi >= 75:

        short_score += 10
        short_reasons.append(
            f"StochRSI alto {stoch_rsi:.1f}"
        )

    # SAR
    if psar_bull:

        long_score += 10
        long_reasons.append(
            "SAR alcista"
        )

    else:

        short_score += 10
        short_reasons.append(
            "SAR bajista"
        )

    # Bollinger
    candle_green = closes[-1] > opens[-1]
    candle_red = closes[-1] < opens[-1]

    if (
        lows[-1] <= lower
        and candle_green
    ):

        long_score += 15
        long_reasons.append(
            "Rebote Bollinger inferior"
        )

    if (
        highs[-1] >= upper
        and candle_red
    ):

        short_score += 15
        short_reasons.append(
            "Rechazo Bollinger superior"
        )

    # Volumen
    if volume_ratio >= 1.20:

        if candle_green:

            long_score += 10
            long_reasons.append(
                f"Volumen x{volume_ratio:.2f}"
            )

        elif candle_red:

            short_score += 10
            short_reasons.append(
                f"Volumen x{volume_ratio:.2f}"
            )

    # =====================================================
    # SEÑAL
    # =====================================================

    if (
        long_score >= MIN_SCORE
        and long_score > short_score
    ):

        signal = "LONG"
        score = long_score
        reasons = long_reasons

    elif (
        short_score >= MIN_SCORE
        and short_score > long_score
    ):

        signal = "SHORT"
        score = short_score
        reasons = short_reasons

    else:

        signal = "SIN OPERACIÓN"
        score = max(
            long_score,
            short_score
        )
        reasons = []

    # =====================================================
    # NIVELES
    # =====================================================

    trade = None

    if signal in ["LONG", "SHORT"]:

        trade = calculate_trade_levels(
            signal,
            price,
            atr
        )

    return {
        "symbol": symbol,
        "signal": signal,
        "score": score,
        "price": price,
        "rsi": rsi,
        "stoch_rsi": stoch_rsi,
        "ema9": ema9,
        "ema21": ema21,
        "ema50": ema50,
        "sma50": sma50,
        "sma100": sma100,
        "sma200": sma200,
        "upper": upper,
        "middle": middle,
        "lower": lower,
        "atr": atr,
        "psar": psar,
        "psar_bull": psar_bull,
        "volume_ratio": volume_ratio,
        "trade": trade,
        "candle_id": closed[-1][0],
        "reasons": reasons
    }


# =========================================================
# MENSAJE TELEGRAM
# =========================================================

def format_message(r):

    if r["signal"] == "LONG":
        emoji = "🟢"

    elif r["signal"] == "SHORT":
        emoji = "🔴"

    else:
        emoji = "⚪"

    message = f"""
{emoji} ULTRA PRO — {r["symbol"]}

SEÑAL: {r["signal"]}

🔥 SCORE: {r["score"]}/100

💰 Entrada:
{r["price"]:.2f}

━━━━━━━━━━━━━━━━━━

📊 MEDIAS

EMA 9: {r["ema9"]:.2f}
EMA 21: {r["ema21"]:.2f}
EMA 50: {r["ema50"]:.2f}

SMA 50: {r["sma50"]:.2f}
SMA 100: {r["sma100"]:.2f}
SMA 200: {r["sma200"]:.2f}

━━━━━━━━━━━━━━━━━━

📊 MOMENTUM

RSI: {r["rsi"]:.2f}
StochRSI: {r["stoch_rsi"]:.2f}

━━━━━━━━━━━━━━━━━━

📊 VOLATILIDAD

ATR: {r["atr"]:.2f}
SAR: {r["psar"]:.2f}

━━━━━━━━━━━━━━━━━━

🔵 BOLLINGER

Superior: {r["upper"]:.2f}
Media: {r["middle"]:.2f}
Inferior: {r["lower"]:.2f}

━━━━━━━━━━━━━━━━━━

📦 VOLUMEN

x{r["volume_ratio"]:.2f}

"""

    if r["trade"]:

        t = r["trade"]

        message += f"""
━━━━━━━━━━━━━━━━━━

🎯 PLAN DE OPERACIÓN

📍 ENTRADA
{t["entry"]:.2f}

🛑 STOP LOSS
{t["stop_loss"]:.2f}

🎯 TP1
{t["tp1"]:.2f}

🎯 TP2
{t["tp2"]:.2f}

🎯 TP3
{t["tp3"]:.2f}

━━━━━━━━━━━━━━━━━━

⚖️ R:R

TP1 → 1:{t["rr1"]:.2f}
TP2 → 1:{t["rr2"]:.2f}
TP3 → 1:{t["rr3"]:.2f}

"""

    if r["reasons"]:

        message += "\n✅ CONFIRMACIONES\n"

        for reason in r["reasons"]:

            message += (
                f"• {reason}\n"
            )

    message += """
━━━━━━━━━━━━━━━━━━

⚠️ Vela cerrada.
⚠️ Análisis técnico.
⚠️ NO ejecuta operaciones.
"""

    return message


# =========================================================
# MOTOR
# =========================================================

def bot_loop():

    last_alert = {}

    send_telegram(
        "🤖 BTC ULTRA PRO INICIADO\n\n"
        "15 minutos\n"
        "BTC / ETH / SOL\n\n"
        "Bollinger + RSI + StochRSI\n"
        "EMA + SMA + SAR + ATR\n"
        "Volumen + SL + TP1/TP2/TP3"
    )

    while True:

        try:

            for symbol in SYMBOLS:

                result = analyze(symbol)

                if result is None:
                    continue

                print(
                    symbol,
                    result["signal"],
                    result["score"]
                )

                if result["signal"] in [
                    "LONG",
                    "SHORT"
                ]:

                    candle_id = result[
                        "candle_id"
                    ]

                    if (
                        last_alert.get(symbol)
                        != candle_id
                    ):

                        send_telegram(
                            format_message(result)
                        )

                        last_alert[
                            symbol
                        ] = candle_id

            time.sleep(CHECK_EVERY)

        except Exception as e:

            print(
                "Error:",
                e
            )

            time.sleep(60)

# =========================================================
# ARRANQUE PARA GUNICORN / RENDER
# =========================================================


print("🚀 INICIANDO MOTOR TELEGRAM...")

bot_thread = threading.Thread(
    target=bot_loop,
    daemon=True
)

bot_thread.start()

print("🚀 HILO TELEGRAM INICIADO")

    
