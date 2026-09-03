# -*- coding: utf-8 -*-
"""
Turtle Soup Pro Suite - Zero-Lag Background Worker, Multi-Asset Radar & Quant Backtest Engine
Categories (74+ Assets):
- Commodities: Gold (XAU), Silver (XAG), WTI Crude Oil (USOIL), Brent Oil (UKOIL), Natural Gas, Copper
- US Equities: Tesla (TSLA), Nvidia (NVDA), Apple (AAPL), Microsoft (MSFT), Amazon (AMZN), Google (GOOGL), Meta (META), AMD, Coinbase (COIN), S&P 500 (SPY), Nasdaq (QQQ)
- Forex: EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD, USD/CHF, NZD/USD
- Cryptocurrencies: Top 50 (BTC, ETH, SOL, BNB, XRP, DOGE, PEPE, SUI, NEAR...)
"""
import os
import sys
import time
import json
import threading
import urllib.parse
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import pandas as pd
import numpy as np

from config import StrategyConfig, BacktestConfig
from data_loader import DataLoader
from strategy import TurtleSoupStrategy
from engine import BacktestEngine
from metrics import PerformanceMetrics
from telegram_bot import TelegramNotifier

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DataLoader.create_default_datasets(DATA_DIR)

# Global Zero-Lag Scan Cache & Thread Lock
GLOBAL_SCAN_CACHE = {
    "timestamp": int(time.time()),
    "pairs": [],
    "last_updated": "Başlatılıyor..."
}
CACHE_LOCK = threading.Lock()
# Telegram Mükerrer Mesaj Koruması (Disk Kayıtlı - Asla Spam Yapmaz)
SENT_SIGNALS_FILE = os.path.join(DATA_DIR, "sent_signals_cache.json")

