# -*- coding: utf-8 -*-
"""
Gerçek Zamanlı Piyasa Verisi İndirici Modülü (Live Data Fetcher)
- Kriptolar (50 Varlık): Binance Public REST API (Spot & Futures) - 100% Gerçek Canlı Veri
- Hisseler (11 Varlık): NASDAQ / Yahoo Finance (TSLA, NVDA, AAPL, META...)
- Emtialar (6 Varlık): Altın, Gümüş, Petrol (WTI & Brent), Doğal Gaz, Bakır
- Forex (7 Varlık): EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD, USD/CHF, NZD/USD
"""
import os
import sys
import json
import time
import urllib.request
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

class LiveDataFetcher:
    # Yahoo Ticker Eşlemeleri (Hisseler, Emtialar, Forex)
    YAHOO_MAP = {
        "TSLA": "TSLA", "NVDA": "NVDA", "AAPL": "AAPL", "MSFT": "MSFT",
        "AMZN": "AMZN", "GOOGL": "GOOGL", "META": "META", "AMD": "AMD",
        "COIN": "COIN", "SPY": "SPY", "QQQ": "QQQ",
        "XAU/USD": "GC=F", "XAUUSD": "GC=F",
        "XAG/USD": "SI=F", "XAGUSD": "SI=F",
        "USOIL": "CL=F", "UKOIL": "BZ=F",
        "NATGAS": "NG=F", "COPPER": "HG=F",
        "EUR/USD": "EURUSD=X", "EURUSD": "EURUSD=X",
        "GBP/USD": "GBPUSD=X", "GBPUSD": "GBPUSD=X",
        "USD/JPY": "JPY=X", "USDJPY": "JPY=X",
        "AUD/USD": "AUDUSD=X", "AUDUSD": "AUDUSD=X",
        "USD/CAD": "CAD=X", "USDCAD": "CAD=X",
        "USD/CHF": "CHF=X", "USDCHF": "CHF=X",
        "NZD/USD": "NZDUSD=X", "NZDUSD": "NZDUSD=X"
    }

    @staticmethod
    def get_all_binance_live_prices() -> dict:
        """Binance'deki tüm koinlerin anlık canlı fiyatlarını tek bir 1 saniyelik sorguyla çeker."""
        url = "https://api.binance.com/api/v3/ticker/price"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            res = urllib.request.urlopen(req, timeout=5)
            data = json.loads(res.read().decode("utf-8"))
            return {item["symbol"]: float(item["price"]) for item in data}
        except Exception:
            return {}

    @classmethod
    def fetch_binance(cls, symbol: str = "BTCUSDT", interval: str = "5m", limit: int = 250) -> pd.DataFrame:
        """Binance Spot veya Vadeli İşlemlerden gerçek canlı 5m mumlarını çeker."""
        clean_sym = symbol.replace("/", "").replace(" ", "").upper()
        if not clean_sym.endswith("USDT"):
            clean_sym += "USDT"

        # 1. Önce Spot API dene
        url_spot = f"https://api.binance.com/api/v3/klines?symbol={clean_sym}&interval={interval}&limit={limit}"
        data = None
        try:
            req = urllib.request.Request(url_spot, headers={"User-Agent": "Mozilla/5.0"})
            res = urllib.request.urlopen(req, timeout=5)
            data = json.loads(res.read().decode("utf-8"))
        except Exception:
            # 2. Spotta yoksa Futures dene (Örn: KASUSDT)
            try:
                url_fut = f"https://fapi.binance.com/fapi/v1/klines?symbol={clean_sym}&interval={interval}&limit={limit}"
                req = urllib.request.Request(url_fut, headers={"User-Agent": "Mozilla/5.0"})
                res = urllib.request.urlopen(req, timeout=5)
                data = json.loads(res.read().decode("utf-8"))
            except Exception:
                return pd.DataFrame()

        if not data or not isinstance(data, list):
            return pd.DataFrame()

        df = pd.DataFrame(data, columns=[
            "time", "open", "high", "low", "close", "volume",
            "close_time", "qav", "num_trades", "taker_base_vol", "taker_quote_vol", "ignore"
        ])
        df["datetime"] = pd.to_datetime(df["time"], unit="ms")
        df.set_index("datetime", inplace=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        return df[["open", "high", "low", "close", "volume"]]

    @classmethod
    def fetch_yahoo(cls, ticker: str, range_str: str = "5d", interval: str = "5m") -> pd.DataFrame:
        """Yahoo Finance üzerinden hisse senedi, emtia ve forex mumlarını çeker."""
        yf_sym = cls.YAHOO_MAP.get(ticker, ticker)

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
                df = cls.fetch_binance(symbol=symbol, interval="5m", limit=250)
            else:
                df = cls.fetch_yahoo(ticker=symbol, range_str="5d", interval="5m")

            if len(df) > 0:
                df.to_csv(fp)
                return True
        except Exception:
            pass
        return False

    @classmethod
    def sync_all_assets_concurrent(cls, assets_list: list, data_dir: str, max_workers: int = 8) -> int:
        """Tüm 74 varlığın mumlarını çoklu iş parçacıklarıyla (threading) 3-4 saniyede günceller."""
        def sync_one(item):
            return cls.update_asset_csv(item, data_dir)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(sync_one, assets_list))
        return sum(1 for r in results if r)
