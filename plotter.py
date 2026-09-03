# -*- coding: utf-8 -*-
"""
Turtle Soup Görselleştirme Modülü (Matplotlib & Static Export)
Equity Curve, Drawdown ve İşlem Dağılım Grafikleri.
"""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

class StrategyPlotter:
    @staticmethod
    def plot_equity_and_drawdown(df: pd.DataFrame, output_path: str = "static/equity_curve.png"):
        """
        Bakiye büyümesi ve drawdown grafiğini profesyonel temada çizer ve PNG olarak kaydeder.
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        plt.style.use('dark_background')
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), gridspec_kw={'height_ratios': [3, 1]}, sharex=True)
        fig.patch.set_facecolor('#0f172a')
        
        # 1. Equity Curve
        ax1.set_facecolor('#1e293b')
        ax1.plot(df.index, df['equity'], color='#10b981', linewidth=2.0, label='Portfolio Equity ($)')
        ax1.set_title('Turtle Soup (4H Sweep + Reclaim) - Equity Curve', fontsize=14, fontweight='bold', color='#f8fafc', pad=12)
        ax1.set_ylabel('Equity ($)', fontsize=11, color='#94a3b8')
        ax1.grid(True, linestyle='--', alpha=0.2, color='#64748b')
        ax1.legend(loc='upper left', framealpha=0.8, facecolor='#0f172a')
        
        # 2. Drawdown
        ax2.set_facecolor('#1e293b')
        ax2.fill_between(df.index, df['drawdown'], 0, color='#ef4444', alpha=0.4, label='Drawdown (%)')
        ax2.plot(df.index, df['drawdown'], color='#f87171', linewidth=1.2)
        ax2.set_ylabel('Drawdown (%)', fontsize=11, color='#94a3b8')
        ax2.set_xlabel('Tarih', fontsize=11, color='#94a3b8')
        ax2.grid(True, linestyle='--', alpha=0.2, color='#64748b')
        ax2.legend(loc='lower left', framealpha=0.8, facecolor='#0f172a')
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close()
        print(f"Equity Curve grafiği kaydedildi: {output_path}")
