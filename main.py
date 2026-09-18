import os
import requests
import math
import time

TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
INTERVAL = "15m"
LIMIT = 250
MIN_SCORE = 70
SL_ATR = 1.5
TP1_ATR = 1.5
TP2_ATR = 2.5
TP3_ATR = 3.5

def send_telegram(message):
    if not TOKEN or not CHAT_ID:
        print("Falta las variables de Telegram")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, data=data, timeout=15)
        print(f"Telegram {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print("Error Telegram:", e)

def get_klines(symbol):
    url = "https://data-api.binance.vision/api/v3/klines"
    params = {"symbol": symbol, "interval": INTERVAL, "limit": LIMIT}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else None
    except Exception as e:
        print(f"Error Binance {symbol}:", e)
        return None

def sma(values, period):
    return sum(values[-period:]) / period if len(values) >= period else None

def ema(values, period):
    if len(values) < period: return None
    multiplier = 2 / (period + 1)
    result = sum(values[:period]) / period
    for price in values[period:]:
        result = (price - result) * multiplier + result
    return result

def calculate_rsi(values, period=14):
    if len(values) < period + 1: return None
    gains, losses = [], []
    for i in range(1, len(values)):
        change = values[i] - values[i-1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0: return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def rsi_series(values, period=14):
    result = []
    if len(values) < period + 2: return result
    for i in range(period + 1, len(values) + 1):
        rsi = calculate_rsi(values[:i], period)
        if rsi is not None: result.append(rsi)
    return result

def calculate_stoch_rsi(values, rsi_period=14, stoch_period=14):
    rsis = rsi_series(values, rsi_period)
    if len(rsis) < stoch_period: return None
    window = rsis[-stoch_period:]
    lowest, highest = min(window), max(window)
    if highest == lowest: return 50.0
    return (rsis[-1] - lowest) / (highest - lowest) * 100

def bollinger(values, period=20, deviations=2):
    if len(values) < period: return None, None, None
    window = values[-period:]
    middle = sum(window) / period
    std = math.sqrt(sum((x - middle) ** 2 for x in window) / period)
    return middle + deviations * std, middle, middle - deviations * std

def calculate_atr(highs, lows, closes, period=14):
    if len(closes) < period + 1: return None
    true_ranges = []
    for i in range(1, len(closes)):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        true_ranges.append(tr)
    if len(true_ranges) < period: return None
    atr = sum(true_ranges[:period]) / period
    for tr in true_ranges[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr

def calculate_psar(highs, lows, step=0.02, maximum=0.2):
    if len(highs) < 3: return None, None
    bull = True
    sar, extreme, acc = lows[0], highs[0], step
    for i in range(1, len(highs)):
        prev_sar = sar
        if bull:
            sar = prev_sar + acc * (extreme - prev_sar)
            sar = min(sar, lows[i-1], lows[i-2]) if i>=2 else min(sar, lows[i-1])
            if lows[i] < sar:
                bull, sar, extreme, acc = False, extreme, lows[i], step
            elif highs[i] > extreme:
                extreme = highs[i]
                acc = min(acc+step, maximum)
        else:
            sar = prev_sar + acc * (extreme - prev_sar)
            sar = max(sar, highs[i-1], highs[i-2]) if i>=2 else max(sar, highs[i-1])
            if highs[i] > sar:
                bull, sar, extreme, acc = True, extreme, highs[i], step
            elif lows[i] < extreme:
                extreme = lows[i]
                acc = min(acc+step, maximum)
    return sar, bull

def calculate_trade_levels(signal, entry, atr):
    if signal == "LONG":
        sl, tp1, tp2, tp3 = entry-SL_ATR*atr, entry+TP1_ATR*atr, entry+TP2_ATR*atr, entry+TP3_ATR*atr
    elif signal == "SHORT":
        sl, tp1, tp2, tp3 = entry+SL_ATR*atr, entry-TP1_ATR*atr, entry-TP2_ATR*atr, entry-TP3_ATR*atr
    else: return None
    risk = abs(entry-sl)
    return {"entry":entry,"stop_loss":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"rr1":abs(tp1-entry)/risk,"rr2":abs(tp2-entry)/risk,"rr3":abs(tp3-entry)/risk}

def analyze(symbol):
    data = get_klines(symbol)
    if not data or len(data) < 220: return None
    closed = data[:-1]
    opens = [float(x[1]) for x in closed]
    highs = [float(x[2]) for x in closed]
    lows = [float(x[3]) for x in closed]
    closes = [float(x[4]) for x in closed]
    volumes = [float(x[5]) for x in closed]
    price = closes[-1]
    ema9, ema21, ema50 = ema(closes,9), ema(closes,21), ema(closes,50)
    sma50, sma100, sma200 = sma(closes,50), sma(closes,100), sma(closes,200)
    rsi = calculate_rsi(closes,14)
    stoch_rsi = calculate_stoch_rsi(closes,14,14)
    upper, middle, lower = bollinger(closes,20,2)
    atr = calculate_atr(highs,lows,closes,14)
    psar, psar_bull = calculate_psar(highs,lows)
    avg_vol = sma(volumes[:-1],20)
    vol_ratio = volumes[-1]/avg_vol if avg_vol else 1
    long_score, short_score = 0,0
    long_reasons, short_reasons = [],[]
    if ema9 > ema21: long_score+=10; long_reasons.append("EMA9 > EMA21")
    elif ema9 < ema21: short_score+=10; short_reasons.append("EMA9 < EMA21")
    if price > ema50: long_score+=10; long_reasons.append("Precio > EMA50")
    elif price < ema50: short_score+=10; short_reasons.append("Precio < EMA50")
    if price > sma50: long_score+=5; long_reasons.append("Precio > SMA50")
    elif price < sma50: short_score+=5; short_reasons.append("Precio < SMA50")
    if price > sma100: long_score+=5; long_reasons.append("Precio > SMA100")
    elif price < sma100: short_score+=5; short_reasons.append("Precio < SMA100")
    if price > sma200: long_score+=15; long_reasons.append("Precio > SMA200")
    elif price < sma200: short_score+=15; short_reasons.append("Precio < SMA200")
    if 50 <= rsi <= 70: long_score+=10; long_reasons.append(f"RSI {rsi:.1f}")
    elif 30 <= rsi < 50: short_score+=10; short_reasons.append(f"RSI {rsi:.1f}")
    if stoch_rsi <= 25: long_score+=10; long_reasons.append(f"StochRSI bajo {stoch_rsi:.1f}")
    elif stoch_rsi >= 75: short_score+=10; short_reasons.append(f"StochRSI alto {stoch_rsi:.1f}")
    if psar_bull: long_score+=10; long_reasons.append("SAR alcista")
    else: short_score+=10; short_reasons.append("SAR bajista")
    if lows[-1] <= lower and closes[-1] > opens[-1]: long_score+=15; long_reasons.append("Rebote Bollinger inf")
    if highs[-1] >= upper and closes[-1] < opens[-1]: short_score+=15; short_reasons.append("Rechazo Bollinger sup")
    if vol_ratio >= 1.2:
        if closes[-1] > opens[-1]: long_score+=10; long_reasons.append(f"Volumen x{vol_ratio:.2f}")
        else: short_score+=10; short_reasons.append(f"Volumen x{vol_ratio:.2f}")
    if long_score >= MIN_SCORE and long_score > short_score:
        signal, score, reasons = "LONG", long_score, long_reasons
    elif short_score >= MIN_SCORE and short_score > long_score:
        signal, score, reasons = "SHORT", short_score, short_reasons
    else:
        signal, score, reasons = "SIN OPERACIÓN", max(long_score, short_score), []
    trade = calculate_trade_levels(signal, price, atr) if signal in ["LONG","SHORT"] else None
    return {"symbol":symbol,"signal":signal,"score":score,"price":price,"rsi":rsi,"stoch_rsi":stoch_rsi,"ema9":ema9,"ema21":ema21,"ema50":ema50,"sma50":sma50,"sma100":sma100,"sma200":sma200,"upper":upper,"middle":middle,"lower":lower,"atr":atr,"psar":psar,"psar_bull":psar_bull,"volume_ratio":vol_ratio,"trade":trade,"reasons":reasons}

def format_message(r):
    emoji = "🟢" if r["signal"]=="LONG" else "🔴" if r["signal"]=="SHORT" else "⚪"
    msg = f"{emoji} ULTRA PRO — {r['symbol']}\n\nSEÑAL: {r['signal']}\nSCORE: {r['score']}/100\nEntrada: {r['price']:.2f}\n\nRSI: {r['rsi']:.2f} | StochRSI: {r['stoch_rsi']:.2f}\nEMA9: {r['ema9']:.2f} EMA21: {r['ema21']:.2f} EMA50: {r['ema50']:.2f}\nSMA200: {r['sma200']:.2f}\nATR: {r['atr']:.2f} SAR: {r['psar']:.2f}\nBollinger: {r['upper']:.2f} / {r['middle']:.2f} / {r['lower']:.2f}\nVol: x{r['volume_ratio']:.2f}\n"
    if r["trade"]:
        t=r["trade"]
        msg+=f"\n🎯 ENTRADA {t['entry']:.2f}\n🛑 SL {t['stop_loss']:.2f}\nTP1 {t['tp1']:.2f} | TP2 {t['tp2']:.2f} | TP3 {t['tp3']:.2f}\nRR {t['rr1']:.2f} / {t['rr2']:.2f} / {t['rr3']:.2f}\n"
    if r["reasons"]:
        msg+="\n✅ "+ ", ".join(r["reasons"])+"\n"
    return msg

# ==== MODO CRON JOB ====
if __name__ == "__main__":
    print("🚀 INICIANDO SCAN CRON JOB...")
    mensajes = 0
    for sym in SYMBOLS:
        print(f"Analizando {sym}...")
        res = analyze(sym)
        if not res:
            continue
        # Solo enviamos si hay señal fuerte, pero también avisamos si no hay nada
        texto = format_message(res)
        send_telegram(texto)
        mensajes+=1
        time.sleep(2)

    if mensajes==0:
        send_telegram("⚪ BTC ULTRA PRO - Sin señales en este momento (todo por debajo de 70 pts)")
    print("✅ FIN CRON")
