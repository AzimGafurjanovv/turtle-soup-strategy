# -*- coding: utf-8 -*-
"""
Turtle Soup (4H Liquidity Sweep + Reclaim) Ana Calistirma Modulu (CLI & Web Entegrasyonu)
"""
import os
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import argparse
import pandas as pd

from config import StrategyConfig, BacktestConfig
from data_loader import DataLoader
from strategy import TurtleSoupStrategy
from engine import BacktestEngine
from metrics import PerformanceMetrics
from plotter import StrategyPlotter

def print_banner():
    print("=" * 75)
    print("         TURTLE SOUP (4H LIQUIDITY SWEEP + RECLAIM) QUANT SUITE")
    print("      Multi-Timeframe | Zero Lookahead Bias | Institutional Edge")
    print("=" * 75)

def run_cli_backtest(args):
    print_banner()
    
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    DataLoader.create_default_datasets(data_dir)
    
    filepath = args.file if args.file else os.path.join(data_dir, f"{args.symbol.replace('/', '')}_5m.csv")
    if not os.path.exists(filepath):
        filepath = os.path.join(data_dir, "BTCUSDT_5m.csv")
        
    print(f"📂 Veri Seti Yükleniyor: {filepath}")
    df_5m = DataLoader.load_csv(filepath)
    print(f"   Toplam Bar Sayısı : {len(df_5m):,} (5 Dakikalık Veri)")
    print(f"   Tarih Aralığı     : {df_5m.index[0]}  -->  {df_5m.index[-1]}")
    
    # 1. Konfigürasyon
    strat_cfg = StrategyConfig(
        risk_reward_ratio=args.rr,
        use_trend_filter=not args.no_trend_filter,
        ema_period=args.ema,
        risk_per_trade_pct=args.risk
    )
    
    bt_cfg = BacktestConfig(
        initial_capital=args.capital,
        commission_rate=args.commission / 100.0
    )
    
    print("\n⚙️ Strateji Parametreleri:")
    print(f"   - Risk/Reward Oranı     : 1:{strat_cfg.risk_reward_ratio}")
    print(f"   - Trend Filtresi        : {'AÇIK (200 EMA)' if strat_cfg.use_trend_filter else 'KAPALI'}")
    print(f"   - Risk / İşlem          : %{strat_cfg.risk_per_trade_pct}")
    print(f"   - Başlangıç Sermayesi   : ${bt_cfg.initial_capital:,.2f}")
    print(f"   - Komisyon Oranı        : %{args.commission}")
    
    # 2. Sinyal Üretimi
    print("\n🔍 4H Seviyeleri Hesaplanıyor & Sinyaller Taranıyor...")
    strategy = TurtleSoupStrategy(strat_cfg)
    df_signals = strategy.generate_signals(df_5m)
    
    # 3. Backtest Simülasyonu
    print("⚡ Backtest Motoru Çalıştırılıyor (Event-Driven Simulation)...")
    engine = BacktestEngine(strat_cfg, bt_cfg)
    result = engine.run(df_signals)
    
    trades = result['trades']
    metrics = PerformanceMetrics.calculate(
        trades=trades,
        initial_capital=bt_cfg.initial_capital,
        final_capital=result['final_capital'],
        equity_series=result['equity_series']
    )
    
    # 4. Sonuçları Ekrana Yazdır
    print("\n" + "="*75)
    print(f"                    📊 BACKTEST PERFORMANS RAPORU                    ")
    print("="*75)
    
    col1 = [
        ("Başlangıç Bakiyesi", f"${bt_cfg.initial_capital:,.2f}"),
        ("Bitiş Bakiyesi", f"${result['final_capital']:,.2f}"),
        ("Net Kar / Zarar", f"${metrics['net_profit_dollar']:+,.2f} ({metrics['net_profit_pct']:+.2f}%)"),
        ("Toplam İşlem Sayısı", f"{metrics['total_trades']}"),
        ("Kazanan / Kaybeden", f"{metrics['winning_trades']} / {metrics['losing_trades']}"),
        ("Kazanma Oranı (Win Rate)", f"%{metrics['win_rate_pct']:.2f}")
    ]
    
    col2 = [
        ("Profit Factor", f"{metrics['profit_factor']:.2f}"),
        ("Payoff Oranı (Win/Loss)", f"{metrics['payoff_ratio']:.2f}"),
        ("Maksimum Drawdown", f"-{metrics['max_drawdown_pct']:.2f}% (-${metrics['max_drawdown_dollar']:,.2f})"),
        ("Sharpe Oranı", f"{metrics['sharpe_ratio']:.2f}"),
        ("Sortino Oranı", f"{metrics['sortino_ratio']:.2f}"),
        ("Beklenti (Expectancy)", f"{metrics['expectancy_r']:+.2f}R (${metrics['expectancy_dollar']:+.2f})")
    ]
    
    for (k1, v1), (k2, v2) in zip(col1, col2):
        print(f"  {k1:<26}: {v1:<18} | {k2:<24}: {v2}")
        
    print("="*75)
    
    # Long & Short Dağılımı
    print(f"  Long İşlemler  : {metrics['long_trades']} Adet  (Win Rate: %{metrics['long_win_rate_pct']:.1f})")
    print(f"  Short İşlemler : {metrics['short_trades']} Adet  (Win Rate: %{metrics['short_win_rate_pct']:.1f})")
    print(f"  Ort. Süre / İşlem: {metrics['avg_duration_minutes']:.1f} Dakika ({metrics['avg_duration_minutes']/60:.1f} Saat)")
    print("="*75)
    
    # 5. Son İşlemler Tablosu
    if len(trades) > 0:
        print("\n📋 Son Gerçekleşen 5 İşlem:")
        print(f"  {'ID':<4} {'YÖN':<6} {'GİRİŞ TARİHİ':<17} {'GİRİŞ':<9} {'SL':<9} {'TP':<9} {'ÇIKIŞ':<9} {'NEDEN':<12} {'NET PNL':<10} {'R':<6}")
        print("  " + "-"*92)
        for t in trades[-5:]:
            print(f"  #{t.trade_id:<3} {t.direction:<6} {t.entry_time[:16]:<17} {t.entry_price:<9.2f} {t.stop_loss:<9.2f} {t.take_profit:<9.2f} {t.exit_price:<9.2f} {t.exit_reason:<12} ${t.pnl_net:<+9.2f} {t.r_multiple:+.1f}R")
        print("  " + "-"*92)
        
    # 6. Grafik Kaydet
    output_chart = os.path.join(os.path.dirname(__file__), "static", "equity_curve.png")
    StrategyPlotter.plot_equity_and_drawdown(result['df'], output_chart)
    print(f"\n📈 Görsel grafik dosyası oluşturuldu: {output_chart}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Turtle Soup 4H Liquidity Sweep & Reclaim Quantitative Backtest Engine")
    parser.add_argument("--symbol", type=str, default="BTCUSDT", help="Sembol adı (varsayılan: BTCUSDT)")
    parser.add_argument("--file", type=str, default=None, help="Özel 5m CSV veri dosyası yolu")
    parser.add_argument("--rr", type=float, default=2.0, help="Risk/Reward oranı (varsayılan: 2.0)")
    parser.add_argument("--risk", type=float, default=1.0, help="İşlem başına risk %% (varsayılan: 1.0)")
    parser.add_argument("--capital", type=float, default=10000.0, help="Başlangıç sermayesi (varsayılan: 10000)")
    parser.add_argument("--commission", type=float, default=0.06, help="Komisyon oranı %% (varsayılan: 0.06)")
    parser.add_argument("--no-trend-filter", action="store_true", help="200 EMA trend filtresini devre dışı bırak")
    parser.add_argument("--ema", type=int, default=200, help="EMA periyodu (varsayılan: 200)")
    parser.add_argument("--web", action="store_true", help="Web Dashboard sunucusunu başlat (http://localhost:8080)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8080)), help="Web Dashboard portu (varsayılan: 8080 veya $PORT)")
    
    args = parser.parse_args()
    
    if args.web:
        import app
        app.start_server(port=args.port)
    else:
        run_cli_backtest(args)
