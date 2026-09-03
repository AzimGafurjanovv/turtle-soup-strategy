# -*- coding: utf-8 -*-
"""
Turtle Soup Backtest Motoru (Event-Driven Execution Simulation)
Intra-bar TP/SL kontrolü, işlem kayması (slippage), borsa komisyonları ve portföy dinamikleri.
"""
from dataclasses import dataclass, asdict
from typing import List, Dict
import numpy as np
import pandas as pd
from config import StrategyConfig, BacktestConfig

@dataclass
class TradeRecord:
    trade_id: int
    entry_time: str
    exit_time: str
    direction: str            # 'LONG' or 'SHORT'
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    sweep_extreme: float
    shares: float
    position_value: float
    pnl_gross: float
    commission_paid: float
    pnl_net: float
    return_pct: float
    exit_reason: str          # 'TAKE_PROFIT', 'STOP_LOSS', 'END_OF_DATA'
    duration_bars: int
    duration_minutes: int
    r_multiple: float

    def to_dict(self):
        return asdict(self)

class BacktestEngine:
    def __init__(self, strategy_config: StrategyConfig = None, backtest_config: BacktestConfig = None):
        self.strategy_config = strategy_config or StrategyConfig()
        self.backtest_config = backtest_config or BacktestConfig()

    def run(self, df_with_signals: pd.DataFrame) -> Dict:
        """
        Sinyal üretilmiş veri seti üzerinde gerçekçi simülasyon çalıştırır.
        """
        df = df_with_signals.copy()
        
        timestamps = df.index
        opens = df['open'].values
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        signals = df['signal'].values
        sl_prices = df['sl_price'].values
        tp_prices = df['tp_price'].values
        sweep_extremes = df['sweep_extreme'].values
        
        n = len(df)
        capital = self.backtest_config.initial_capital
        initial_cap = capital
        
        equity_series = np.zeros(n)
        cash_series = np.zeros(n)
        drawdown_series = np.zeros(n)
        
        trades: List[TradeRecord] = []
        trade_count = 0
        
        # Aktif Pozisyon Durumu
        in_position = False
        pos_direction = 0     # 1: Long, -1: Short
        pos_entry_price = 0.0
        pos_sl = 0.0
        pos_tp = 0.0
        pos_shares = 0.0
        pos_entry_bar = 0
        pos_entry_time = None
        pos_sweep_extreme = 0.0
        pos_risk_per_share = 0.0
        
        peak_equity = initial_cap
        
        for i in range(n):
            current_time = str(timestamps[i])
            o = opens[i]
            h = highs[i]
            l = lows[i]
            c = closes[i]
            
            # 1. Mevcut Pozisyon Varsa: Intra-Bar TP / SL Kontrolü
            if in_position:
                closed = False
                exit_price = 0.0
                exit_reason = ""
                
                if pos_direction == 1: # LONG Pozisyon
                    hit_sl = l <= pos_sl
                    hit_tp = h >= pos_tp
                    
                    if hit_sl and hit_tp:
                        # Aynı barda hem SL hem TP görülmüşse: Konservatif yaklaşım (Önce SL gerçekleşir)
                        exit_price = pos_sl * (1.0 - self.backtest_config.slippage_pct)
                        exit_reason = "STOP_LOSS"
                        closed = True
                    elif hit_sl:
                        exit_price = pos_sl * (1.0 - self.backtest_config.slippage_pct)
                        exit_reason = "STOP_LOSS"
                        closed = True
                    elif hit_tp:
                        exit_price = pos_tp * (1.0 - self.backtest_config.slippage_pct)
                        exit_reason = "TAKE_PROFIT"
                        closed = True
                        
                elif pos_direction == -1: # SHORT Pozisyon
                    hit_sl = h >= pos_sl
                    hit_tp = l <= pos_tp
                    
                    if hit_sl and hit_tp:
                        exit_price = pos_sl * (1.0 + self.backtest_config.slippage_pct)
                        exit_reason = "STOP_LOSS"
                        closed = True
                    elif hit_sl:
                        exit_price = pos_sl * (1.0 + self.backtest_config.slippage_pct)
                        exit_reason = "STOP_LOSS"
                        closed = True
                    elif hit_tp:
                        exit_price = pos_tp * (1.0 + self.backtest_config.slippage_pct)
                        exit_reason = "TAKE_PROFIT"
                        closed = True

                if closed:
                    trade_count += 1
                    if pos_direction == 1:
                        pnl_gross = (exit_price - pos_entry_price) * pos_shares
                    else:
                        pnl_gross = (pos_entry_price - exit_price) * pos_shares
                    
                    exit_val = exit_price * pos_shares
                    entry_val = pos_entry_price * pos_shares
                    commission = (entry_val + exit_val) * self.backtest_config.commission_rate
                    pnl_net = pnl_gross - commission
                    capital += pnl_net
                    
                    duration_bars = i - pos_entry_bar
                    duration_mins = duration_bars * 5
                    r_multiple = (pnl_net / (pos_risk_per_share * pos_shares)) if (pos_risk_per_share * pos_shares) > 0 else 0.0
                    
                    trade = TradeRecord(
                        trade_id=trade_count,
                        entry_time=str(pos_entry_time),
                        exit_time=current_time,
                        direction='LONG' if pos_direction == 1 else 'SHORT',
                        entry_price=round(pos_entry_price, 4),
                        exit_price=round(exit_price, 4),
                        stop_loss=round(pos_sl, 4),
                        take_profit=round(pos_tp, 4),
                        sweep_extreme=round(pos_sweep_extreme, 4),
                        shares=round(pos_shares, 4),
                        position_value=round(entry_val, 2),
                        pnl_gross=round(pnl_gross, 2),
                        commission_paid=round(commission, 2),
                        pnl_net=round(pnl_net, 2),
                        return_pct=round((pnl_net / entry_val) * 100, 2),
                        exit_reason=exit_reason,
                        duration_bars=duration_bars,
                        duration_minutes=duration_mins,
                        r_multiple=round(r_multiple, 2)
                    )
                    trades.append(trade)
                    in_position = False

            # 2. Yeni Sinyal Varsa ve Pozisyonda Değilsek: Pozisyon Aç
            if not in_position and signals[i] != 0:
                sig = signals[i]
                sl = sl_prices[i]
                tp = tp_prices[i]
                sweep_ext = sweep_extremes[i]
                
                # Giriş Fiyatı (Reclaim bar kapanışı + slippage)
                if sig == 1:
                    entry_p = c * (1.0 + self.backtest_config.slippage_pct)
                    risk_per_unit = entry_p - sl
                else:
                    entry_p = c * (1.0 - self.backtest_config.slippage_pct)
                    risk_per_unit = sl - entry_p
                    
                if risk_per_unit > 0:
                    # Sabit Risk Modeli: Portföyün %1'i riske edilir
                    risk_dollar = capital * (self.strategy_config.risk_per_trade_pct / 100.0)
                    shares = risk_dollar / risk_per_unit
                    
                    # Kaldıraç limiti kontrolü
                    max_position_val = capital * self.backtest_config.leverage
                    if (shares * entry_p) > max_position_val:
                        shares = max_position_val / entry_p
                        
                    if shares > 0:
                        in_position = True
                        pos_direction = sig
                        pos_entry_price = entry_p
                        pos_sl = sl
                        pos_tp = tp
                        pos_shares = shares
                        pos_entry_bar = i
                        pos_entry_time = timestamps[i]
                        pos_sweep_extreme = sweep_ext
                        pos_risk_per_share = risk_per_unit

            # 3. Bar Sonu Portföy Değeri (Equity) Hesaplama
            if in_position:
                if pos_direction == 1:
                    unrealized_pnl = (c - pos_entry_price) * pos_shares
                else:
                    unrealized_pnl = (pos_entry_price - c) * pos_shares
                current_equity = capital + unrealized_pnl
            else:
                current_equity = capital
                
            equity_series[i] = current_equity
            cash_series[i] = capital
            
            if current_equity > peak_equity:
                peak_equity = current_equity
                
            dd_pct = ((current_equity - peak_equity) / peak_equity) * 100.0 if peak_equity > 0 else 0.0
            drawdown_series[i] = dd_pct

        # Veri bittiğinde pozisyon açıksa kapat
        if in_position:
            trade_count += 1
            last_c = closes[-1]
            if pos_direction == 1:
                pnl_gross = (last_c - pos_entry_price) * pos_shares
            else:
                pnl_gross = (pos_entry_price - last_c) * pos_shares
            commission = (pos_entry_price * pos_shares + last_c * pos_shares) * self.backtest_config.commission_rate
            pnl_net = pnl_gross - commission
            capital += pnl_net
            
            trades.append(TradeRecord(
                trade_id=trade_count,
                entry_time=str(pos_entry_time),
                exit_time=str(timestamps[-1]),
                direction='LONG' if pos_direction == 1 else 'SHORT',
                entry_price=round(pos_entry_price, 4),
                exit_price=round(last_c, 4),
                stop_loss=round(pos_sl, 4),
                take_profit=round(pos_tp, 4),
                sweep_extreme=round(pos_sweep_extreme, 4),
                shares=round(pos_shares, 4),
                position_value=round(pos_entry_price * pos_shares, 2),
                pnl_gross=round(pnl_gross, 2),
                commission_paid=round(commission, 2),
                pnl_net=round(pnl_net, 2),
                return_pct=round((pnl_net / (pos_entry_price * pos_shares)) * 100, 2),
                exit_reason="END_OF_DATA",
                duration_bars=n - 1 - pos_entry_bar,
                duration_minutes=(n - 1 - pos_entry_bar) * 5,
                r_multiple=round(pnl_net / (pos_risk_per_share * pos_shares) if (pos_risk_per_share * pos_shares) > 0 else 0, 2)
            ))

        df['equity'] = equity_series
        df['drawdown'] = drawdown_series

        return {
            'df': df,
            'trades': trades,
            'final_capital': capital,
            'equity_series': equity_series,
            'drawdown_series': drawdown_series
        }
