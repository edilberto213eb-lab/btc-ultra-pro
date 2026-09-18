
import os
import requests
import pandas as pd
import ta
import time

TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

SYMBOLS = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]
DISPLAY = {"BTC-USDT":"BTCUSDT", "ETH-USDT":"ETHUSDT", "SOL-USDT":"SOLUSDT"}

def get_df(symbol):
    url = f"https://www.okx.com/api/v5/market/candles?instId={symbol}&bar=1H&limit=200"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15).json()
    data = r.get("data", [])
    if len(data) < 150:
        return None
    data = data[::-1]
    df = pd.DataFrame(data, columns=["ts","o","h","l","c","vol","volCcy","volCcyQuote","confirm"])
    for col in ["o","h","l","c","vol"]:
        df[col] = df[col].astype(float)
    return df

def check(symbol):
    df = get_df(symbol)
    if df is None:
        return
    close = df["c"]
    high = df["h"]
    low = df["l"]
    vol = df["vol"]
    price = float(close.iloc[-1])

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

    long = 0
    short = 0
    if ema9 > ema21: long += 15
    else: short += 15
    if price > ema50: long += 15
    else: short += 15
    if price > sma200: long += 15
    else: short += 15
    if 50 < rsi < 70: long += 20
    if 30 < rsi < 50: short += 20
    if macd_diff > 0: long += 15
    else: short += 15
    if vol_ratio > 1.2:
        if long > short: long += 10
        else: short += 10

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

    # FILTRO 75
    if score < 75:
        print(f"{DISPLAY[symbol]} sin señal {score}")
        return

    risk = abs(price - sl)
    rr1 = abs(tp1 - price) / risk if risk else 0
    rr2 = abs(tp2 - price) / risk if risk else 0
    rr3 = abs(tp3 - price) / risk if risk else 0

    conf = []
    if ema9 > ema21: conf.append("• EMA9 > EMA21")
    if price > ema50: conf.append("• Precio > EMA50")
    if price > sma50: conf.append("• Precio > SMA50")
    if price > sma100: conf.append("• Precio > SMA100")
    if price > sma200: conf.append("• Precio > SMA200")
    if 40 < rsi < 75: conf.append(f"• RSI favorable {rsi:.2f}")
    if (signal=="LONG" and price > sar) or (signal=="SHORT" and price < sar):
        conf.append(f"• SAR {'alcista' if signal=='LONG' else 'bajista'}")
    if vol_ratio > 1.2: conf.append(f"• Volumen x{vol_ratio:.2f}")
    conf_text = "\n".join(conf)

    msg = f"""{emoji} ULTRA PRO — {DISPLAY[symbol]}

SEÑAL: {signal}

🔥 SCORE: {score}/100

💰 Entrada:
{price:.2f}

━━━━━━━━━━━━━━━━━━

📊 MEDIAS

EMA 9: {ema9:.2f}
EMA 21: {ema21:.2f}
EMA 50: {ema50:.2f}

SMA 50: {sma50:.2f}
SMA 100: {sma100:.2f}
SMA 200: {sma200:.2f}

━━━━━━━━━━━━━━━━━━

📊 MOMENTUM

RSI: {rsi:.2f}
StochRSI: {stoch:.2f}

━━━━━━━━━━━━━━━━━━

📊 VOLATILIDAD

ATR: {atr:.2f}
SAR: {sar:.2f}

━━━━━━━━━━━━━━━━━━

🔵 BOLLINGER

Superior: {bb_high:.2f}
Media: {bb_mid:.2f}
Inferior: {bb_low:.2f}

━━━━━━━━━━━━━━━━━━

📦 VOLUMEN

x{vol_ratio:.2f}

━━━━━━━━━━━━━━━━━━

🎯 PLAN DE OPERACIÓN

📍 ENTRADA
{price:.2f}

🛑 STOP LOSS
{sl:.2f}

🎯 TP1
{tp1:.2f}

🎯 TP2
{tp2:.2f}

🎯 TP3
{tp3:.2f}

━━━━━━━━━━━━━━━━━━

⚖️ R:R

TP1 → 1:{rr1:.2f}
TP2 → 1:{rr2:.2f}
TP3 → 1:{rr3:.2f}

✅ CONFIRMACIONES
{conf_text}

━━━━━━━━━━━━━━━━━━

⚠️ Vela cerrada.
⚠️ Análisis técnico.
⚠️ NO ejecuta operaciones.
"""
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": msg}, timeout=15)
    print(f"Enviado {DISPLAY[symbol]} {score}")

def main():
    print("INICIANDO ULTRA PRO 75...")
    for s in SYMBOLS:
        check(s)
        time.sleep(1)

if __name__ == "__main__":
    main()
