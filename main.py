import os, requests, pandas as pd, ta, time
from datetime import datetime

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

def get_df(symbol):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=4h&limit=100"
        r = requests.get(url, timeout=10).json()
        df = pd.DataFrame(r, columns=["ot","o","h","l","c","v","ct","qv","n","tb","tq","i"])
        df[["o","h","l","c"]] = df[["o","h","l","c"]].astype(float)
        return df
    except Exception as e:
        print(f"Error {symbol}: {e}")
        return None

def check(symbol):
    df = get_df(symbol)
    if df is None: return
    
    c = df["c"]
    price = c.iloc[-1]
    rsi = ta.momentum.RSIIndicator(c, 14).rsi().iloc[-1]
    ema20 = ta.trend.EMAIndicator(c, 20).ema_indicator().iloc[-1]
    ema50 = ta.trend.EMAIndicator(c, 50).ema_indicator().iloc[-1]
    macd_diff = ta.trend.MACD(c).macd_diff().iloc[-1]

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

    # Filtro extra
    if price > ema20: long += 10
    else: short += 10

    print(f"{symbol} | LONG {long} | SHORT {short} | RSI {rsi:.1f}")

    if long >= 70:
        send(symbol, "LONG 🟢", long, price)
    elif short >= 70:
        send(symbol, "SHORT 🔴", short, price)

def send(symbol, signal, score, price):
    if "LONG" in signal:
        sl = price * 0.985
        tp1 = price * 1.025
        tp2 = price * 1.05
    else:
        sl = price * 1.015
        tp1 = price * 0.975
        tp2 = price * 0.95

    text = f"""
🚀 *{symbol} {signal}*
*Score:* {score}/100
*Precio:* {price:.2f}

*SL:* {sl:.2f}
*TP1:* {tp1:.2
