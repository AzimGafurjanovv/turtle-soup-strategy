# -*- coding: utf-8 -*-
"""
Turtle Soup (4H Liquidity Sweep + Reclaim) Strateji ve Backtest Konfigürasyon Modülü
"""
from dataclasses import dataclass, asdict

@dataclass
class StrategyConfig:
    """Strateji Parametreleri (Multi-Timeframe & Risk & Sinyal)"""
    # Zaman Dilimleri
    base_timeframe: str = "5m"            # Yürütme ve sinyal zaman dilimi (5 dakika)
    htf_timeframe: str = "4h"             # Yüksek zaman dilimi referansı (4 saat)
    
    # Risk / Getiri ve Stop Yönetimi
    risk_reward_ratio: float = 2.0        # Varsayılan 1:2 R:R oranı (Parametrik: 1.5, 2.0, 3.0 vb.)
    sl_buffer_pct: float = 0.0005         # Stop Loss için sweep extremum'una eklenecek güvenlik marjı (%0.05)
    risk_per_trade_pct: float = 1.0       # Her işlemde portföyden riske edilecek oran (%)
    
    # Trend Filtresi (200 EMA)
    use_trend_filter: bool = True         # 200 EMA filtresi açık / kapalı toggle
    ema_period: int = 200                 # Trend belirleyici EMA periyodu
    
    # Likidite Sweep Kuralları
    max_sweep_bars: int = 48              # Sweep başladıktan sonra reclaim için izin verilen maksimum 5m bar sayısı (48 bar = 4 saat)
    min_sweep_depth_pct: float = 0.0      # Minimum sweep derinliği filtresi (%)
    
    # Pozisyon Kuralları
    max_open_positions: int = 1           # Aynı anda sadece 1 açık pozisyon kuralı
    allow_long: bool = True               # Long işlemlere izin ver
    allow_short: bool = True              # Short işlemlere izin ver

    def to_dict(self):
        return asdict(self)

@dataclass
class BacktestConfig:
    """Backtest & Portföy Simülasyon Parametreleri"""
    initial_capital: float = 10000.0      # Başlangıç Sermayesi ($)
    commission_rate: float = 0.0006       # Komisyon oranı (Maker/Taker %0.06)
    slippage_pct: float = 0.0002          # Kayma (Slippage) maliyeti (%0.02)
    leverage: float = 1.0                 # Kaldıraç oranı (1x = spot, 2x+ = vadeli)

    def to_dict(self):
        return asdict(self)
