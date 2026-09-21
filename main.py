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
    variation = ((current["volume"] - avg_volume) / avg_volume) 
