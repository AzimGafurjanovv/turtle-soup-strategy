# -*- coding: utf-8 -*-
"""
Turtle Soup (4H Liquidity Sweep & Reclaim) Strateji Modülü
Kurallar:
1. 4H Seviyeleri: Standart UTC+0 4H barlarının (00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC) bir önceki mumunun High ve Low değerleri referans alınır.
2. 5m Mumlar:
   - Long Setup: 4H Low seviyesinin altına inilir (fitil veya mum kapanışı), ardından mum 4H Low seviyesinin ÜSTÜNE kapanır (reclaim).
   - Short Setup: 4H High seviyesinin üstüne çıkılır, ardından mum 4H High seviyesinin ALTINA kapanır (reclaim).
3. Seviye Tüketimi (Level Consumption): Aynı 4H bloğu içinde bir seviye geri kazanıldığında, seviye tüketilir; böylece her 10 dakikada bir sahte mükerrer sinyal üretilmesi engellenir.
4. Trend Filtresi (Opsiyonel): 200 EMA üstünde sadece Long, altında sadece Short.
5. Risk / Reward: TP = 1:2 R:R (parametrik), SL = Sweep en uç fitil noktası.
"""
import pandas as pd
import numpy as np
from config import StrategyConfig

class TurtleSoupStrategy:
    def __init__(self, config: StrategyConfig = None):
        self.config = config or StrategyConfig()

    def prepare_data(self, df_5m: pd.DataFrame) -> pd.DataFrame:
        df = df_5m.copy()
        
        # 1. Standart 4H Barları
        df_4h = df.resample('4h', origin='start_day').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        })
        
        # Geleceği Görmeme Garantisi (Shift 1): Yalnızca tamamlanmış 4H mumunun High/Low'u
        df_4h['prev_4h_high'] = df_4h['high'].shift(1)
        df_4h['prev_4h_low'] = df_4h['low'].shift(1)
        
        df = df.join(df_4h[['prev_4h_high', 'prev_4h_low']], how='left')
        df['prev_4h_high'] = df['prev_4h_high'].ffill()
        df['prev_4h_low'] = df['prev_4h_low'].ffill()
        
        # 2. 200 EMA Trend Göstergesi
        df['ema_200'] = df['close'].ewm(span=self.config.ema_period, adjust=False).mean()
        
        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self.prepare_data(df)
        
        n = len(df)
        signals = np.zeros(n, dtype=int)        # 1: Long, -1: Short, 0: Nötr
        stop_loss = np.zeros(n, dtype=float)
        take_profit = np.zeros(n, dtype=float)
        sweep_extremes = np.zeros(n, dtype=float)
        
        opens = df['open'].values
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        prev_h4_highs = df['prev_4h_high'].values
        prev_h4_lows = df['prev_4h_low'].values
        ema_vals = df['ema_200'].values
        
        current_h4_ref_low = np.nan
        current_h4_ref_high = np.nan
        
        is_sweeping_low = False
        sweep_min_low = np.inf
        h4_low_consumed = False
        
        is_sweeping_high = False
        sweep_max_high = -np.inf
        h4_high_consumed = False
        
        for i in range(1, n):
            h4_low = prev_h4_lows[i]
            h4_high = prev_h4_highs[i]
            c_price = closes[i]
            h_price = highs[i]
            l_price = lows[i]
            ema = ema_vals[i]
            
            if np.isnan(h4_low) or np.isnan(h4_high) or np.isnan(ema):
                continue
                
            # Yeni 4H referans bloğuna geçildiğinde seviyeleri sıfırla
            if h4_low != current_h4_ref_low or h4_high != current_h4_ref_high:
                current_h4_ref_low = h4_low
                current_h4_ref_high = h4_high
                is_sweeping_low = False
                is_sweeping_high = False
                sweep_min_low = np.inf
                sweep_max_high = -np.inf
                h4_low_consumed = False
                h4_high_consumed = False

            # ==========================================
            # 1. LONG SETUP: 4H Low Likidite Avı & Reclaim
            # ==========================================
            if self.config.allow_long:
                # Fiyat 4H Low altına indi mi?
                if l_price < h4_low:
                    if l_price < sweep_min_low:
                        sweep_min_low = l_price
                        is_sweeping_low = True
                        h4_low_consumed = False # Daha derin taze likidite avı

                # Reclaim kontrolü (Kapanış 4H Low üstüne çıktı mı?)
                if is_sweeping_low and (c_price > h4_low) and not h4_low_consumed:
                    trend_ok = (not self.config.use_trend_filter) or (c_price > ema)
                    depth_pct = (h4_low - sweep_min_low) / h4_low
                    depth_ok = depth_pct >= self.config.min_sweep_depth_pct
                    
                    if trend_ok and depth_ok:
                        entry_price = c_price
                        sl = sweep_min_low * (1.0 - self.config.sl_buffer_pct)
                        risk = entry_price - sl
                        
                        if risk > 0:
                            tp = entry_price + (risk * self.config.risk_reward_ratio)
                            signals[i] = 1
                            stop_loss[i] = sl
                            take_profit[i] = tp
                            sweep_extremes[i] = sweep_min_low
                            
                    # Seviye bu sweep döngüsü için tüketildi
                    h4_low_consumed = True
                    is_sweeping_low = False

            # ==========================================
            # 2. SHORT SETUP: 4H High Likidite Avı & Reclaim
            # ==========================================
            if self.config.allow_short:
                # Fiyat 4H High üstüne çıktı mı?
                if h_price > h4_high:
                    if h_price > sweep_max_high:
                        sweep_max_high = h_price
                        is_sweeping_high = True
                        h4_high_consumed = False

                # Reclaim kontrolü (Kapanış 4H High altına indi mi?)
                if is_sweeping_high and (c_price < h4_high) and not h4_high_consumed:
                    trend_ok = (not self.config.use_trend_filter) or (c_price < ema)
                    depth_pct = (sweep_max_high - h4_high) / h4_high
                    depth_ok = depth_pct >= self.config.min_sweep_depth_pct
                    
                    if trend_ok and depth_ok:
                        entry_price = c_price
                        sl = sweep_max_high * (1.0 + self.config.sl_buffer_pct)
                        risk = sl - entry_price
                        
                        if risk > 0:
                            tp = entry_price - (risk * self.config.risk_reward_ratio)
                            signals[i] = -1
                            stop_loss[i] = sl
                            take_profit[i] = tp
                            sweep_extremes[i] = sweep_max_high
                            
                    h4_high_consumed = True
                    is_sweeping_high = False
                    
        df['signal'] = signals
        df['sl_price'] = stop_loss
        df['tp_price'] = take_profit
        df['sweep_extreme'] = sweep_extremes
        
        return df
