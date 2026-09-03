# -*- coding: utf-8 -*-
"""
Gerçek Zamanlı Piyasa Verisi İndirici Modülü (Live Data Fetcher)
- Kriptolar: Binance Public REST API (Ücretsiz, anlık canlı veri)
- Hisse Senetleri & Emtialar: Yahoo Finance / NASDAQ (TSLA, META, NVDA, AAPL, XAU, USOIL...)
- Otomatik 60 saniyede bir canlı senkronizasyon.
"""
import os
import sys
import json
import time
import urllib.request
import pandas as pd
from datetime import datetime

class LiveDataFetcher:
    PRIORITY_SYMBOLS = [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "DOGE/USDT", "XRP/USDT",
        "META", "TSLA", "NVDA", "AAPL", "AMZN", "MSFT",
        "XAU/USD", "USOIL"
    ]

    @staticmethod
    def fetch_binance(symbol: str = "BTCUSDT", interval: str = "5m", limit: int = 200) -> pd.DataFrame:
        """Binance borsasından gerçek canlı 5m mumlarını çeker."""
        clean_sym = symbol.replace("/", "").replace(" ", "").upper()
        if not clean_sym.endswith("USDT"):
            clean_sym += "USDT"

        url = f"https://api.binance.com/api/v3/klines?symbol={clean_sym}&interval={interval}&limit={limit}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        res = urllib.request.urlopen(req, timeout=6)
        data = json.loads(res.read().decode("utf-8"))

        df = pd.DataFrame(data, columns=[
            "time", "open", "high", "low", "close", "volume",
            "close_time", "qav", "num_trades", "taker_base_vol", "taker_quote_vol", "ignore"
        ])
        df["datetime"] = pd.to_datetime(df["time"], unit="ms")
        df.set_index("datetime", inplace=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        return df[["open", "high", "low", "close", "volume"]]

    @staticmethod
    def fetch_yahoo(ticker: str, range_str: str = "5d", interval: str = "5m") -> pd.DataFrame:
        """Yahoo Finance üzerinden gerçek NASDAQ/NYSE hisse ve emtia mumlarını çeker."""
        ticker_map = {
            "TSLA": "TSLA", "NVDA": "NVDA", "AAPL": "AAPL", "MSFT": "MSFT",
            "AMZN": "AMZN", "GOOGL": "GOOGL", "META": "META", "AMD": "AMD",
            "COIN": "COIN", "SPY": "SPY", "QQQ": "QQQ",
            "XAU/USD": "GC=F", "XAUUSD": "GC=F",
            "XAG/USD": "SI=F", "XAGUSD": "SI=F",
            "USOIL": "CL=F", "UKOIL": "BZ=F",
            "NATGAS": "NG=F", "COPPER": "HG=F",
            "EUR/USD": "EURUSD=X", "EURUSD": "EURUSD=X",
            "GBP/USD": "GBPUSD=X", "GBPUSD": "GBPUSD=X",
            "USD/JPY": "JPY=X", "USDJPY": "JPY=X"
        }
        yf_sym = ticker_map.get(ticker, ticker)

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_sym}?interval={interval}&range={range_str}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        res = urllib.request.urlopen(req, timeout=6)
        data = json.loads(res.read().decode("utf-8"))

        res_data = data["chart"]["result"][0]
        timestamps = res_data["timestamp"]
        quote = res_data["indicators"]["quote"][0]

        df = pd.DataFrame({
            "datetime": pd.to_datetime(timestamps, unit="s"),
            "open": quote["open"],
            "high": quote["high"],
            "low": quote["low"],
            "close": quote["close"],
            "volume": quote.get("volume", [1000]*len(timestamps))
        }).dropna()
        df.set_index("datetime", inplace=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        return df

    @classmethod
    def update_asset_csv(cls, asset_info: dict, data_dir: str) -> bool:
        """Belirtilen varlığın CSV dosyasını gerçek borsa verileriyle günceller."""
        symbol = asset_info["symbol"]
        cat = asset_info.get("category", "crypto")
        file_name = asset_info["file"]
        fp = os.path.join(data_dir, file_name)

        try:
            if cat == "crypto":
                df = cls.fetch_binance(symbol=symbol, interval="5m", limit=300)
            else:
                df = cls.fetch_yahoo(ticker=symbol, range_str="5d", interval="5m")

            if len(df) > 0:
                df.to_csv(fp)
                return True
        except Exception as e:
            pass
        return False

    @classmethod
    def sync_all_priority_assets(cls, assets_list: list, data_dir: str):
        """Her 1 dakikada bir öncelikli varlıkları otomatik olarak Binance ve NASDAQ ile senkronize eder."""
        updated = 0
        for item in assets_list:
            if item["symbol"] in cls.PRIORITY_SYMBOLS:
                if cls.update_asset_csv(item, data_dir):
                    updated += 1
        return updated