def load_sent_signals():
    try:
        if os.path.exists(SENT_SIGNALS_FILE):
            with open(SENT_SIGNALS_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
    except Exception:
        pass
    return set()

def save_sent_signal(key):
    SENT_TELEGRAM_SIGNALS.add(key)
    try:
        # Son 500 sinyali sakla
        items = list(SENT_TELEGRAM_SIGNALS)[-500:]
        with open(SENT_SIGNALS_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f)
    except Exception:
        pass

SENT_TELEGRAM_SIGNALS = load_sent_signals()


def scan_all_markets():
    # Saf Turtle Soup: 200 EMA filtresi canlı tarayıcıda sinyali boğmasın (Tüm likidite avlarını yakalar)
    strat_config = StrategyConfig(risk_reward_ratio=2.0, min_sweep_depth_pct=0.0004, use_trend_filter=False)
    strat = TurtleSoupStrategy(strat_config)
    results = []
    recent_feed = []

    # Canlı Binance anlık fiyat haritası
    binance_live = {}
    try:
        from live_fetcher import LiveDataFetcher
        binance_live = LiveDataFetcher.get_all_binance_live_prices()
    except Exception:
        pass

    for item in DataLoader.ASSETS:
        fp = os.path.join(DATA_DIR, item["file"])
        if not os.path.exists(fp):
            continue
        try:
            df = DataLoader.load_csv(fp)
            df_sig = strat.generate_signals(df)
            
            cur_row = df_sig.iloc[-1]
            cur_price = float(cur_row["close"])
            # Kripto ise anlık canlı Binance fiyatını al
            clean_sym = item["symbol"].replace("/", "").replace(" ", "").upper()
            if not clean_sym.endswith("USDT") and item["category"] == "crypto":
                clean_sym += "USDT"
            if clean_sym in binance_live:
                cur_price = float(binance_live[clean_sym])
            h4_high = float(cur_row["prev_4h_high"]) if not np.isnan(cur_row["prev_4h_high"]) else cur_price * 1.01
            h4_low = float(cur_row["prev_4h_low"]) if not np.isnan(cur_row["prev_4h_low"]) else cur_price * 0.99
            ema = float(cur_row["ema_200"]) if not np.isnan(cur_row["ema_200"]) else cur_price

            # Son 3 saatteki (36 bar) tüm taze likidite avlarını ve sinyalleri tara
            lookback_bars = min(36, len(df_sig))
            current_4h_slice = df_sig.iloc[-lookback_bars:]
            sig_indices = np.where(current_4h_slice["signal"].values != 0)[0]

            state = "⚪ Range İçinde"
            sig_type = ""
            sl_val = 0.0
            tp_val = 0.0
            entry_val = 0.0
            pnl_pct = 0.0
            mins_ago = -1
            is_new = False
            is_active = False
            is_tp_hit = False
            is_sl_hit = False
            is_sweep = False

            if cur_price < h4_low:
                state = "🟡 4H Low Likidite Avında (Sweep)"
                is_sweep = True
            elif cur_price > h4_high:
                state = "🟡 4H High Likidite Avında (Sweep)"
                is_sweep = True

            if len(sig_indices) > 0:
                # Get most recent signal
                last_sig_idx_rel = sig_indices[-1]
                abs_idx = len(df_sig) - lookback_bars + last_sig_idx_rel
                sig_row = df_sig.iloc[abs_idx]
                
                sig_type = "LONG" if sig_row["signal"] == 1 else "SHORT"
                entry_val = round(float(sig_row["close"]), item["dec"])
                sl_val = round(float(sig_row["sl_price"]), item["dec"])
                tp_val = round(float(sig_row["tp_price"]), item["dec"])
                bars_ago = len(df_sig) - 1 - abs_idx
                mins_ago = int(bars_ago * 5)

                # Check outcome from signal bar to current bar
                sub_bars = df_sig.iloc[abs_idx:]
                hit_tp = (sub_bars["high"] >= tp_val).any() if sig_type == "LONG" else (sub_bars["low"] <= tp_val).any()
                hit_sl = (sub_bars["low"] <= sl_val).any() if sig_type == "LONG" else (sub_bars["high"] >= sl_val).any()

                if sig_type == "LONG":
                    pnl_pct = round(((cur_price - entry_val) / entry_val) * 100.0, 2)
                else:
                    pnl_pct = round(((entry_val - cur_price) / entry_val) * 100.0, 2)

                # Kullanıcı İsteği: TP almış veya Stop olmuş eski tamamlanan işlemleri gösterme!
                if bars_ago <= 2:
                    is_new = True
                    state = f"🔥 YENİ {sig_type} RECLAIM! ({mins_ago} dk önce)"
                elif not hit_tp and not hit_sl:
                    is_active = True
                    pnl_sign = "+" if pnl_pct >= 0 else ""
                    state = f"🟢 AKTİF {sig_type} ({pnl_sign}%{pnl_pct}) - {mins_ago} dk önce" if sig_type == "LONG" else f"🔴 AKTİF {sig_type} ({pnl_sign}%{pnl_pct}) - {mins_ago} dk önce"
                else:
                    # İşlem TP veya SL ile sonuçlandı -> Tamamen elenir!
                    if cur_price < h4_low:
                        state = "🟡 4H Low Likidite Avında (Sweep)"
                    elif cur_price > h4_high:
                        state = "🟡 4H High Likidite Avında (Sweep)"
                    else:
                        state = "⚪ Range İçinde"
                    sig_type = ""
                    entry_val = 0.0
                    sl_val = 0.0
                    tp_val = 0.0

                # SADECE HALEN DEVAM EDEN AKTİF VEYA YENİ AÇILAN İŞLEMLERİ AKIŞA EKLE!
                if is_new or is_active:
                    recent_feed.append({
                        "symbol": item["symbol"],
                        "name": item["name"],
                        "file": item["file"],
                        "category": item["category"],
                        "tv": item["tv"],
                        "direction": sig_type,
                        "time": str(sig_row.name)[5:16],
                        "mins_ago": int(mins_ago),
                        "entry_price": entry_val,
                        "cur_price": round(cur_price, item["dec"]),
                        "sl": sl_val,
                        "tp": tp_val,
                        "pnl_pct": pnl_pct,
                        "status": "YENİ" if is_new else "AKTİF"
                    })

            results.append({
                "symbol": item["symbol"],
                "name": item["name"],
                "file": item["file"],
                "tv": item["tv"],
                "category": item["category"],
                "dec": item.get("dec", 2),
                "price": round(cur_price, item["dec"]),
                "h4_high": round(h4_high, item["dec"]),
                "h4_low": round(h4_low, item["dec"]),
                "state": state,
                "ema_state": "Boğa (Fiyat > EMA)" if cur_price > ema else "Ayı (Fiyat < EMA)",
                "signal_type": sig_type,
                "entry": entry_val,
                "sl": sl_val,
                "tp": tp_val,
                "pnl_pct": pnl_pct,
                "mins_ago": int(mins_ago),
                "is_new": is_new,
                "is_active": is_active,
                "is_tp_hit": is_tp_hit,
                "is_sweep": is_sweep,
                "signal_triggered": is_new or is_active
            })
        except Exception:
            continue

    # Sort recent feed by most recent
    recent_feed.sort(key=lambda x: x["mins_ago"])

    with CACHE_LOCK:
        GLOBAL_SCAN_CACHE["timestamp"] = int(time.time())
        GLOBAL_SCAN_CACHE["pairs"] = results
        GLOBAL_SCAN_CACHE["recent_feed"] = recent_feed
        GLOBAL_SCAN_CACHE["last_updated"] = datetime.now().strftime("%H:%M:%S")

def perform_initial_scan():
    scan_all_markets()

def background_market_scanner_worker():
    while True:
        try:
            # 1. Her 60 saniyede bir Binance & NASDAQ borsalarından gerçek canlı mumları indir
            try:
                from live_fetcher import LiveDataFetcher
                LiveDataFetcher.sync_all_assets_concurrent(DataLoader.ASSETS, DATA_DIR, max_workers=6)
            except Exception as fe:
                pass

            # 2. Gerçek canlı verilerle piyasayı tara
            scan_all_markets()

            # 3. Yeni sinyal oluştuğunda Telegram botuna anlık bildirim gönder
            with CACHE_LOCK:
                feed = GLOBAL_SCAN_CACHE.get("recent_feed", [])
            for item in feed:
                # Sadece taze (son 15 dk) ve daha önce HİÇ gönderilmemiş sinyalleri 1 KEZ gönder
                if item.get("mins_ago", 99) <= 15:
                    # Fiyat dalgalanmasından etkilenmeyen sabit benzersiz anahtar
                    sig_key = f"{item['symbol']}_{item['direction']}_{item['time']}"
                    if sig_key not in SENT_TELEGRAM_SIGNALS:
                        save_sent_signal(sig_key)
                        try:
                            TelegramNotifier.send_signal_alert({
                                "symbol": item["symbol"],
                                "name": item["name"],
                                "signal_type": item["direction"],
                                "price": item["entry_price"],
                                "sl": item["sl"],
                                "tp": item["tp"],
                                "h4_high": item.get("h4_high", 0),
                                "h4_low": item.get("h4_low", 0),
                                "ema_state": "Canlı Sinyal",
                                "tv": item["tv"]
                            })
                        except Exception as te:
                            print(f"[Telegram Alert Error] {te}")
        except Exception as e:
            print(f"[Worker Error] {e}")
        time.sleep(60)

worker_thread = threading.Thread(target=background_market_scanner_worker, daemon=True)
worker_thread.start()

HTML_PAGE = """<!DOCTYPE html>
<html lang="tr" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Turtle Soup Pro Suite | Emtia, Hisse, Kripto & Forex Canlı Terminali</title>
    <style>
        :root {
            --bg-main: #0b0f19;
            --bg-card: #111827;
            --bg-input: #1f2937;
            --border: #374151;
            --primary: #6366f1;
            --primary-hover: #4f46e5;
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
            --info: #06b6d4;
            --text-main: #f9fafb;
            --text-muted: #9ca3af;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        body { background-color: var(--bg-main); color: var(--text-main); min-height: 100vh; display: flex; flex-direction: column; }
        
        .header { background-color: var(--bg-card); border-bottom: 1px solid var(--border); padding: 10px 24px; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 50; }
        .logo-box { display: flex; align-items: center; gap: 10px; }
        .logo-icon { width: 36px; height: 36px; background: linear-gradient(135deg, #6366f1, #10b981); border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: bold; }
        
        .nav-tabs { display: flex; gap: 6px; background: var(--bg-input); padding: 4px; border-radius: 10px; border: 1px solid var(--border); }
        .nav-tab { border: none; background: none; color: var(--text-muted); font-size: 12px; font-weight: 700; padding: 7px 16px; border-radius: 8px; cursor: pointer; display: flex; align-items: center; gap: 6px; transition: 0.2s; }
        .nav-tab.active { background: var(--primary); color: #fff; box-shadow: 0 2px 10px rgba(99, 102, 241, 0.4); }
        
        .badge { display: inline-block; padding: 3px 8px; border-radius: 9999px; font-size: 11px; font-weight: 600; }
        .badge-indigo { background: rgba(99, 102, 241, 0.2); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.4); }
        .badge-green { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); }
        .badge-red { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }
        .badge-amber { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); }
        
        .view-section { display: none; width: 100%; max-width: 1920px; margin: 0 auto; padding: 20px; flex: 1; }
        .view-section.active { display: flex; flex-direction: column; gap: 16px; }
        
        .card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; padding: 18px; position: relative; }
        
        /* Visual Guide */
        .guide-box { background: linear-gradient(135deg, #111827 0%, #0f172a 100%); border: 1px solid #4f46e5; border-radius: 16px; padding: 18px; }
        .guide-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; margin-top: 14px; }
        .guide-card { background: #080c14; border: 1px solid var(--border); border-radius: 12px; padding: 12px; display: flex; flex-direction: column; gap: 6px; }
        .guide-title { font-size: 12px; font-weight: 800; display: flex; align-items: center; gap: 6px; }
        .guide-desc { font-size: 11px; line-height: 1.5; color: #94a3b8; }
        
        /* Filter Bar */
        .filter-bar { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; padding: 12px 18px; background: var(--bg-card); border: 1px solid var(--border); border-radius: 14px; }
        .filter-chips { display: flex; flex-wrap: wrap; gap: 6px; }
        .chip { border: 1px solid var(--border); background: var(--bg-input); color: var(--text-muted); font-size: 11px; font-weight: 600; padding: 6px 12px; border-radius: 8px; cursor: pointer; transition: 0.15s; }
        .chip:hover { color: #fff; border-color: #6366f1; }
        .chip.active { background: #6366f1; color: #fff; border-color: #6366f1; }
        
        .asset-tags { display: flex; flex-wrap: wrap; gap: 5px; max-height: 110px; overflow-y: auto; padding: 4px; }
        .asset-tag { font-size: 10px; font-weight: 600; padding: 3px 8px; border-radius: 6px; background: #080c14; border: 1px solid var(--border); color: #cbd5e1; cursor: pointer; transition: 0.15s; font-family: monospace; }
        .asset-tag.active { background: rgba(99, 102, 241, 0.3); border-color: #6366f1; color: #a5b4fc; }
        
        /* Signal Grid */
        .signal-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 14px; }
        .signal-card { background: #080c14; border: 1px solid var(--border); border-radius: 14px; padding: 14px; display: flex; flex-direction: column; gap: 8px; transition: 0.2s; position: relative; }
        .signal-card:hover { transform: translateY(-2px); border-color: #4b5563; }
        .signal-card.has-signal { border-color: #10b981; box-shadow: 0 0 15px rgba(16, 185, 129, 0.3); }
        .signal-card.has-short-signal { border-color: #ef4444; box-shadow: 0 0 15px rgba(239, 68, 68, 0.3); }
        .signal-card.in-sweep { border-color: #f59e0b; }
        
        .signal-header { display: flex; justify-content: space-between; align-items: center; }
        .signal-symbol { font-weight: 800; font-size: 14px; color: #fff; display: flex; align-items: center; gap: 6px; }
        .signal-price { font-family: monospace; font-size: 15px; font-weight: 800; color: #fff; }
        
        .signal-targets { background: var(--bg-input); border: 1px solid var(--border); border-radius: 8px; padding: 8px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; text-align: center; }
        .target-item { display: flex; flex-direction: column; }
        .target-label { font-size: 8px; text-transform: uppercase; color: var(--text-muted); }
        .target-val { font-size: 11px; font-weight: bold; font-family: monospace; }
        
        /* Backtest View */
        .backtest-layout { display: flex; flex-direction: row; gap: 20px; width: 100%; }
        @media (max-width: 1024px) { .backtest-layout { flex-direction: column; } }
        .sidebar { width: 340px; background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; padding: 18px; display: flex; flex-direction: column; gap: 14px; flex-shrink: 0; }
        @media (max-width: 1024px) { .sidebar { width: 100%; } }
        
        .form-group { display: flex; flex-direction: column; gap: 6px; }
        .form-label { font-size: 12px; color: var(--text-muted); font-weight: 500; }
        .form-control { background: var(--bg-input); border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; color: #fff; font-size: 13px; outline: none; width: 100%; }
        .form-control:focus { border-color: var(--primary); }
        
        .btn-primary { background: linear-gradient(135deg, #6366f1, #4f46e5); color: #fff; border: none; border-radius: 10px; padding: 12px; font-weight: 600; font-size: 14px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; transition: 0.2s; }
        .btn-primary:hover { opacity: 0.9; }
        .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-sm { padding: 5px 10px; font-size: 11px; border-radius: 6px; border: 1px solid var(--border); background: var(--bg-input); color: #cbd5e1; cursor: pointer; transition: 0.15s; }
        .btn-sm:hover { background: #374151; color: #fff; }
        
        .time-pills { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; background: var(--bg-input); padding: 4px; border-radius: 8px; border: 1px solid var(--border); }
        .time-pill { border: none; background: none; color: var(--text-muted); font-size: 11px; font-weight: 600; padding: 6px 0; border-radius: 6px; cursor: pointer; transition: 0.2s; }
        .time-pill.active { background: var(--primary); color: #fff; }
        
        .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 14px; }
        .kpi-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 14px; padding: 14px; display: flex; flex-direction: column; }
        .kpi-title { font-size: 11px; color: var(--text-muted); }
        .kpi-value { font-size: 19px; font-weight: 800; margin: 4px 0 2px 0; font-family: monospace; }
        .kpi-sub { font-size: 11px; color: var(--text-muted); font-family: monospace; }
        
        .table-responsive { overflow-x: auto; max-height: 300px; border-radius: 8px; }
        table { width: 100%; border-collapse: collapse; text-align: left; font-size: 12px; font-family: monospace; }
        th { background: #080c14; color: #94a3b8; padding: 10px; position: sticky; top: 0; z-index: 10; text-transform: uppercase; font-size: 10px; }
        td { padding: 8px 10px; border-bottom: 1px solid #1e293b; }
        tr.trade-row:hover { background: rgba(99, 102, 241, 0.1); cursor: pointer; }
        
        #toastContainer { position: fixed; top: 20px; right: 20px; z-index: 9999; display: flex; flex-direction: column; gap: 10px; pointer-events: none; }
        .toast { pointer-events: auto; padding: 12px 18px; border-radius: 10px; font-size: 13px; font-weight: 500; display: flex; align-items: center; gap: 10px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); transform: translateX(120%); transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
        .toast.show { transform: translateX(0); }
        .toast-success { background: #064e3b; color: #6ee7b7; border: 1px solid #059669; }
        .toast-info { background: #1e1b4b; color: #a5b4fc; border: 1px solid #4f46e5; }
        .toast-alert { background: #78350f; color: #fde68a; border: 1px solid #d97706; }
        
        .switch { position: relative; display: inline-block; width: 44px; height: 24px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #374151; transition: .3s; border-radius: 24px; }
        .slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 3px; bottom: 3px; background-color: white; transition: .3s; border-radius: 50%; }
        input:checked + .slider { background-color: #6366f1; }
        input:checked + .slider:before { transform: translateX(20px); }
    </style>
</head>
<body>

    <div id="toastContainer"></div>

    <!-- TELEGRAM SETTINGS MODAL -->
    <div id="telegramModal" style="display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 9999; display: none; align-items: center; justify-content: center; backdrop-filter: blur(4px);">
        <div style="background: #111827; border: 1px solid #0284c7; border-radius: 16px; width: 100%; max-width: 480px; padding: 22px; display: flex; flex-direction: column; gap: 14px; box-shadow: 0 10px 40px rgba(2, 132, 199, 0.3);">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1f2937; padding-bottom: 10px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 20px;">✈️</span>
                    <h3 style="font-size: 15px; font-weight: 800; color: #fff;">Telegram Sinyal Botu Entegrasyonu</h3>
                </div>
                <button onclick="closeTelegramModal()" style="background: none; border: none; color: #9ca3af; font-size: 16px; cursor: pointer;">✖</button>
            </div>

            <div style="background: #080c14; border: 1px solid #1f2937; border-radius: 10px; padding: 12px; font-size: 12px; line-height: 1.5; color: #cbd5e1;">
                <p>🤖 <b>Bot Adı:</b> <a href="https://t.me/Cry2pto_Signal_Bot" target="_blank" style="color: #38bdf8; font-weight: bold; text-decoration: underline;">@Cry2pto_Signal_Bot ↗</a></p>
                <p style="margin-top: 4px; color: #94a3b8; font-size: 11px;">
                    <b>1.</b> Telegram'da bota gidin ve <b>/start</b> yazın.<br>
                    <b>2.</b> Aşağıdaki <b>"🔍 Chat ID'mi Otomatik Bul"</b> butonuna basın.
                </p>
            </div>

            <div class="form-group">
                <label class="form-label">Telegram Chat ID</label>
                <div style="display: flex; gap: 6px;">
                    <input type="text" id="tgChatId" placeholder="Örn: 123456789" class="form-control" style="font-family: monospace;">
                    <button onclick="detectTelegramChatId()" class="btn-sm" style="background: #0284c7; color: #fff; font-weight: bold; white-space: nowrap;">
                        🔍 Otomatik Bul
                    </button>
                </div>
            </div>

            <div style="display: flex; justify-content: space-between; align-items: center; background: #1f2937; padding: 10px 14px; border-radius: 8px;">
                <div>
                    <div style="font-size: 12px; font-weight: 600;">Canlı Sinyal Gönderimi</div>
                    <div style="font-size: 10px; color: #94a3b8;">Her yeni Turtle Soup sinyalinde anında mesaj at</div>
                </div>
                <label class="switch">
                    <input type="checkbox" id="tgEnabled" checked>
                    <span class="slider"></span>
                </label>
            </div>

            <div style="display: flex; gap: 8px; margin-top: 6px;">
                <button onclick="sendTelegramTest()" class="btn-sm" style="flex: 1; padding: 10px; background: rgba(14, 165, 233, 0.2); color: #38bdf8; border-color: #0284c7; font-weight: bold;">
                    🔔 Test Mesajı Gönder
                </button>
                <button onclick="saveTelegramSettings()" class="btn-primary" style="flex: 1; padding: 10px;">
                    💾 Kaydet & Aktifleştir
                </button>
            </div>
        </div>
    </div>


    <header class="header">
        <div class="logo-box">
            <div class="logo-icon">🎯</div>
            <div>
                <h1 style="font-size: 16px; font-weight: 800;">TURTLE SOUP PRO SUITE</h1>
                <p style="font-size: 10px; color: var(--text-muted);">Emtia (Petrol/Altın), Hisseler (Tesla vb.), Kripto & Forex</p>
            </div>
        </div>

        <div class="nav-tabs">
            <button class="nav-tab active" onclick="switchView('signals', this)">
                🚨 Canlı Sinyal Terminali <span id="navSignalCountBadge" class="badge badge-green" style="font-size: 10px; padding: 1px 6px;">74 Varlık</span>
            </button>
            <button class="nav-tab" onclick="switchView('backtest', this)">
                📊 Quant Backtest Lab
            </button>
        </div>

        <div style="display: flex; align-items: center; gap: 10px;">
            <button onclick="syncRealMarketData()" class="btn-sm" style="background: rgba(16, 185, 129, 0.15); color: #34d399; border-color: #059669; font-weight: 700; display: flex; align-items: center; gap: 4px;">
                🔄 Canlı Borsa Verisi Çek (TradingView / Binance / NASDAQ)
            </button>
            <button id="soundToggleBtn" onclick="toggleSound()" class="btn-sm" style="color: #34d399; font-weight: bold;">
                🔊 Ses Açık
            </button>
            <button onclick="openTelegramModal()" class="btn-sm" style="background: rgba(14, 165, 233, 0.2); color: #38bdf8; border-color: #0284c7; font-weight: bold; display: flex; align-items: center; gap: 4px;">
                ✈️ Telegram Botu
            </button>
            <button onclick="toggleGuide()" class="btn-sm" style="background: rgba(99, 102, 241, 0.2); color: #a5b4fc; border-color: #6366f1; font-weight: bold;">
                📖 Kılavuz & Terimler
            </button>
            <div style="background: var(--bg-input); padding: 5px 10px; border-radius: 8px; border: 1px solid var(--border); display: flex; align-items: center; gap: 8px;">
                <span id="livePulse" style="width: 8px; height: 8px; background: #10b981; border-radius: 50%; display: inline-block;"></span>
                <span style="font-size: 11px; font-weight: 600; color: #34d399;">ARKA PLAN MOTORU AKTİF</span>
                <span id="countdownBadge" style="font-size: 11px; font-family: monospace; color: #818cf8; background: #0f172a; padding: 2px 6px; border-radius: 4px;">60s</span>
            </div>
            <button onclick="triggerLiveScan()" class="btn-sm" style="background: #6366f1; color: #fff; font-weight: bold;">
                🔄 Şimdi Tara
            </button>
        </div>
    </header>

    <!-- INTERFACE 1: LIVE SIGNAL TERMINAL -->
    <div id="viewSignals" class="view-section active">
        
        <!-- VISUAL GUIDE -->
        <div id="guideSection" class="guide-box">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(99, 102, 241, 0.3); padding-bottom: 8px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 18px;">📖</span>
                    <div>
                        <h2 style="font-size: 14px; font-weight: 800; color: #fff;">TURTLE SOUP STRATEJİSİ KULLANIM REHBERİ</h2>
                        <p style="font-size: 11px; color: #a5b4fc;">Likidite Avı (Sweep), Range ve Reclaim kavramları</p>
                    </div>
                </div>
                <button onclick="toggleGuide()" style="background: none; border: none; color: #94a3b8; font-size: 14px; cursor: pointer;">✖ Kapat</button>
            </div>

            <div class="guide-grid">
                <div class="guide-card">
                    <span class="guide-title" style="color: #fbbf24;">🟡 1. Likidite Avı (Sweep) Nedir?</span>
                    <p class="guide-desc">Büyük fonlar ve piyasa yapıcılar (Market Maker), yüksek hacimli pozisyon toplayabilmek için küçük yatırımcıların stop emirlerinin yığıldığı <b>4H High (Tepe)</b> veya <b>4H Low (Dip)</b> seviyelerinin dışına sahte iğneler (fakeout) atarlar.</p>
                </div>
                <div class="guide-card">
                    <span class="guide-title" style="color: #34d399;">🟢 2. Reclaim (Geri Kazanma) Nedir?</span>
                    <p class="guide-desc">Fiyat 4H seviyesini iğneledikten sonra kırılım devam etmez ve 5 dakikalık mum tekrar <b>4H seviyesinin İÇİNE kapanır</b>. Bu an avın bittiğini onaylar ve <b>tam bu kapanışta AL / SAT sinyali üretilir!</b></p>
                </div>
                <div class="guide-card">
                    <span class="guide-title" style="color: #818cf8;">⚪ 3. Range (Fiyat Aralığı) Nedir?</span>
                    <p class="guide-desc">Fiyatın <b>4H High (Tavan)</b> ve <b>4H Low (Taban)</b> arasında dalgalandığı sakin denge bölgesidir. Fiyat Range içindeyken işlem aranmaz; seviyelerin dışına taşması beklenir.</p>
                </div>
                <div class="guide-card">
                    <span class="guide-title" style="color: #c084fc;">📈 4. 200 EMA Trend Filtresi</span>
                    <p class="guide-desc">Fiyat 200 EMA'nın üstündeyse ana yön yukarıdır, sadece <b>LONG</b> aranır. Altındaysa sadece <b>SHORT</b> aranır (trend tersi işlem engellenir).</p>
                </div>
                <div class="guide-card">
                    <span class="guide-title" style="color: #f87171;">🛡️ 5. Stop Loss & Take Profit (1:2 R:R)</span>
                    <p class="guide-desc"><b>Stop Loss:</b> Sweep sırasında oluşan en uç fitil noktasına koyulur.<br><b>Take Profit:</b> Risk edilen miktarın 2 katı hedeflenir ($1:2$ Risk/Reward).</p>
                </div>
                <div class="guide-card" style="border-color: #10b981; background: rgba(16, 185, 129, 0.05);">
                    <span class="guide-title" style="color: #34d399;">⚡ 6. Sinyal Gelince 3 Adım:</span>
                    <p class="guide-desc"><b>1.</b> Radarda 🟢 <b>LONG</b> veya 🔴 <b>SHORT</b> koinini gör.<br><b>2.</b> Karttaki <b>Giriş, SL ve TP (1:2)</b> fiyatlarını borsana gir.<br><b>3.</b> Kasanın en fazla %1'ini riske et.</p>
                </div>
            </div>
        </div>

        <!-- Filter Bar -->
        <div class="filter-bar">
            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                <span style="font-size: 11px; font-weight: 700; color: #cbd5e1;">🔍 Kategori Filtreleri:</span>
                <div class="filter-chips">
                    <button class="chip active" onclick="filterSignals('all', this)">⚡ Tümü (74 Varlık)</button>
                    <button class="chip" onclick="filterSignals('triggered', this)" style="border-color: rgba(16, 185, 129, 0.4); color: #34d399;">🟢 Tetiklenen Sinyaller</button>
                    <button class="chip" onclick="filterSignals('sweep', this)" style="border-color: rgba(245, 158, 11, 0.4); color: #fbbf24;">🟡 Likidite Avında (Sweep)</button>
                    <button class="chip" onclick="filterSignals('commodity', this)">🛢️ Emtia (Petrol, Altın, Gümüş, Gaz)</button>
                    <button class="chip" onclick="filterSignals('stock', this)">📈 Hisseler (Tesla, Nvidia, Apple...)</button>
                    <button class="chip" onclick="filterSignals('crypto', this)">🪙 Top 50 Kripto</button>
                    <button class="chip" onclick="filterSignals('forex', this)">💱 Forex</button>
                </div>
            </div>
            
            <input type="text" id="coinSearchInput" placeholder="Varlık Ara (TSLA, USOIL, XAU, BTC, NVDA)..." oninput="onSearchCoin(this.value)" class="form-control" style="width: 250px; padding: 6px 10px; font-size: 12px;">
        </div>

        <!-- Quick Asset Tags (Watchlist Toggle) -->
        <div class="card" style="padding: 10px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <span style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--text-muted);">
                    📌 Güncelleme Alacak Varlıkları Seçin (İzleme Listesi / Watchlist):
                </span>
                <div style="display: flex; gap: 6px;">
                    <button onclick="toggleCategoryTags('commodity')" class="btn-sm" style="font-size: 10px;">🛢️ Emtialar</button>
                    <button onclick="toggleCategoryTags('stock')" class="btn-sm" style="font-size: 10px;">📈 Hisseler</button>
                    <button onclick="toggleCategoryTags('crypto')" class="btn-sm" style="font-size: 10px;">🪙 Kriptolar</button>
                    <button onclick="toggleCategoryTags('forex')" class="btn-sm" style="font-size: 10px;">💱 Forex</button>
                    <button onclick="selectAllCoinTags()" class="btn-sm" style="font-size: 10px; background: #6366f1; color: #fff;">Tümünü Seç/Temizle</button>
                </div>
            </div>
            <div id="coinTagsContainer" class="asset-tags"></div>
        </div>

        <!-- Signal Cards Grid -->
        <div>
        <!-- LIVE SIGNAL FEED & ACTIVE TRADES TABLE -->
        <div class="card" id="liveFeedCard" style="border-color: rgba(99, 102, 241, 0.4); padding: 14px; margin-bottom: 14px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 18px;">⚡</span>
                    <h3 style="font-size: 13px; font-weight: 800; color: #fff;">CANLI VE AKTİF İŞLEMLER (Henüz Sonuçlanmamış Pozisyonlar)</h3>
                    <span id="liveFeedBadge" class="badge badge-indigo" style="font-size: 10px;">Yükleniyor...</span>
                </div>
                <span style="font-size: 10px; color: var(--text-muted);">🕒 Yalnızca Aktif 4H Seansı (Kapanmış Eski Seanslar Gösterilmez)</span>
            </div>
            <div class="table-responsive" style="max-height: 220px;">
                <table>
                    <thead>
                        <tr>
                            <th>VARLIK</th><th>YÖN</th><th>SİNYAL ZAMANI</th><th>GİRİŞ ($)</th>
                            <th>GÜNCEL ($)</th><th>ANLIK KAR / ZARAR</th><th>DURUM</th><th>HEDEFLER</th><th>AKSİYON</th>
                        </tr>
                    </thead>
                    <tbody id="liveFeedTableBody">
                        <tr><td colspan="9" style="text-align: center; padding: 18px; color: #64748b;">Henüz aktif sinyal taranmadı.</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <h2 style="font-size: 14px; font-weight: 800; display: flex; align-items: center; gap: 8px;">
                    📡 Canlı Sinyal Masası
                    <span id="activeFilteredCount" class="badge badge-indigo">74 Varlık Taranıyor</span>
                </h2>
                <span style="font-size: 11px; color: var(--text-muted); font-family: monospace;">Arka Plan RAM Önbelleği: <span id="lastCacheUpdate" style="color: #34d399;">Canlı</span></span>
            </div>

            <div id="signalCardsContainer" class="signal-grid"></div>
        </div>

    </div>

    <!-- INTERFACE 2: QUANT BACKTEST LAB -->
    <div id="viewBacktest" class="view-section">
        <div class="backtest-layout">
            <aside class="sidebar">
                <div style="display: flex; justify-content: space-between; align-items: center; padding-bottom: 8px; border-bottom: 1px solid var(--border);">
                    <h2 style="font-size: 13px; font-weight: 700; text-transform: uppercase; color: #cbd5e1;">⚙️ Backtest Laboratuvarı</h2>
                    <span style="font-size: 11px; color: #818cf8; font-family: monospace;">74+ VARLIK</span>
                </div>

                <div class="form-group">
                    <label class="form-label">Test Edilecek Varlık (Hisse, Emtia, Kripto, FX)</label>
                    <select id="btAssetSelect" class="form-control" onchange="runBacktest()"></select>
                </div>

                <div class="form-group">
                    <label class="form-label">📅 Geriye Dönük Veri Aralığı</label>
                    <div class="time-pills">
                        <button type="button" class="time-pill" onclick="selectTimeRange('7d', this)">7 Gün</button>
                        <button type="button" class="time-pill" onclick="selectTimeRange('14d', this)">14 Gün</button>
                        <button type="button" class="time-pill" onclick="selectTimeRange('30d', this)">30 Gün</button>
                        <button type="button" class="time-pill active" onclick="selectTimeRange('60d', this)">Tümü</button>
                    </div>
                </div>

                <div class="form-group">
                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 12px;">
                        <span class="form-label">🎯 Risk / Reward Oranı (R:R)</span>
                        <span id="rrVal" style="color: #34d399; font-weight: 800; font-family: monospace; font-size: 14px; background: rgba(16, 185, 129, 0.15); padding: 2px 8px; border-radius: 6px; border: 1px solid #10b981;">1:2.0</span>
                    </div>
                    <input type="range" id="rrRatio" min="1.0" max="5.0" step="0.1" value="2.0" oninput="onRRSliderChange(this.value)" onchange="runBacktest()" style="width: 100%; accent-color: #6366f1; cursor: pointer;">
                    <div style="display: flex; gap: 4px; margin-top: 2px;">
                        <button type="button" class="btn-sm" style="flex: 1; padding: 2px 0; font-size: 10px;" onclick="setRRPreset(1.5)">1:1.5</button>
                        <button type="button" class="btn-sm" style="flex: 1; padding: 2px 0; font-size: 10px; background: #6366f1; color: #fff;" onclick="setRRPreset(2.0)">1:2.0</button>
                        <button type="button" class="btn-sm" style="flex: 1; padding: 2px 0; font-size: 10px;" onclick="setRRPreset(2.5)">1:2.5</button>
                        <button type="button" class="btn-sm" style="flex: 1; padding: 2px 0; font-size: 10px;" onclick="setRRPreset(3.0)">1:3.0</button>
                        <button type="button" class="btn-sm" style="flex: 1; padding: 2px 0; font-size: 10px;" onclick="setRRPreset(4.0)">1:4.0</button>
                    </div>
                </div>

                <div style="background: var(--bg-input); padding: 10px; border-radius: 10px; border: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <div style="font-size: 12px; font-weight: 600;">200 EMA Trend Filtresi</div>
                        <div style="font-size: 10px; color: var(--text-muted);">Sadece trend yönünde işlem</div>
                    </div>
                    <label class="switch">
                        <input type="checkbox" id="trendFilter" checked>
                        <span class="slider"></span>
                    </label>
                </div>

                <div class="form-group">
                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 12px;">
                        <span class="form-label">📏 Min. Likidite Derinliği</span>
                        <span id="sweepDepthVal" style="color: #60a5fa; font-weight: bold; font-family: monospace;">%0.15</span>
                    </div>
                    <input type="range" id="minSweepDepth" min="0.0" max="0.5" step="0.02" value="0.15" oninput="onSweepDepthChange(this.value)" onchange="runBacktest()" style="width: 100%; accent-color: #3b82f6; cursor: pointer;">
                    <span style="font-size: 9px; color: #94a3b8;">Mikro gürültü fitillerini eler, Win Rate'i yükseltir.</span>
                </div>

                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                    <div class="form-group">
                        <label class="form-label">Risk / İşlem (%)</label>
                        <input type="number" id="riskPct" value="1.0" step="0.1" class="form-control">
                    </div>
                    <div class="form-group">
                        <label class="form-label">SL Buffer (%)</label>
                        <input type="number" id="slBuffer" value="0.05" step="0.01" class="form-control">
                    </div>
                </div>

                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                    <div class="form-group">
                        <label class="form-label">Bakiye ($)</label>
                        <input type="number" id="capital" value="10000" step="1000" class="form-control">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Komisyon (%)</label>
                        <input type="number" id="commission" value="0.06" step="0.01" class="form-control">
                    </div>
                </div>

                <button id="runBtn" onclick="runBacktest()" class="btn-primary">
                    <span>⚡ Simülasyonu Çalıştır</span>
                </button>
            </aside>

            <div style="flex: 1; display: flex; flex-direction: column; gap: 16px; min-width: 0;">
                <div class="kpi-grid">
                    <div class="kpi-card">
                        <span class="kpi-title">💰 Net Kar / Zarar</span>
                        <span id="kpiNetProfit" class="kpi-value" style="color: #34d399;">+$0.00</span>
                        <span id="kpiNetProfitPct" class="kpi-sub" style="color: rgba(52, 211, 153, 0.8);">+0.00%</span>
                    </div>
                    <div class="kpi-card">
                        <span class="kpi-title">🎯 Win Rate</span>
                        <span id="kpiWinRate" class="kpi-value" style="color: #60a5fa;">0.0%</span>
                        <span id="kpiTradesCount" class="kpi-sub">0 İşlem</span>
                    </div>
                    <div class="kpi-card">
                        <span class="kpi-title">📈 Profit Factor</span>
                        <span id="kpiProfitFactor" class="kpi-value" style="color: #fbbf24;">0.00</span>
                        <span id="kpiPayoff" class="kpi-sub">Payoff: 0.00</span>
                    </div>
                    <div class="kpi-card">
                        <span class="kpi-title">🛡️ Max Drawdown</span>
                        <span id="kpiMaxDD" class="kpi-value" style="color: #f87171;">-0.00%</span>
                        <span id="kpiMaxDDVal" class="kpi-sub">-$0.00</span>
                    </div>
                    <div class="kpi-card">
                        <span class="kpi-title">⚡ Sharpe Oranı</span>
                        <span id="kpiSharpe" class="kpi-value" style="color: #c084fc;">0.00</span>
                        <span id="kpiSortino" class="kpi-sub">Sortino: 0.00</span>
                    </div>
                    <div class="kpi-card">
                        <span class="kpi-title">🏆 Expectancy</span>
                        <span id="kpiExpectancy" class="kpi-value" style="color: #22d3ee;">+0.00R</span>
                        <span id="kpiExpectancyDollar" class="kpi-sub">+$0.00 / trade</span>
                    </div>
                </div>

                <div id="chartCard" class="card">
                    <div style="display: flex; justify-content: space-between; align-items: center; padding-bottom: 8px; border-bottom: 1px solid var(--border); margin-bottom: 8px;">
                        <h3 style="font-size: 13px; font-weight: 700;">📊 5m Fiyat Mumları & 4H Seviyeleri</h3>
                        <div style="display: flex; gap: 6px;">
                            <button onclick="zoomChart(1.3)" class="btn-sm">🔍 +</button>
                            <button onclick="zoomChart(0.7)" class="btn-sm">🔍 -</button>
                            <button onclick="resetChartZoom()" class="btn-sm">↺ Sıfırla</button>
                        </div>
                    </div>
                    <div id="chartContainer" style="width: 100%; height: 380px;">
                        <canvas id="fallbackCanvas" style="width: 100%; height: 100%; display: block;"></canvas>
                    </div>
                </div>

                <div class="card" style="padding: 14px;">
                    <h3 style="font-size: 12px; font-weight: 700; margin-bottom: 6px;">📈 Bakiye Büyümesi (Equity Curve)</h3>
                    <div id="equityChartContainer" style="width: 100%; height: 150px;">
                        <canvas id="equityCanvas" style="width: 100%; height: 100%; display: block;"></canvas>
                    </div>
                </div>

                <div class="card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <h3 style="font-size: 13px; font-weight: 700;">📑 İşlem Geçmişi (Trade Log)</h3>
                        <button onclick="downloadTradeCSV()" class="btn-sm">📥 CSV İndir</button>
                    </div>
                    <div class="table-responsive">
                        <table>
                            <thead>
                                <tr>
                                    <th>ODAKLAN</th><th>ID</th><th>YÖN</th><th>GİRİŞ TARİHİ</th><th>GİRİŞ ($)</th>
                                    <th>STOP LOSS ($)</th><th>TAKE PROFIT ($)</th><th>ÇIKIŞ ($)</th><th>NEDEN</th>
                                    <th style="text-align: right;">NET KAR ($)</th><th style="text-align: right;">GETİRİ (%)</th><th style="text-align: right;">R</th>
                                </tr>
                            </thead>
                            <tbody id="tradeTableBody">
                                <tr><td colspan="12" style="text-align: center; padding: 20px; color: #64748b;">Yükleniyor...</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let ALL_ASSETS = [];

        function formatPrice(val, dec = 2) {
            if (val === undefined || val === null || isNaN(val)) return '$0.00';
            const num = Number(val);
            if (num === 0) return '$0.00';
            if (num < 0.0001) {
                return '$' + num.toFixed(dec > 4 ? dec : 7);
            }
            if (num < 1) {
                return '$' + num.toFixed(dec > 4 ? dec : 4);
            }
            if (num < 10) {
                return '$' + num.toFixed(dec > 2 ? dec : 3);
            }
            return '$' + num.toLocaleString('en-US', { minimumFractionDigits: (dec > 2 ? 2 : dec), maximumFractionDigits: (dec > 2 ? 2 : dec) });
        }

        let selectedCoinSymbols = new Set();
        let livePairsData = [];
        let activeStatusFilter = 'all';
        let searchQuery = '';
        let currentTrades = [];
        let rawResponseData = null;
        let selectedTimeRange = '60d';
        let focusedTrade = null;
        let chartSlice = { start: 0, count: 500 };
        let countdownSeconds = 60;
        let countdownInterval = null;
        // ZERO-LATENCY INSTANT RENDERING FROM INITIAL PAYLOAD
        if (window.__INIT_DATA__ && window.__INIT_DATA__.pairs && window.__INIT_DATA__.pairs.length > 0) {
            livePairsData = window.__INIT_DATA__.pairs;
            window.liveFeedData = window.__INIT_DATA__.recent_feed || [];
            ALL_ASSETS = livePairsData.map(p => ({
                symbol: p.symbol,
                name: p.name,
                file: p.file,
                tv: p.tv,
                category: p.category
            }));
            ALL_ASSETS.forEach(a => selectedCoinSymbols.add(a.symbol));
        }

        const notifiedSignalKeys = new Set();
        let soundAlertsEnabled = true;

        
        async function syncRealMarketData() {
            showToast('🌐 Binance ve NASDAQ borsalarından gerçek canlı mumlar indiriliyor...', 'info');
            try {
                const res = await fetch('/api/sync_real_market', { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    showToast('✅ ' + data.message, 'success');
                    await triggerLiveScan();
                } else {
                    showToast('Hata: ' + data.message, 'error');
                }
            } catch(e) {
                showToast('Hata: ' + e.message, 'error');
            }
        }

        function toggleSound() {
            soundAlertsEnabled = !soundAlertsEnabled;
            const btn = document.getElementById("soundToggleBtn");
            if (btn) {
                btn.innerText = soundAlertsEnabled ? "🔊 Ses Açık" : "🔇 Sessiz";
                btn.style.color = soundAlertsEnabled ? "#34d399" : "#94a3b8";
            }
            showToast(soundAlertsEnabled ? "Sesli bildirimler açıldı" : "Sesli bildirimler kapatıldı", "info");
        }

        
        
        function onSweepDepthChange(val) {
            document.getElementById('sweepDepthVal').innerText = '%' + parseFloat(val).toFixed(2);
        }

        function onRRSliderChange(val) {
            document.getElementById('rrVal').innerText = '1:' + parseFloat(val).toFixed(1);
        }

        function setRRPreset(val) {
            document.getElementById('rrRatio').value = val;
            document.getElementById('rrVal').innerText = '1:' + parseFloat(val).toFixed(1);
            runBacktest();
        }

        function toggleGuide() {
            const el = document.getElementById('guideSection');
            el.style.display = el.style.display === 'none' ? 'block' : 'none';
        }

        function switchView(viewName, el) {
            document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
            el.classList.add('active');
            document.querySelectorAll('.view-section').forEach(v => v.classList.remove('active'));
            if (viewName === 'signals') {
                document.getElementById('viewSignals').classList.add('active');
            } else {
                document.getElementById('viewBacktest').classList.add('active');
                if (!rawResponseData) runBacktest();
            }
        }

        function initAssetSelects() {
            const sel = document.getElementById('btAssetSelect');
            sel.innerHTML = ALL_ASSETS.map(a => `<option value="${a.file}">${a.symbol} (${a.name})</option>`).join('');

            const tagsCont = document.getElementById('coinTagsContainer');
            tagsCont.innerHTML = ALL_ASSETS.map(a => `<span id="tag_${a.symbol.replace(/[/]/g, '_')}" class="asset-tag active" onclick="toggleCoinTag('${a.symbol}')">${a.symbol}</span>`).join('');
        }

        function toggleCoinTag(sym) {
            const id = `tag_${sym.replace(/[/]/g, '_')}`;
            const el = document.getElementById(id);
            if (selectedCoinSymbols.has(sym)) {
                selectedCoinSymbols.delete(sym);
                if (el) el.classList.remove('active');
            } else {
                selectedCoinSymbols.add(sym);
                if (el) el.classList.add('active');
            }
            renderSignalCards();
        }

        function toggleCategoryTags(category) {
            const catAssets = ALL_ASSETS.filter(a => a.category === category);
            const allSelected = catAssets.every(a => selectedCoinSymbols.has(a.symbol));
            catAssets.forEach(a => {
                const id = `tag_${a.symbol.replace(/[/]/g, '_')}`;
                const el = document.getElementById(id);
                if (allSelected) {
                    selectedCoinSymbols.delete(a.symbol);
                    if (el) el.classList.remove('active');
                } else {
                    selectedCoinSymbols.add(a.symbol);
                    if (el) el.classList.add('active');
                }
            });
            renderSignalCards();
        }

        function selectAllCoinTags() {
            if (selectedCoinSymbols.size === ALL_ASSETS.length) {
                selectedCoinSymbols.clear();
                document.querySelectorAll('.asset-tag').forEach(t => t.classList.remove('active'));
            } else {
                ALL_ASSETS.forEach(a => selectedCoinSymbols.add(a.symbol));
                document.querySelectorAll('.asset-tag').forEach(t => t.classList.add('active'));
            }
            renderSignalCards();
        }

        
        function resetAllFilters() {
            activeStatusFilter = 'all';
            searchQuery = '';
            const searchInput = document.getElementById('coinSearchInput');
            if (searchInput) searchInput.value = '';
            
            if (ALL_ASSETS.length > 0) {
                ALL_ASSETS.forEach(a => selectedCoinSymbols.add(a.symbol));
                document.querySelectorAll('.asset-tag').forEach(t => t.classList.add('active'));
            }
            
            document.querySelectorAll('.filter-chips .chip').forEach(c => c.classList.remove('active'));
            const firstChip = document.querySelector('.filter-chips .chip');
            if (firstChip) firstChip.classList.add('active');
            
            renderSignalCards();
            showToast('Tüm filtreler sıfırlandı, 74 varlık listeleniyor.', 'info');
        }

        function filterSignals(filterType, el) {
            document.querySelectorAll('.filter-chips .chip').forEach(c => c.classList.remove('active'));
            el.classList.add('active');
            activeStatusFilter = filterType;
            renderSignalCards();
        }

        function onSearchCoin(val) {
            searchQuery = val.trim().toUpperCase();
            renderSignalCards();
        }

        function playSignalChime() {
            try {
                const ctx = new (window.AudioContext || window.webkitAudioContext)();
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'sine';
                osc.frequency.setValueAtTime(587.33, ctx.currentTime);
                osc.frequency.setValueAtTime(880, ctx.currentTime + 0.15);
                gain.gain.setValueAtTime(0.3, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.6);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start();
                osc.stop(ctx.currentTime + 0.6);
            } catch(e) {}
        }

        function showToast(msg, type = 'info') {
            const container = document.getElementById('toastContainer');
            const toast = document.createElement('div');
            toast.className = `toast toast-${type}`;
            const icon = type === 'success' ? '✅' : (type === 'error' ? '❌' : (type === 'alert' ? '🚨' : 'ℹ️'));
            toast.innerHTML = `<span>${icon}</span> <span>${msg}</span>`;
            container.appendChild(toast);
            setTimeout(() => toast.classList.add('show'), 10);
            setTimeout(() => {
                toast.classList.remove('show');
                setTimeout(() => toast.remove(), 300);
            }, 4500);
        }

        function initLiveScanner() {
            startCountdown();
            triggerLiveScan();
        }

        function startCountdown() {
            clearInterval(countdownInterval);
            countdownSeconds = 60;
            updateCountdownDisplay();
            countdownInterval = setInterval(() => {
                countdownSeconds--;
                if (countdownSeconds <= 0) {
                    countdownSeconds = 60;
                    triggerLiveScan();
                }
                updateCountdownDisplay();
            }, 1000);
        }

        function updateCountdownDisplay() {
            document.getElementById('countdownBadge').innerText = `${countdownSeconds}s`;
        }

        async function triggerLiveScan() {
            try {
                const res = await fetch('/api/live_scan');
                if (!res.ok) throw new Error('Live scan API failed');
                const data = await res.json();
                livePairsData = data.pairs || [];
                window.liveFeedData = data.recent_feed || [];
                
                if (data.last_updated) {
                    document.getElementById('lastCacheUpdate').innerText = data.last_updated;
                }
                renderLiveFeed();

                if (ALL_ASSETS.length === 0 && livePairsData.length > 0) {
                    ALL_ASSETS = livePairsData.map(p => ({
                        symbol: p.symbol,
                        name: p.name,
                        file: p.file,
                        tv: p.tv,
                        category: p.category
                    }));
                    ALL_ASSETS.forEach(a => selectedCoinSymbols.add(a.symbol));
                    initAssetSelects();
                } else if (selectedCoinSymbols.size === 0 && ALL_ASSETS.length > 0) {
                    ALL_ASSETS.forEach(a => selectedCoinSymbols.add(a.symbol));
                }

                renderSignalCards();

                livePairsData.forEach(p => {
                    // Sadece YENİ (son 10 dk) ve daha önce bildirilmemiş sinyalleri 1 kez bildir
                    if (p.is_new && selectedCoinSymbols.has(p.symbol)) {
                        const sigKey = `${p.symbol}_${p.signal_type}_${p.entry}_${p.mins_ago}`;
                        if (!notifiedSignalKeys.has(sigKey)) {
                            notifiedSignalKeys.add(sigKey);
                            if (soundAlertsEnabled) {
                                playSignalChime();
                            }
                            showToast(`🚨 YENİ SİNYAL: ${p.symbol} ${p.signal_type}! Giriş: $${p.entry} (SL: $${p.sl} - TP: $${p.tp})`, 'alert');
                        }
                    }
                });
            } catch(e) {
                console.error('Live scan error:', e);
            }
        }

        
        function renderLiveFeed() {
            const feed = window.liveFeedData || [];
            const badge = document.getElementById('liveFeedBadge');
            const tbody = document.getElementById('liveFeedTableBody');

            const activeCount = feed.filter(f => f.status === 'AKTİF' || f.status === 'YENİ').length;
            if (badge) badge.innerText = `${feed.length} Sinyal (${activeCount} Aktif Pozisyon)`;

            if (feed.length === 0) {
                tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 20px; color: #64748b;">Şu anda piyasada açık aktif işlem bulunmuyor (Eski TP/SL olmuş işlemler filtrelendi). Yeni bir Reclaim sinyali oluştuğunda burada canlı listelenecektir.</td></tr>`;
                return;
            }

            tbody.innerHTML = feed.map(f => {
                const isLong = f.direction === 'LONG';
                const pnlPositive = f.pnl_pct >= 0;
                let statusBadge = '';
                if (f.status === 'YENİ') statusBadge = '<span class="badge badge-green" style="animation: pulse 1.5s infinite;">🔥 YENİ GİRİŞ</span>';
                else if (f.status === 'AKTİF') statusBadge = `<span class="badge ${isLong ? 'badge-green' : 'badge-red'}">🟢 AKTİF İŞLEM</span>`;
                else if (f.status === 'TP_HIT') statusBadge = '<span class="badge badge-green">✅ TP VURULDU</span>';
                else statusBadge = '<span class="badge badge-red">🛑 STOP OLDU</span>';

                const tvUrl = `https://www.tradingview.com/chart/?symbol=${f.tv || 'BINANCE:BTCUSDT'}&interval=5`;

                return `<tr>
                    <td style="font-weight: 800; color: #fff;">${f.symbol} <span style="font-size: 10px; color: #94a3b8; font-weight: normal;">(${f.name})</span></td>
                    <td><span class="badge ${isLong ? 'badge-green' : 'badge-red'}">${f.direction}</span></td>
                    <td style="color: #cbd5e1;">${f.mins_ago === 0 ? 'Tam Şimdi' : f.mins_ago + ' dk önce'} (${f.time})</td>
                    <td style="font-weight: 600; color: #fff;">$${formatPrice(f.entry_price, f.dec).replace("$", "")}</td>
                    <td style="font-weight: 600; color: #818cf8;">$${formatPrice(f.cur_price, f.dec).replace("$", "")}</td>
                    <td style="font-weight: 800; color: ${pnlPositive ? '#34d399' : '#f87171'};">${pnlPositive ? '+' : ''}${f.pnl_pct.toFixed(2)}%</td>
                    <td>${statusBadge}</td>
                    <td style="font-size: 10px; color: #94a3b8;">SL: ${formatPrice(f.sl, f.dec)} | TP: ${formatPrice(f.tp, f.dec)}</td>
                    <td>
                        <div style="display: flex; gap: 4px;">
                            <button onclick="goToBacktestForAsset('${f.file || (f.symbol.replace('/', '') + '_5m.csv')}')" class="btn-sm" style="font-size: 10px;">📊 Test Et</button>
                            <a href="${tvUrl}" target="_blank" class="btn-sm" style="text-decoration: none; font-size: 10px; color: #60a5fa;">TV ↗</a>
                        </div>
                    </td>
                </tr>`;
            }).join('');
        }

        function renderSignalCards() {
            const container = document.getElementById('signalCardsContainer');
            let filtered = livePairsData.filter(p => {
                // Arama filtresi
                if (searchQuery && !p.symbol.includes(searchQuery) && !p.name.toUpperCase().includes(searchQuery)) return false;

                // Durum ve Kategori filtreleri
                if (activeStatusFilter === 'triggered') {
                    return p.signal_triggered || p.is_new || p.is_active || p.is_tp_hit || p.is_sl_hit || p.is_sweep || p.state.includes('RECLAIM');
                }
                if (activeStatusFilter === 'sweep') {
                    return p.is_sweep || p.state.includes('Sweep');
                }
                if (activeStatusFilter === 'commodity') {
                    return p.category === 'commodity';
                }
                if (activeStatusFilter === 'stock') {
                    return p.category === 'stock';
                }
                if (activeStatusFilter === 'crypto') {
                    return p.category === 'crypto';
                }
                if (activeStatusFilter === 'forex') {
                    return p.category === 'forex';
                }

                // Yalnızca kullanıcı özel olarak etiket elediğinde izleme listesini uygula
                if (selectedCoinSymbols.size > 0 && selectedCoinSymbols.size < ALL_ASSETS.length) {
                    if (!selectedCoinSymbols.has(p.symbol)) return false;
                }

                return true;
            });

            document.getElementById('activeFilteredCount').innerText = `${filtered.length} Varlık Listeleniyor`;

            if (filtered.length === 0) {
                container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 36px 20px; color: #94a3b8; background: #080c14; border-radius: 14px; border: 1px dashed rgba(99, 102, 241, 0.4); display: flex; flex-direction: column; align-items: center; gap: 12px;">
                    <p style="font-size: 14px; font-weight: 600; color: #cbd5e1;">Seçilen filtre kriterlerine uygun varlık bulunamadı.</p>
                    <p style="font-size: 11px; color: #64748b;">Mevcut seanstaki tüm varlıkları görmek için filtreleri sıfırlayabilirsiniz.</p>
                    <button onclick="resetAllFilters()" class="btn-primary" style="padding: 8px 18px; font-size: 12px;">
                        ↺ Tüm Filtreleri Sıfırla (74 Varlığı Göster)
                    </button>
                </div>`;
                return;
            }

            container.innerHTML = filtered.map(p => {
                const isNewSig = p.is_new;
                const isActiveSig = p.is_active;
                const isSig = isNewSig || isActiveSig;
                const isLongSig = p.signal_type === 'LONG';
                let cardClass = '';
                if (isNewSig) cardClass = isLongSig ? 'has-signal' : 'has-short-signal';
                else if (isActiveSig) cardClass = isLongSig ? 'has-signal' : 'has-short-signal';
                else if (p.is_sweep || p.state.includes('Sweep')) cardClass = 'in-sweep';

                const tvUrl = `https://www.tradingview.com/chart/?symbol=${p.tv || 'BINANCE:BTCUSDT'}&interval=5`;

                return `<div class="signal-card ${cardClass}">
                    <div class="signal-header">
                        <div class="signal-symbol">
                            <span>${p.symbol}</span>
                            <span style="font-size: 10px; color: #94a3b8; font-weight: normal;">(${p.name})</span>
                            ${isSig ? `<span class="badge ${isLongSig ? 'badge-green' : 'badge-red'}" style="font-size: 9px; font-weight: 800;">🔥 ${p.signal_type}</span>` : ''}
                        </div>
                        <span class="signal-price">${formatPrice(p.price, p.dec)}</span>
                    </div>

                    <div style="display: flex; justify-content: space-between; font-size: 10px; font-family: monospace; color: #94a3b8;">
                        <span style="color: #f87171;">4H High: ${formatPrice(p.h4_high, p.dec)}</span>
                        <span style="color: #34d399;">4H Low: ${formatPrice(p.h4_low, p.dec)}</span>
                    </div>

                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span class="badge ${p.state.includes('RECLAIM') ? (isLongSig?'badge-green':'badge-red') : (p.state.includes('Sweep')?'badge-amber':'badge-indigo')}">${p.state}</span>
                        <span style="font-size: 10px; color: #64748b; font-family: monospace;">200 EMA: ${p.ema_state || 'Nötr'}</span>
                    </div>

                    <div class="signal-targets">
                        <div class="target-item">
                            <span class="target-label">GİRİŞ (SEVİYE)</span>
                            <span class="target-val" style="color: #818cf8;">${p.entry > 0 ? formatPrice(p.entry, p.dec) : (p.state.includes('Sweep') ? '🟡 Reclaim Bekleniyor' : formatPrice(p.price, p.dec))}</span>
                        </div>
                        <div class="target-item">
                            <span class="target-label">STOP LOSS</span>
                            <span class="target-val" style="color: #f87171;">${p.sl > 0 ? formatPrice(p.sl, p.dec) : '4H Fitil Seviyesi'}</span>
                        </div>
                        <div class="target-item">
                            <span class="target-label">TAKE PROFIT (1:2)</span>
                            <span class="target-val" style="color: #34d399;">${p.tp > 0 ? formatPrice(p.tp, p.dec) : '1:2 R:R Hedefi'}</span>
                        </div>
                    </div>

                    <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-top: 2px;">
                        <button onclick="goToBacktestForAsset('${p.file}')" class="btn-sm" style="flex: 1; text-align: center; background: rgba(99, 102, 241, 0.2); color: #a5b4fc; border-color: rgba(99, 102, 241, 0.4);">
                            📊 Grafikte İncele
                        </button>
                        <a href="${tvUrl}" target="_blank" class="btn-sm" style="text-decoration: none; display: flex; align-items: center; gap: 4px; color: #60a5fa; border-color: rgba(96, 165, 250, 0.4);">
                            🌐 TV ↗
                        </a>
                    </div>
                </div>`;
            }).join('');
        }

        function goToBacktestForAsset(file) {
            const selectEl = document.getElementById('btAssetSelect');
            if (selectEl) {
                let found = false;
                for (let i = 0; i < selectEl.options.length; i++) {
                    if (selectEl.options[i].value === file) {
                        selectEl.selectedIndex = i;
                        found = true;
                        break;
                    }
                }
                if (!found && selectEl.options.length > 0) {
                    selectEl.selectedIndex = 0;
                }
            }
            switchView('backtest', document.querySelectorAll('.nav-tab')[1]);
            runBacktest();
        }

        // BACKTEST LAB
        function selectTimeRange(range, el) {
            document.querySelectorAll('.time-pills .time-pill').forEach(b => b.classList.remove('active'));
            el.classList.add('active');
            selectedTimeRange = range;
            runBacktest();
        }

        async function runBacktest() {
            const btn = document.getElementById('runBtn');
            btn.disabled = true;
            const asset = document.getElementById('btAssetSelect').value;
            const payload = {
                filename: asset,
                time_range: selectedTimeRange,
                risk_reward_ratio: parseFloat(document.getElementById('rrRatio').value),
                use_trend_filter: document.getElementById('trendFilter').checked,
                risk_per_trade_pct: parseFloat(document.getElementById('riskPct').value),
                sl_buffer_pct: parseFloat(document.getElementById('slBuffer').value) / 100.0,
                min_sweep_depth_pct: (parseFloat(document.getElementById('minSweepDepth') ? document.getElementById('minSweepDepth').value : 0.15) / 100.0),
                initial_capital: parseFloat(document.getElementById('capital').value),
                commission_rate: parseFloat(document.getElementById('commission').value) / 100.0
            };

            try {
                const response = await fetch('/api/backtest', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (!response.ok) throw new Error('Backtest API error');
                const data = await response.json();
                rawResponseData = data;
                updateBacktestUI(data);
            } catch(e) {
                console.error(e);
                showToast('Backtest hatası: ' + e.message, 'error');
            } finally {
                btn.disabled = false;
            }
        }

        function updateBacktestUI(res) {
            const m = res.metrics;
            currentTrades = res.trades;

            const profitEl = document.getElementById('kpiNetProfit');
            profitEl.innerText = (m.net_profit_dollar >= 0 ? '+$' : '-$') + Math.abs(m.net_profit_dollar).toLocaleString();
            profitEl.style.color = m.net_profit_dollar >= 0 ? '#34d399' : '#f87171';

            const profitPctEl = document.getElementById('kpiNetProfitPct');
            profitPctEl.innerText = (m.net_profit_pct >= 0 ? '+' : '') + m.net_profit_pct.toFixed(2) + '%';

            document.getElementById('kpiWinRate').innerText = m.win_rate_pct.toFixed(1) + '%';
            document.getElementById('kpiTradesCount').innerText = `${m.total_trades} İşlem (${m.winning_trades}W / ${m.losing_trades}L)`;
            document.getElementById('kpiProfitFactor').innerText = m.profit_factor.toFixed(2);
            document.getElementById('kpiPayoff').innerText = `Payoff: ${m.payoff_ratio.toFixed(2)}`;
            document.getElementById('kpiMaxDD').innerText = '-' + m.max_drawdown_pct.toFixed(2) + '%';
            document.getElementById('kpiMaxDDVal').innerText = '-$' + m.max_drawdown_dollar.toLocaleString();
            document.getElementById('kpiSharpe').innerText = m.sharpe_ratio.toFixed(2);
            document.getElementById('kpiSortino').innerText = `Sortino: ${m.sortino_ratio.toFixed(2)}`;
            document.getElementById('kpiExpectancy').innerText = (m.expectancy_r >= 0 ? '+' : '') + m.expectancy_r.toFixed(2) + 'R';
            document.getElementById('kpiExpectancyDollar').innerText = (m.expectancy_dollar >= 0 ? '+$' : '-$') + Math.abs(m.expectancy_dollar) + ' / trade';

            renderCanvasCharts();

            const tbody = document.getElementById('tradeTableBody');
            if (res.trades.length === 0) {
                tbody.innerHTML = `<tr><td colspan="12" style="text-align: center; padding: 24px; color: #64748b;">Seçilen kriterlerde işlem bulunamadı.</td></tr>`;
                return;
            }

            tbody.innerHTML = res.trades.map(t => {
                const isWin = t.pnl_net > 0;
                const isLong = t.direction === 'LONG';
                return `<tr id="tradeRow_${t.trade_id}" class="trade-row" onclick="focusOnTrade(${t.trade_id})">
                    <td><button class="btn-sm" style="color: #a5b4fc; border-color: #6366f1;" onclick="event.stopPropagation(); focusOnTrade(${t.trade_id})">🔍 Odaklan</button></td>
                    <td style="color: #94a3b8; font-weight: bold;">#${t.trade_id}</td>
                    <td><span class="badge ${isLong ? 'badge-green' : 'badge-red'}">${t.direction}</span></td>
                    <td style="color: #cbd5e1;">${t.entry_time.slice(0, 16)}</td>
                    <td style="font-weight: 600; color: #fff;">$${t.entry_price.toLocaleString()}</td>
                    <td style="color: #f87171;">$${t.stop_loss.toLocaleString()}</td>
                    <td style="color: #34d399;">$${t.take_profit.toLocaleString()}</td>
                    <td style="color: #e2e8f0;">$${t.exit_price.toLocaleString()}</td>
                    <td><span style="font-size: 10px; padding: 2px 6px; border-radius: 4px; background: ${t.exit_reason === 'TAKE_PROFIT' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)'}; color: ${t.exit_reason === 'TAKE_PROFIT' ? '#34d399' : '#f87171'};">${t.exit_reason}</span></td>
                    <td style="text-align: right; font-weight: bold; color: ${isWin ? '#34d399' : '#f87171'};">${isWin ? '+' : ''}$${t.pnl_net.toFixed(2)}</td>
                    <td style="text-align: right; color: ${isWin ? '#34d399' : '#f87171'};">${isWin ? '+' : ''}${t.return_pct.toFixed(2)}%</td>
                    <td style="text-align: right; font-weight: bold; color: ${isWin ? '#34d399' : '#f87171'};">${t.r_multiple > 0 ? '+' : ''}${t.r_multiple.toFixed(2)}R</td>
                </tr>`;
            }).join('');
        }

        function focusOnTrade(tradeId) {
            const trade = currentTrades.find(t => t.trade_id === tradeId);
            if (!trade || !rawResponseData) return;
            focusedTrade = trade;

            const candles = rawResponseData.chart_candles || [];
            const entryTs = Math.floor(new Date(trade.entry_time).getTime() / 1000);
            let targetIdx = candles.findIndex(c => Math.abs(c.time - entryTs) <= 300);
            if (targetIdx === -1) targetIdx = candles.length - 1;

            const count = 120;
            const start = Math.max(0, targetIdx - 40);
            chartSlice = { start: start, count: Math.min(count, candles.length - start) };
            renderCanvasCharts();
            document.getElementById('chartCard').scrollIntoView({ behavior: 'smooth', block: 'center' });
            showToast(`#${trade.trade_id} ${trade.direction} işlemine odaklanıldı.`, 'info');
        }

        function zoomChart(factor) {
            if (!rawResponseData) return;
            const candles = rawResponseData.chart_candles || [];
            let newCount = Math.round(chartSlice.count / factor);
            chartSlice.count = Math.max(30, Math.min(candles.length, newCount));
            renderCanvasCharts();
        }

        function resetChartZoom() {
            if (!rawResponseData) return;
            const candles = rawResponseData.chart_candles || [];
            chartSlice = { start: Math.max(0, candles.length - 400), count: Math.min(400, candles.length) };
        }

        function renderCanvasCharts() {
            if (!rawResponseData) return;
            const data = rawResponseData;

            const canvas = document.getElementById('fallbackCanvas');
            const container = document.getElementById('chartContainer');
            canvas.width = container.clientWidth * window.devicePixelRatio;
            canvas.height = container.clientHeight * window.devicePixelRatio;
            const ctx = canvas.getContext('2d');
            ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
            
            const w = container.clientWidth;
            const h = container.clientHeight;
            ctx.fillStyle = '#080c14';
            ctx.fillRect(0, 0, w, h);

            const allCandles = data.chart_candles || [];
            if (allCandles.length === 0) return;

            const start = Math.max(0, chartSlice.start);
            const count = Math.min(chartSlice.count, allCandles.length - start);
            const visibleCandles = allCandles.slice(start, start + count);

            let minP = Infinity, maxP = -Infinity;
            visibleCandles.forEach(c => {
                if (c.low < minP) minP = c.low;
                if (c.high > maxP) maxP = c.high;
            });

            if (focusedTrade) {
                if (focusedTrade.stop_loss < minP) minP = focusedTrade.stop_loss;
                if (focusedTrade.take_profit > maxP) maxP = focusedTrade.take_profit;
            }

            const pad = (maxP - minP) * 0.08 || 10;
            minP -= pad; maxP += pad;
            const priceRange = maxP - minP;
            const getY = p => h - 30 - ((p - minP) / priceRange) * (h - 55);

            ctx.strokeStyle = '#1e293b';
            ctx.lineWidth = 1;
            for (let i = 1; i <= 4; i++) {
                const y = (h / 5) * i;
                ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w - 65, y); ctx.stroke();
                const pVal = maxP - (i / 5) * priceRange;
                ctx.fillStyle = '#64748b';
                ctx.font = '10px monospace';
                ctx.fillText(pVal.toFixed(1), w - 60, y + 3);
            }

            const barW = Math.max(2, (w - 75) / visibleCandles.length);

            if (data.chart_ema && data.chart_ema.length > 0) {
                const emaSlice = data.chart_ema.slice(start, start + count);
                ctx.strokeStyle = '#fbbf24'; ctx.lineWidth = 1.5; ctx.beginPath();
                emaSlice.forEach((pt, i) => {
                    const x = i * barW + barW / 2;
                    const y = getY(pt.value);
                    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
                });
                ctx.stroke();
            }

            if (data.chart_h4_high && data.chart_h4_high.length > 0) {
                const highSlice = data.chart_h4_high.slice(start, start + count);
                ctx.strokeStyle = '#f87171'; ctx.lineWidth = 1.2; ctx.setLineDash([4, 4]); ctx.beginPath();
                highSlice.forEach((pt, i) => {
                    const x = i * barW + barW / 2;
                    const y = getY(pt.value);
                    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
                });
                ctx.stroke(); ctx.setLineDash([]);
            }

            if (data.chart_h4_low && data.chart_h4_low.length > 0) {
                const lowSlice = data.chart_h4_low.slice(start, start + count);
                ctx.strokeStyle = '#34d399'; ctx.lineWidth = 1.2; ctx.setLineDash([4, 4]); ctx.beginPath();
                lowSlice.forEach((pt, i) => {
                    const x = i * barW + barW / 2;
                    const y = getY(pt.value);
                    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
                });
                ctx.stroke(); ctx.setLineDash([]);
            }

            let focusedCandleX = null;
            visibleCandles.forEach((c, i) => {
                const x = i * barW;
                const isUp = c.close >= c.open;
                const color = isUp ? '#10b981' : '#ef4444';

                if (focusedTrade) {
                    const entryTs = Math.floor(new Date(focusedTrade.entry_time).getTime() / 1000);
                    if (Math.abs(c.time - entryTs) <= 300) {
                        focusedCandleX = x + barW / 2;
                        ctx.fillStyle = 'rgba(99, 102, 241, 0.25)';
                        ctx.fillRect(x - 4, 0, barW + 8, h);
                    }
                }

                ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.beginPath();
                ctx.moveTo(x + barW / 2, getY(c.high)); ctx.lineTo(x + barW / 2, getY(c.low)); ctx.stroke();
                ctx.fillStyle = color;
                ctx.fillRect(x + 0.5, Math.min(getY(c.open), getY(c.close)), Math.max(1, barW - 1), Math.max(1, Math.abs(getY(c.open) - getY(c.close))));

                if (i % 25 === 0) {
                    const dt = new Date(c.time * 1000);
                    ctx.fillStyle = '#64748b'; ctx.font = '9px monospace';
                    ctx.fillText(`${dt.getMonth()+1}/${dt.getDate()} ${dt.getHours()}:${dt.getMinutes()<10?'0':''}${dt.getMinutes()}`, x, h - 8);
                }
            });

            if (focusedTrade && focusedCandleX !== null) {
                const entryY = getY(focusedTrade.entry_price);
                const slY = getY(focusedTrade.stop_loss);
                const tpY = getY(focusedTrade.take_profit);

                ctx.strokeStyle = '#10b981'; ctx.lineWidth = 1.5; ctx.setLineDash([5, 3]);
                ctx.beginPath(); ctx.moveTo(focusedCandleX, tpY); ctx.lineTo(w - 70, tpY); ctx.stroke();
                ctx.fillStyle = '#10b981'; ctx.font = 'bold 10px monospace'; ctx.fillText(`TP: $${focusedTrade.take_profit}`, w - 65, tpY + 3);

                ctx.strokeStyle = '#ef4444'; ctx.lineWidth = 1.5; ctx.setLineDash([5, 3]);
                ctx.beginPath(); ctx.moveTo(focusedCandleX, slY); ctx.lineTo(w - 70, slY); ctx.stroke();
                ctx.fillStyle = '#ef4444'; ctx.font = 'bold 10px monospace'; ctx.fillText(`SL: $${focusedTrade.stop_loss}`, w - 65, slY + 3);

                ctx.strokeStyle = '#818cf8'; ctx.lineWidth = 1.5; ctx.setLineDash([]);
                ctx.beginPath(); ctx.moveTo(focusedCandleX, entryY); ctx.lineTo(w - 70, entryY); ctx.stroke();
                ctx.fillStyle = '#818cf8'; ctx.font = 'bold 10px monospace'; ctx.fillText(`GİRİŞ: $${focusedTrade.entry_price}`, w - 65, entryY + 3);
            }

            // Equity Canvas
            const eqCanvas = document.getElementById('equityCanvas');
            const eqContainer = document.getElementById('equityChartContainer');
            eqCanvas.width = eqContainer.clientWidth * window.devicePixelRatio;
            eqCanvas.height = eqContainer.clientHeight * window.devicePixelRatio;
            const eqCtx = eqCanvas.getContext('2d');
            eqCtx.scale(window.devicePixelRatio, window.devicePixelRatio);
            const eqW = eqContainer.clientWidth;
            const eqH = eqContainer.clientHeight;
            eqCtx.fillStyle = '#080c14';
            eqCtx.fillRect(0, 0, eqW, eqH);

            const eqData = data.chart_equity || [];
            if (eqData.length === 0) return;

            let minEq = Infinity, maxEq = -Infinity;
            eqData.forEach(d => {
                if (d.value < minEq) minEq = d.value;
                if (d.value > maxEq) maxEq = d.value;
            });
            const eqPad = (maxEq - minEq) * 0.1 || 100;
            minEq -= eqPad; maxEq += eqPad;
            const eqRange = maxEq - minEq;
            const getEqY = v => eqH - 20 - ((v - minEq) / eqRange) * (eqH - 35);

            const eqStep = (eqW - 60) / eqData.length;
            eqCtx.beginPath(); eqCtx.moveTo(0, eqH);
            eqData.forEach((d, i) => eqCtx.lineTo(i * eqStep, getEqY(d.value)));
            eqCtx.lineTo((eqData.length - 1) * eqStep, eqH); eqCtx.closePath();
            const grad = eqCtx.createLinearGradient(0, 0, 0, eqH);
            grad.addColorStop(0, 'rgba(99, 102, 241, 0.4)');
            grad.addColorStop(1, 'rgba(99, 102, 241, 0.0)');
            eqCtx.fillStyle = grad; eqCtx.fill();

            eqCtx.beginPath(); eqCtx.strokeStyle = '#818cf8'; eqCtx.lineWidth = 2;
            eqData.forEach((d, i) => {
                const x = i * eqStep;
                const y = getEqY(d.value);
                if (i === 0) eqCtx.moveTo(x, y); else eqCtx.lineTo(x, y);
            });
            eqCtx.stroke();
        }

        function downloadTradeCSV() {
            if (!currentTrades || currentTrades.length === 0) {
                showToast('İndirilecek işlem bulunamadı', 'error');
                return;
            }
            const headers = Object.keys(currentTrades[0]).join(',');
            const rows = currentTrades.map(t => Object.values(t).join(',')).join('\\n');
            const csvContent = 'data:text/csv;charset=utf-8,' + headers + '\\n' + rows;
            const link = document.createElement('a');
            link.setAttribute('href', encodeURI(csvContent));
            link.setAttribute('download', 'turtle_soup_trade_ledger.csv');
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            showToast('Trade log CSV olarak indirildi.', 'success');
        }

        window.addEventListener('resize', () => {
            if (rawResponseData) renderCanvasCharts();
        });

        
        // TELEGRAM MODAL & API FUNCTIONS
        function openTelegramModal() {
            document.getElementById('telegramModal').style.display = 'flex';
            loadTelegramStatus();
        }

        function closeTelegramModal() {
            document.getElementById('telegramModal').style.display = 'none';
        }

        async function loadTelegramStatus() {
            try {
                const res = await fetch('/api/telegram_status');
                const data = await res.json();
                if (data.chat_id) document.getElementById('tgChatId').value = data.chat_id;
                document.getElementById('tgEnabled').checked = !!data.enabled;
            } catch(e) {}
        }

        async function detectTelegramChatId() {
            showToast('Telegram güncellemeleri taranıyor...', 'info');
            try {
                const res = await fetch('/api/telegram_detect');
                const data = await res.json();
                if (data.success && data.chat_id) {
                    document.getElementById('tgChatId').value = data.chat_id;
                    showToast(data.message, 'success');
                } else {
                    showToast(data.message, 'error');
                }
            } catch(e) {
                showToast('Hata: ' + e.message, 'error');
            }
        }

        async function saveTelegramSettings() {
            const chatId = document.getElementById('tgChatId').value.trim();
            const enabled = document.getElementById('tgEnabled').checked;

            try {
                const res = await fetch('/api/telegram_save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ chat_id: chatId, enabled: enabled })
                });
                const data = await res.json();
                if (data.success) {
                    showToast('Telegram ayarları kaydedildi!', 'success');
                    closeTelegramModal();
                } else {
                    showToast('Hata: ' + data.message, 'error');
                }
            } catch(e) {
                showToast('Hata: ' + e.message, 'error');
            }
        }

        async function sendTelegramTest() {
            const chatId = document.getElementById('tgChatId').value.trim();
            if (!chatId) {
                showToast('Lütfen önce Chat ID girin veya otomatik bulun!', 'error');
                return;
            }
            showToast('Test mesajı iletiliyor...', 'info');
            try {
                const res = await fetch('/api/telegram_test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ chat_id: chatId })
                });
                const data = await res.json();
                if (data.success) {
                    showToast('✅ Test mesajı Telegram botunuza başarıyla iletildi!', 'success');
                } else {
                    showToast('❌ Mesaj iletilemedi: ' + data.message, 'error');
                }
            } catch(e) {
                showToast('Hata: ' + e.message, 'error');
            }
        }

        window.onload = () => {
            if (ALL_ASSETS.length > 0) {
                initAssetSelects();
                renderLiveFeed();
                renderSignalCards();
            }
            initLiveScanner();
        };
    </script>
</body>
</html>
"""

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        elif isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)

class RobustThreadingServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        exc_type, exc_val, exc_tb = sys.exc_info()
        if exc_type in (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            return
        super().handle_error(request, client_address)

class BacktestRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        msg = format % args
        if "404" not in msg and "favicon" not in msg:
            print(f"  [HTTP] {msg}")

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path.rstrip("/")
            if path == "":
                path = "/"

            if path == "/favicon.ico":
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.send_header("Connection", "close")
                self.end_headers()
                return

            if path == "/api/telegram_status":
                cfg = TelegramNotifier.load_config()
                out_bytes = json.dumps(cfg).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(out_bytes)))
                self.send_header("Connection", "close")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(out_bytes)
                return

            if path == "/api/telegram_detect":
                res = TelegramNotifier.detect_chat_id()
                out_bytes = json.dumps(res).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(out_bytes)))
                self.send_header("Connection", "close")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(out_bytes)
                return

            if path == "/api/live_scan":
                with CACHE_LOCK:
                    out_bytes = json.dumps(GLOBAL_SCAN_CACHE, cls=NumpyEncoder).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(out_bytes)))
                self.send_header("Connection", "close")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(out_bytes)
                return

            with CACHE_LOCK:
                init_json = json.dumps(GLOBAL_SCAN_CACHE, cls=NumpyEncoder)
            injected_html = HTML_PAGE.replace('<script>', f'<script>\n        window.__INIT_DATA__ = {init_json};\n')
            content = injected_html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Connection", "close")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(content)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def do_POST(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/api/telegram_save":
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode("utf-8")
                params = json.loads(body) if body else {}
                cfg = TelegramNotifier.load_config()
                cfg["chat_id"] = str(params.get("chat_id", "")).strip()
                cfg["enabled"] = bool(params.get("enabled", True))
                TelegramNotifier.save_config(cfg)
                out_bytes = json.dumps({"success": True, "message": "Kaydedildi"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(out_bytes)))
                self.send_header("Connection", "close")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(out_bytes)
                return

            if parsed.path == "/api/telegram_test":
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode("utf-8")
                params = json.loads(body) if body else {}
                chat_id = str(params.get("chat_id", "")).strip()
                test_msg = "<b>🎯 TURTLE SOUP TELEGRAM TEST BİLDİRİMİ</b>\n\n✅ Telegram bot entegrasyonu başarıyla aktif edildi!\n📡 Canlı Turtle Soup sinyalleri tespit edildiğinde anında bu kanala iletilecektir."
                ok = TelegramNotifier.send_message(test_msg, chat_id=chat_id)
                out_bytes = json.dumps({"success": ok, "message": "Mesaj iletildi" if ok else "Mesaj gönderilemedi. Bot ile sohbeti başlattığınızdan emin olun."}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(out_bytes)))
                self.send_header("Connection", "close")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(out_bytes)
                return

            if parsed.path == "/api/backtest":
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode("utf-8")
                params = json.loads(body) if body else {}

                raw_filename = params.get("filename")
                if not raw_filename or not isinstance(raw_filename, str) or not raw_filename.strip():
                    raw_filename = "BTCUSDT_5m.csv"
                
                filename = os.path.basename(raw_filename.strip())
                filepath = os.path.join(DATA_DIR, filename)

                if not os.path.isfile(filepath):
                    # Fallback arama
                    found = False
                    for item in DataLoader.ASSETS:
                        if item["file"] == filename or item["symbol"].replace("/", "") == filename.replace("_5m.csv", "").replace(".csv", ""):
                            filepath = os.path.join(DATA_DIR, item["file"])
                            found = True
                            break
                    if not found or not os.path.isfile(filepath):
                        csv_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".csv")]
                        filepath = os.path.join(DATA_DIR, csv_files[0] if csv_files else "BTCUSDT_5m.csv")

                time_range = params.get("time_range", "60d")

                strat_config = StrategyConfig(
                    risk_reward_ratio=float(params.get("risk_reward_ratio", 2.0)),
                    sl_buffer_pct=float(params.get("sl_buffer_pct", 0.0005)),
                    risk_per_trade_pct=float(params.get("risk_per_trade_pct", 1.0)),
                    use_trend_filter=bool(params.get("use_trend_filter", True)),
                    ema_period=int(params.get("ema_period", 200)),
                    min_sweep_depth_pct=float(params.get("min_sweep_depth_pct", 0.0015))
                )

                bt_config = BacktestConfig(
                    initial_capital=float(params.get("initial_capital", 10000.0)),
                    commission_rate=float(params.get("commission_rate", 0.0006)),
                    slippage_pct=float(params.get("slippage_pct", 0.0002))
                )

                df_5m = DataLoader.load_csv(filepath)

                # Quant İyileştirmesi: 200 EMA ve 4H seviyelerini tam geçmiş veriyle ısıt
                strategy = TurtleSoupStrategy(strat_config)
                df_signals = strategy.generate_signals(df_5m)

                # İstenen zaman aralığını sinyaller oluştuktan sonra dilimle (Sıfır Isınma Hatası)
                days_map = {"7d": 7, "14d": 14, "30d": 30, "60d": 60}
                if time_range in days_map:
                    bars_to_keep = days_map[time_range] * 288
                    if len(df_signals) > bars_to_keep:
                        df_signals = df_signals.iloc[-bars_to_keep:].copy()

                engine = BacktestEngine(strat_config, bt_config)
                result = engine.run(df_signals)

                df_res = result['df']
                trades = result['trades']
                metrics = PerformanceMetrics.calculate(
                    trades=trades,
                    initial_capital=bt_config.initial_capital,
                    final_capital=result['final_capital'],
                    equity_series=result['equity_series']
                )

                chart_candles = []
                chart_h4_high = []
                chart_h4_low = []
                chart_ema = []
                chart_equity = []

                for idx, row in df_res.iterrows():
                    t = int(idx.timestamp())
                    chart_candles.append({
                        "time": t,
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"])
                    })
                    if not np.isnan(row.get("prev_4h_high", np.nan)):
                        chart_h4_high.append({"time": t, "value": float(row["prev_4h_high"])})
                    if not np.isnan(row.get("prev_4h_low", np.nan)):
                        chart_h4_low.append({"time": t, "value": float(row["prev_4h_low"])})
                    if not np.isnan(row.get("ema_200", np.nan)):
                        chart_ema.append({"time": t, "value": float(row["ema_200"])})

                    chart_equity.append({
                        "time": t,
                        "value": float(row["equity"])
                    })

                response_data = {
                    "metrics": metrics,
                    "trades": [t.to_dict() for t in trades],
                    "chart_candles": chart_candles,
                    "chart_h4_high": chart_h4_high,
                    "chart_h4_low": chart_h4_low,
                    "chart_ema": chart_ema,
                    "chart_equity": chart_equity
                }

                out_bytes = json.dumps(response_data, cls=NumpyEncoder).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(out_bytes)))
                self.send_header("Connection", "close")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(out_bytes)
            else:
                self.send_error(404, "API endpoint bulunamadi")
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

def start_server(port=8080):
    print("[1/2] 🚀 Tüm 74 varlığın verisi RAM'e önbellekleniyor (Lütfen birkaç saniye bekleyin)...")
    scan_all_markets()
    print(f"[2/2] ✅ 74 Varlık hazır! {len(GLOBAL_SCAN_CACHE['recent_feed'])} aktif seans sinyali tespit edildi.")
    server = RobustThreadingServer(("0.0.0.0", port), BacktestRequestHandler)
    print(f"\n=======================================================")
    print(f"🚀 TURTLE SOUP PRO SUITE HAZIR!")
    print(f"👉 Tarayıcınızda açın: http://localhost:{port}")
    print(f"=======================================================\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSunucu durduruldu.")

if __name__ == "__main__":
    start_server(8080)
