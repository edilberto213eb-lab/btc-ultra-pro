import os
import requests
import pandas as pd
import ta
import time
from datetime import datetime

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

SYMBOLS = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]
DISPLAY = {"BTC-USDT":"BTCUSDT", "ETH-USDT":"ETHUSDT", "SOL-USDT":"SOLUSDT"}

def get_df(symbol):
    try:
        # OKX - funciona en USA, sin bloqueo
        url = f"https://www.okx.com/api/v5/market/candles?instId={symbol}&bar=4H&limit=100"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=15).json()
        data = r.get("data", [])
        if not data or len(data) < 50:
            print(f"{symbol} sin datos: {r}")
            return None
        data = data[::-1] # voltear
        df = pd.DataFrame(data, columns=["ts","o","h","l","c","vol","volCcy","volCcyQuote","confirm"])
        df[["o","h","l","c"]] = df[["o","h","l","c"]].astype(float)
        return df
    except Exception as e:
        print(f"Error {symbol}: {e}")
        return None

def send(symbol, signal, score, price):
    if "LONG" in signal:
        sl = price * 0.985
        tp1 = price * 1.025
        tp2 = price * 1.05
    else:
        sl = price * 1.015
        tp1 = price * 0.975
        tp2 = price * 0.95
    hora = datetime.now().strftime('%H:%M - %d/%m')
    text = f"🚀 {DISPLAY[symbol]} {signal}\nScore: {score}/100\nPrecio: {price:.2f}\n\nSL: {sl:.2f}\nTP1: {tp1:.2f}\nTP2: {tp2:.2f}\n\n{hora}"
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=10)
        print(f"Alerta enviada {symbol}")
    except Exception as e:
        print(f"Error telegram {e}")

def check(symbol):
    df = get_df(symbol)
    if df is None or len(df) < 50:
        print(f"{symbol} saltado")
        return
    c = df["c"]
    price = float(c.iloc[-1])
    rsi = float(ta.momentum.RSIIndicator(c, 14).rsi().iloc[-1])
    ema20 = float(ta.trend.EMAIndicator(c, 20).ema_indicator().iloc[-1])
    ema50 = float(ta.trend.EMAIndicator(c, 50).ema_indicator().iloc[-1])
    macd_diff = float(ta.trend.MACD(c).macd_diff().iloc[-1])

    long = 0
    short = 0
    if rsi < 40: long += 30
    if rsi > 60: short += 30
    if rsi < 30: long += 10
    if rsi > 70: short += 10
    if ema20 > ema50: long += 35
    else: short += 35
    if macd_diff > 0: long += 25
    else: short += 25
    if price > ema20: long += 10
    else: short += 10

    print(f"{DISPLAY[symbol]} | LONG {long} | SHORT {short} | RSI {rsi:.1f} | {price}")

    if long >= 70:
        send(symbol, "LONG 🟢", long, price)
    elif short >= 70:
        send(symbol, "SHORT 🔴", short, price)
    else:
        print(f"{symbol} sin señal fuerte")

def main():
    print("INICIANDO MOTOR TELEGRAM - OKX...")
    for s in SYMBOLS:
        check(s)
        time.sleep(1)
    print("Analisis terminado OK")

if __name__ == "__main__":
    main()
