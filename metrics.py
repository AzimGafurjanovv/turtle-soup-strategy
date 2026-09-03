# -*- coding: utf-8 -*-
"""
Turtle Soup Kantitatif Performans Metrikleri Hesaplama Modülü
Win Rate, Profit Factor, Sharpe, Sortino, Expectancy, Max Drawdown vb.
"""
from typing import List, Dict
import numpy as np
import pandas as pd
from engine import TradeRecord

class PerformanceMetrics:
    @staticmethod
    def calculate(trades: List[TradeRecord], initial_capital: float, final_capital: float, equity_series: np.ndarray) -> Dict:
        """
        Detaylı quant performans istatistiklerini hesaplar.
        """
        total_trades = len(trades)
        
        if total_trades == 0:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate_pct': 0.0,
                'profit_factor': 0.0,
                'net_profit_dollar': 0.0,
                'net_profit_pct': 0.0,
                'gross_profit': 0.0,
                'gross_loss': 0.0,
                'max_drawdown_pct': 0.0,
                'max_drawdown_dollar': 0.0,
                'sharpe_ratio': 0.0,
                'sortino_ratio': 0.0,
                'calmar_ratio': 0.0,
                'expectancy_dollar': 0.0,
                'expectancy_r': 0.0,
                'avg_win_dollar': 0.0,
                'avg_loss_dollar': 0.0,
                'payoff_ratio': 0.0,
                'long_trades': 0,
                'short_trades': 0,
                'long_win_rate_pct': 0.0,
                'short_win_rate_pct': 0.0,
                'avg_duration_minutes': 0.0,
                'max_consecutive_wins': 0,
                'max_consecutive_losses': 0
            }

        pnls = np.array([t.pnl_net for t in trades])
        r_multiples = np.array([t.r_multiple for t in trades])
        
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_trades) * 100.0
        
        gross_profit = float(np.sum(wins)) if wins else 0.0
        gross_loss = float(abs(np.sum(losses))) if losses else 0.0
        
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 99.99
        
        net_profit_dollar = round(final_capital - initial_capital, 2)
        net_profit_pct = round((net_profit_dollar / initial_capital) * 100.0, 2)
        
        avg_win = float(np.mean(wins)) if wins else 0.0
        avg_loss = float(abs(np.mean(losses))) if losses else 0.0
        payoff_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0
        
        # Expectancy
        expectancy_dollar = round(float(np.mean(pnls)), 2)
        expectancy_r = round(float(np.mean(r_multiples)), 2)
        
        # Max Drawdown
        peak = initial_capital
        max_dd_pct = 0.0
        max_dd_dollar = 0.0
        for eq in equity_series:
            if eq > peak:
                peak = eq
            dd_d = peak - eq
            dd_p = (dd_d / peak) * 100.0 if peak > 0 else 0.0
            if dd_p > max_dd_pct:
                max_dd_pct = dd_p
            if dd_d > max_dd_dollar:
                max_dd_dollar = dd_d
                
        # Sharpe & Sortino (Bar-by-bar getiri analizi, 5m verisi için yıllıklandırma: 288 * 365 = 105,120 bar)
        returns = np.diff(equity_series) / equity_series[:-1]
        returns = returns[~np.isnan(returns)]
        
        annual_factor = np.sqrt(105120)
        mean_ret = np.mean(returns) if len(returns) > 0 else 0.0
        std_ret = np.std(returns) if len(returns) > 0 else 0.0
        sharpe = round(float((mean_ret / std_ret) * annual_factor), 2) if std_ret > 0 else 0.0
        
        downside_returns = returns[returns < 0]
        downside_std = np.std(downside_returns) if len(downside_returns) > 0 else 0.0
        sortino = round(float((mean_ret / downside_std) * annual_factor), 2) if downside_std > 0 else 0.0
        
        calmar = round(net_profit_pct / max_dd_pct, 2) if max_dd_pct > 0 else 0.0
        
        # Long vs Short Ayrımı
        long_trades = [t for t in trades if t.direction == 'LONG']
        short_trades = [t for t in trades if t.direction == 'SHORT']
        
        long_wins = [t for t in long_trades if t.pnl_net > 0]
        short_wins = [t for t in short_trades if t.pnl_net > 0]
        
        long_wr = (len(long_wins) / len(long_trades) * 100.0) if long_trades else 0.0
        short_wr = (len(short_wins) / len(short_trades) * 100.0) if short_trades else 0.0
        
        avg_dur = float(np.mean([t.duration_minutes for t in trades]))
        
        # Ardışık Kazanma / Kaybetme Serileri
        cur_w, max_w, cur_l, max_l = 0, 0, 0, 0
        for p in pnls:
            if p > 0:
                cur_w += 1
                cur_l = 0
                max_w = max(max_w, cur_w)
            else:
                cur_l += 1
                cur_w = 0
                max_l = max(max_l, cur_l)
                
        return {
            'total_trades': total_trades,
            'winning_trades': win_count,
            'losing_trades': loss_count,
            'win_rate_pct': round(win_rate, 2),
            'profit_factor': profit_factor,
            'net_profit_dollar': net_profit_dollar,
            'net_profit_pct': net_profit_pct,
            'gross_profit': round(gross_profit, 2),
            'gross_loss': round(gross_loss, 2),
            'max_drawdown_pct': round(max_dd_pct, 2),
            'max_drawdown_dollar': round(max_dd_dollar, 2),
            'sharpe_ratio': sharpe,
            'sortino_ratio': sortino,
            'calmar_ratio': calmar,
            'expectancy_dollar': expectancy_dollar,
            'expectancy_r': expectancy_r,
            'avg_win_dollar': round(avg_win, 2),
            'avg_loss_dollar': round(avg_loss, 2),
            'payoff_ratio': payoff_ratio,
            'long_trades': len(long_trades),
            'short_trades': len(short_trades),
            'long_win_rate_pct': round(long_wr, 2),
            'short_win_rate_pct': round(short_wr, 2),
            'avg_duration_minutes': round(avg_dur, 1),
            'max_consecutive_wins': max_w,
            'max_consecutive_losses': max_l
        }
