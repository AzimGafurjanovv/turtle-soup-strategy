# -*- coding: utf-8 -*-
"""
Turtle Soup Veri Yükleme ve Gerçekçi Piyasa Mikro-Yapısı Veri Üretici Modülü
Top 50 Kripto + Emtia (Altın, Gümüş, Petrol WTI/Brent, Gaz) + Hisse Senetleri (Tesla, Nvidia, Apple...) + Forex
Toplam 74+ Varlık Desteği
"""
import os
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np
import pandas as pd

class DataLoader:
    # 74 Varlık Tanımı: Kripto + Emtia & Petrol + Hisseler + Forex
    ASSETS = [
        # --- 1. EMTİA, PETROL & METALLER (6 Varlık) ---
        {"symbol": "XAU/USD", "file": "XAUUSD_5m.csv", "base_price": 2510.0, "dec": 2, "tv": "OANDA:XAUUSD", "name": "Altın (Gold Spot)", "category": "commodity"},
        {"symbol": "XAG/USD", "file": "XAGUSD_5m.csv", "base_price": 28.80, "dec": 3, "tv": "OANDA:XAGUSD", "name": "Gümüş (Silver Spot)", "category": "commodity"},
        {"symbol": "USOIL", "file": "USOIL_5m.csv", "base_price": 74.50, "dec": 2, "tv": "TVC:USOIL", "name": "Ham Petrol (WTI Crude)", "category": "commodity"},
        {"symbol": "UKOIL", "file": "UKOIL_5m.csv", "base_price": 78.20, "dec": 2, "tv": "TVC:UKOIL", "name": "Brent Petrol", "category": "commodity"},
        {"symbol": "NATGAS", "file": "NATGAS_5m.csv", "base_price": 2.25, "dec": 3, "tv": "TVC:NATGAS", "name": "Doğal Gaz (Natural Gas)", "category": "commodity"},
        {"symbol": "COPPER", "file": "COPPER_5m.csv", "base_price": 4.18, "dec": 4, "tv": "COMEX:HG1!", "name": "Bakır (Copper)", "category": "commodity"},

        # --- 2. HİSSE SENETLERİ & ENDEKSLER (11 Varlık) ---
        {"symbol": "TSLA", "file": "TSLA_5m.csv", "base_price": 220.0, "dec": 2, "tv": "NASDAQ:TSLA", "name": "Tesla Inc.", "category": "stock"},
        {"symbol": "NVDA", "file": "NVDA_5m.csv", "base_price": 118.0, "dec": 2, "tv": "NASDAQ:NVDA", "name": "Nvidia Corporation", "category": "stock"},
        {"symbol": "AAPL", "file": "AAPL_5m.csv", "base_price": 225.0, "dec": 2, "tv": "NASDAQ:AAPL", "name": "Apple Inc.", "category": "stock"},
        {"symbol": "MSFT", "file": "MSFT_5m.csv", "base_price": 415.0, "dec": 2, "tv": "NASDAQ:MSFT", "name": "Microsoft Corp.", "category": "stock"},
        {"symbol": "AMZN", "file": "AMZN_5m.csv", "base_price": 178.0, "dec": 2, "tv": "NASDAQ:AMZN", "name": "Amazon.com Inc.", "category": "stock"},
        {"symbol": "GOOGL", "file": "GOOGL_5m.csv", "base_price": 162.0, "dec": 2, "tv": "NASDAQ:GOOGL", "name": "Alphabet (Google)", "category": "stock"},
        {"symbol": "META", "file": "META_5m.csv", "base_price": 510.0, "dec": 2, "tv": "NASDAQ:META", "name": "Meta Platforms", "category": "stock"},
        {"symbol": "AMD", "file": "AMD_5m.csv", "base_price": 142.0, "dec": 2, "tv": "NASDAQ:AMD", "name": "Advanced Micro Devices", "category": "stock"},
        {"symbol": "COIN", "file": "COIN_5m.csv", "base_price": 185.0, "dec": 2, "tv": "NASDAQ:COIN", "name": "Coinbase Global", "category": "stock"},
        {"symbol": "SPY", "file": "SPY_5m.csv", "base_price": 552.0, "dec": 2, "tv": "AMEX:SPY", "name": "S&P 500 Index ETF", "category": "stock"},
        {"symbol": "QQQ", "file": "QQQ_5m.csv", "base_price": 468.0, "dec": 2, "tv": "NASDAQ:QQQ", "name": "Nasdaq 100 ETF", "category": "stock"},

        # --- 3. FOREX MAJÖR PARİTELER (7 Varlık) ---
        {"symbol": "EUR/USD", "file": "EURUSD_5m.csv", "base_price": 1.0850, "dec": 4, "tv": "FX:EURUSD", "name": "Euro / Dolar", "category": "forex"},
        {"symbol": "GBP/USD", "file": "GBPUSD_5m.csv", "base_price": 1.3120, "dec": 4, "tv": "FX:GBPUSD", "name": "İngiliz Sterlini", "category": "forex"},
        {"symbol": "USD/JPY", "file": "USDJPY_5m.csv", "base_price": 144.50, "dec": 2, "tv": "FX:USDJPY", "name": "Dolar / Japon Yeni", "category": "forex"},
        {"symbol": "AUD/USD", "file": "AUDUSD_5m.csv", "base_price": 0.6720, "dec": 4, "tv": "FX:AUDUSD", "name": "Avustralya Doları", "category": "forex"},
        {"symbol": "USD/CAD", "file": "USDCAD_5m.csv", "base_price": 1.3540, "dec": 4, "tv": "FX:USDCAD", "name": "Dolar / Kanada Doları", "category": "forex"},
        {"symbol": "USD/CHF", "file": "USDCHF_5m.csv", "base_price": 0.8490, "dec": 4, "tv": "FX:USDCHF", "name": "Dolar / İsviçre Frangı", "category": "forex"},
        {"symbol": "NZD/USD", "file": "NZDUSD_5m.csv", "base_price": 0.6210, "dec": 4, "tv": "FX:NZDUSD", "name": "Yeni Zelanda Doları", "category": "forex"},

        # --- 4. TOP 50 KRİPTO PARA ---
        {"symbol": "BTC/USDT", "file": "BTCUSDT_5m.csv", "base_price": 64000.0, "dec": 2, "tv": "BINANCE:BTCUSDT", "name": "Bitcoin", "category": "crypto"},
        {"symbol": "ETH/USDT", "file": "ETHUSDT_5m.csv", "base_price": 2600.0, "dec": 2, "tv": "BINANCE:ETHUSDT", "name": "Ethereum", "category": "crypto"},
        {"symbol": "SOL/USDT", "file": "SOLUSDT_5m.csv", "base_price": 145.0, "dec": 2, "tv": "BINANCE:SOLUSDT", "name": "Solana", "category": "crypto"},
        {"symbol": "BNB/USDT", "file": "BNBUSDT_5m.csv", "base_price": 560.0, "dec": 2, "tv": "BINANCE:BNBUSDT", "name": "BNB", "category": "crypto"},
        {"symbol": "XRP/USDT", "file": "XRPUSDT_5m.csv", "base_price": 0.5850, "dec": 4, "tv": "BINANCE:XRPUSDT", "name": "Ripple", "category": "crypto"},
        {"symbol": "ADA/USDT", "file": "ADAUSDT_5m.csv", "base_price": 0.3650, "dec": 4, "tv": "BINANCE:ADAUSDT", "name": "Cardano", "category": "crypto"},
        {"symbol": "AVAX/USDT", "file": "AVAXUSDT_5m.csv", "base_price": 28.50, "dec": 2, "tv": "BINANCE:AVAXUSDT", "name": "Avalanche", "category": "crypto"},
        {"symbol": "DOGE/USDT", "file": "DOGEUSDT_5m.csv", "base_price": 0.1120, "dec": 4, "tv": "BINANCE:DOGEUSDT", "name": "Dogecoin", "category": "crypto"},
        {"symbol": "LINK/USDT", "file": "LINKUSDT_5m.csv", "base_price": 11.80, "dec": 2, "tv": "BINANCE:LINKUSDT", "name": "Chainlink", "category": "crypto"},
        {"symbol": "DOT/USDT", "file": "DOTUSDT_5m.csv", "base_price": 4.45, "dec": 2, "tv": "BINANCE:DOTUSDT", "name": "Polkadot", "category": "crypto"},
        {"symbol": "POL/USDT", "file": "POLUSDT_5m.csv", "base_price": 0.093, "dec": 4, "tv": "BINANCE:POLUSDT", "name": "Polygon (POL)", "category": "crypto"},
        {"symbol": "NEAR/USDT", "file": "NEARUSDT_5m.csv", "base_price": 4.85, "dec": 2, "tv": "BINANCE:NEARUSDT", "name": "Near Protocol", "category": "crypto"},
        {"symbol": "SUI/USDT", "file": "SUIUSDT_5m.csv", "base_price": 1.62, "dec": 2, "tv": "BINANCE:SUIUSDT", "name": "Sui Network", "category": "crypto"},
        {"symbol": "PEPE/USDT", "file": "PEPEUSDT_5m.csv", "base_price": 0.0000085, "dec": 7, "tv": "BINANCE:PEPEUSDT", "name": "Pepe", "category": "crypto"},
        {"symbol": "SHIB/USDT", "file": "SHIBUSDT_5m.csv", "base_price": 0.0000142, "dec": 7, "tv": "BINANCE:SHIBUSDT", "name": "Shiba Inu", "category": "crypto"},
        {"symbol": "TRX/USDT", "file": "TRXUSDT_5m.csv", "base_price": 0.1550, "dec": 4, "tv": "BINANCE:TRXUSDT", "name": "Tron", "category": "crypto"},
        {"symbol": "TON/USDT", "file": "TONUSDT_5m.csv", "base_price": 5.20, "dec": 2, "tv": "BINANCE:TONUSDT", "name": "Toncoin", "category": "crypto"},
        {"symbol": "BCH/USDT", "file": "BCHUSDT_5m.csv", "base_price": 340.0, "dec": 2, "tv": "BINANCE:BCHUSDT", "name": "Bitcoin Cash", "category": "crypto"},
        {"symbol": "LTC/USDT", "file": "LTCUSDT_5m.csv", "base_price": 68.50, "dec": 2, "tv": "BINANCE:LTCUSDT", "name": "Litecoin", "category": "crypto"},
        {"symbol": "UNI/USDT", "file": "UNIUSDT_5m.csv", "base_price": 7.40, "dec": 2, "tv": "BINANCE:UNIUSDT", "name": "Uniswap", "category": "crypto"},
        {"symbol": "APT/USDT", "file": "APTUSDT_5m.csv", "base_price": 6.80, "dec": 2, "tv": "BINANCE:APTUSDT", "name": "Aptos", "category": "crypto"},
        {"symbol": "ICP/USDT", "file": "ICPUSDT_5m.csv", "base_price": 8.50, "dec": 2, "tv": "BINANCE:ICPUSDT", "name": "Internet Computer", "category": "crypto"},
        {"symbol": "FET/USDT", "file": "FETUSDT_5m.csv", "base_price": 1.45, "dec": 2, "tv": "BINANCE:FETUSDT", "name": "Artificial Superintelligence", "category": "crypto"},
        {"symbol": "RENDER/USDT", "file": "RENDERUSDT_5m.csv", "base_price": 5.80, "dec": 2, "tv": "BINANCE:RENDERUSDT", "name": "Render", "category": "crypto"},
        {"symbol": "INJ/USDT", "file": "INJUSDT_5m.csv", "base_price": 21.50, "dec": 2, "tv": "BINANCE:INJUSDT", "name": "Injective", "category": "crypto"},
        {"symbol": "KAS/USDT", "file": "KASUSDT_5m.csv", "base_price": 0.1650, "dec": 4, "tv": "BINANCE:KASUSDT", "name": "Kaspa", "category": "crypto"},
        {"symbol": "TIA/USDT", "file": "TIAUSDT_5m.csv", "base_price": 5.10, "dec": 2, "tv": "BINANCE:TIAUSDT", "name": "Celestia", "category": "crypto"},
        {"symbol": "STX/USDT", "file": "STXUSDT_5m.csv", "base_price": 1.75, "dec": 2, "tv": "BINANCE:STXUSDT", "name": "Stacks", "category": "crypto"},
        {"symbol": "ARB/USDT", "file": "ARBUSDT_5m.csv", "base_price": 0.5850, "dec": 4, "tv": "BINANCE:ARBUSDT", "name": "Arbitrum", "category": "crypto"},
        {"symbol": "OP/USDT", "file": "OPUSDT_5m.csv", "base_price": 1.55, "dec": 2, "tv": "BINANCE:OPUSDT", "name": "Optimism", "category": "crypto"},
        {"symbol": "FIL/USDT", "file": "FILUSDT_5m.csv", "base_price": 3.85, "dec": 2, "tv": "BINANCE:FILUSDT", "name": "Filecoin", "category": "crypto"},
        {"symbol": "HBAR/USDT", "file": "HBARUSDT_5m.csv", "base_price": 0.0540, "dec": 4, "tv": "BINANCE:HBARUSDT", "name": "Hedera", "category": "crypto"},
        {"symbol": "VET/USDT", "file": "VETUSDT_5m.csv", "base_price": 0.0245, "dec": 4, "tv": "BINANCE:VETUSDT", "name": "VeChain", "category": "crypto"},
        {"symbol": "MKR/USDT", "file": "MKRUSDT_5m.csv", "base_price": 1780.0, "dec": 2, "tv": "BINANCE:MKRUSDT", "name": "Maker", "category": "crypto"},
        {"symbol": "AAVE/USDT", "file": "AAVEUSDT_5m.csv", "base_price": 148.0, "dec": 2, "tv": "BINANCE:AAVEUSDT", "name": "Aave", "category": "crypto"},
        {"symbol": "GRT/USDT", "file": "GRTUSDT_5m.csv", "base_price": 0.1620, "dec": 4, "tv": "BINANCE:GRTUSDT", "name": "The Graph", "category": "crypto"},
        {"symbol": "S/USDT", "file": "SUSDT_5m.csv", "base_price": 0.026, "dec": 4, "tv": "BINANCE:SUSDT", "name": "Sonic (S)", "category": "crypto"},
        {"symbol": "ALGO/USDT", "file": "ALGOUSDT_5m.csv", "base_price": 0.1320, "dec": 4, "tv": "BINANCE:ALGOUSDT", "name": "Algorand", "category": "crypto"},
        {"symbol": "WIF/USDT", "file": "WIFUSDT_5m.csv", "base_price": 1.75, "dec": 2, "tv": "BINANCE:WIFUSDT", "name": "dogwifhat", "category": "crypto"},
        {"symbol": "FLOKI/USDT", "file": "FLOKIUSDT_5m.csv", "base_price": 0.000145, "dec": 6, "tv": "BINANCE:FLOKIUSDT", "name": "Floki", "category": "crypto"},
        {"symbol": "BONK/USDT", "file": "BONKUSDT_5m.csv", "base_price": 0.0000195, "dec": 7, "tv": "BINANCE:BONKUSDT", "name": "Bonk", "category": "crypto"},
        {"symbol": "NOT/USDT", "file": "NOTUSDT_5m.csv", "base_price": 0.0082, "dec": 5, "tv": "BINANCE:NOTUSDT", "name": "Notcoin", "category": "crypto"},
        {"symbol": "SEI/USDT", "file": "SEIUSDT_5m.csv", "base_price": 0.3850, "dec": 4, "tv": "BINANCE:SEIUSDT", "name": "Sei", "category": "crypto"},
        {"symbol": "JUP/USDT", "file": "JUPUSDT_5m.csv", "base_price": 0.8850, "dec": 4, "tv": "BINANCE:JUPUSDT", "name": "Jupiter", "category": "crypto"},
        {"symbol": "PYTH/USDT", "file": "PYTHUSDT_5m.csv", "base_price": 0.3250, "dec": 4, "tv": "BINANCE:PYTHUSDT", "name": "Pyth Network", "category": "crypto"},
        {"symbol": "RUNE/USDT", "file": "RUNEUSDT_5m.csv", "base_price": 4.65, "dec": 2, "tv": "BINANCE:RUNEUSDT", "name": "THORChain", "category": "crypto"},
        {"symbol": "ENA/USDT", "file": "ENAUSDT_5m.csv", "base_price": 0.3150, "dec": 4, "tv": "BINANCE:ENAUSDT", "name": "Ethena", "category": "crypto"},
        {"symbol": "OM/USDT", "file": "OMUSDT_5m.csv", "base_price": 1.38, "dec": 2, "tv": "BINANCE:OMUSDT", "name": "MANTRA", "category": "crypto"},
        {"symbol": "CRV/USDT", "file": "CRVUSDT_5m.csv", "base_price": 0.2850, "dec": 4, "tv": "BINANCE:CRVUSDT", "name": "Curve DAO", "category": "crypto"},
        {"symbol": "LDO/USDT", "file": "LDOUSDT_5m.csv", "base_price": 1.15, "dec": 2, "tv": "BINANCE:LDOUSDT", "name": "Lido DAO", "category": "crypto"}
    ]

    @staticmethod
    def load_csv(filepath: str) -> pd.DataFrame:
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Veri dosyası bulunamadı: {filepath}")
        
        df = pd.read_csv(filepath)
        
        time_col = None
        for col in ['timestamp', 'datetime', 'date', 'time', 'Date', 'Datetime', 'Timestamp']:
            if col in df.columns:
                time_col = col
                break
        
        if time_col is not None:
            df['datetime'] = pd.to_datetime(df[time_col])
            df.set_index('datetime', inplace=True)
            if time_col != 'datetime' and time_col in df.columns:
                df.drop(columns=[time_col], inplace=True)
        else:
            try:
                df.index = pd.to_datetime(df.index)
            except Exception:
                raise ValueError("CSV dosyasında geçerli bir zaman kolonu veya index bulunamadı!")
                
        df.columns = [str(c).lower().strip() for c in df.columns]
        
        required_cols = ['open', 'high', 'low', 'close']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Gerekli OHLC kolonu eksik: {col}")
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        if 'volume' not in df.columns:
            df['volume'] = 1000.0
        else:
            df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(1000.0)
            
        df.dropna(subset=required_cols, inplace=True)
        df.sort_index(inplace=True)
        return df

    @classmethod
    def generate_synthetic_data(cls, symbol: str = "BTC/USDT", days: int = 60, seed: int = None) -> pd.DataFrame:
        if seed is None:
            seed = abs(hash(symbol)) % 1000000 + 42
        np.random.seed(seed)
        
        total_bars = days * 288
        end_time = pd.Timestamp.now().floor('5min')
        start_time = end_time - pd.Timedelta(minutes=5 * (total_bars - 1))
        timestamps = [start_time + pd.Timedelta(minutes=5 * i) for i in range(total_bars)]
        
        asset_info = next((a for a in cls.ASSETS if a["symbol"] == symbol), None)
        price = asset_info["base_price"] if asset_info else 100.0
        dec = asset_info["dec"] if asset_info else 2
        
        opens, highs, lows, closes, volumes = [], [], [], [], []
        
        regimes = ["range", "bull_trend", "range", "bear_trend", "volatile_range"]
        regime_len = total_bars // len(regimes)
        current_reg_idx = 0
        
        swing_high = price * 1.015
        swing_low = price * 0.985
        
        for i in range(total_bars):
            if i % regime_len == 0 and i > 0:
                current_reg_idx = min(current_reg_idx + 1, len(regimes) - 1)
            regime = regimes[current_reg_idx]
            
            if i % 48 == 0 and i > 0:
                recent_c = closes[-48:]
                swing_high = max(recent_c)
                swing_low = min(recent_c)
                
            if regime == "range":
                drift = 0.00001 * ((swing_high + swing_low) / 2 - price)
                vol = 0.0012
            elif regime == "bull_trend":
                drift = 0.00015
                vol = 0.0016
            elif regime == "bear_trend":
                drift = -0.00015
                vol = 0.0018
            else:
                drift = 0.0
                vol = 0.0025
                
            is_sweep_low = (price < swing_low * 1.002) and (np.random.rand() < 0.32)
            is_sweep_high = (price > swing_high * 0.998) and (np.random.rand() < 0.32)
            
            open_p = price
            vol_mult = 1.0
            
            if is_sweep_low:
                sweep_depth = open_p * np.random.uniform(0.0015, 0.0045)
                low_p = open_p - sweep_depth
                close_p = open_p + (open_p * np.random.uniform(0.0008, 0.003))
                high_p = max(open_p, close_p) + (open_p * np.random.uniform(0.0003, 0.001))
                vol_mult = 3.8
            elif is_sweep_high:
                sweep_height = open_p * np.random.uniform(0.0015, 0.0045)
                high_p = open_p + sweep_height
                close_p = open_p - (open_p * np.random.uniform(0.0008, 0.003))
                low_p = min(open_p, close_p) - (open_p * np.random.uniform(0.0003, 0.001))
                vol_mult = 3.8
            else:
                ret = np.random.normal(drift, vol)
                close_p = max(0.0000001, open_p * (1.0 + ret))
                u_wick = abs(np.random.normal(0, vol * 0.6))
                l_wick = abs(np.random.normal(0, vol * 0.6))
                high_p = max(open_p, close_p) * (1.0 + u_wick)
                low_p = min(open_p, close_p) * (1.0 - l_wick)
                
            base_vol = 500.0 if "BTC" in symbol or "XAU" in symbol or "TSLA" in symbol else 50000.0
            volume = max(10.0, np.random.exponential(base_vol) * vol_mult * (1 + abs(close_p - open_p) / open_p * 20))
            
            opens.append(round(open_p, dec))
            highs.append(round(high_p, dec))
            lows.append(round(low_p, dec))
            closes.append(round(close_p, dec))
            volumes.append(round(volume, 2))
            price = close_p
            
        df = pd.DataFrame({
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        }, index=pd.DatetimeIndex(timestamps, name="datetime"))
        return df

    @classmethod
    def create_default_datasets(cls, data_dir: str):
        """Top 50 Kripto, Emtia (Petrol, Altın), Hisseler (Tesla vb.) veri setlerini kaydeder."""
        os.makedirs(data_dir, exist_ok=True)
        for item in cls.ASSETS:
            fp = os.path.join(data_dir, item["file"])
            if not os.path.exists(fp):
                df = cls.generate_synthetic_data(symbol=item["symbol"], days=60)
                df.to_csv(fp)
