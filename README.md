# 🐢 Turtle Soup (4H Liquidity Sweep + Reclaim) Trading & Backtest Suite

Profesyonel seviyede, kurumsal likidite avı (Turtle Soup) konseptini multi-timeframe olarak simüle eden, sıfır lookahead bias ve tam parametrik risk yönetimine sahip Python kantitatif trading motoru ve web uygulaması.

---

## 📌 Strateji Mantığı ve Kurallar

1. **Zaman Dilimleri**:
   - **Referans Zaman Dilimi**: 4 Saatlik (H4) tamamlanmış mumların High ve Low seviyeleri.
   - **Yürütme Zaman Dilimi**: 5 Dakikalık (M5) mumlar.
2. **Sıfır Lookahead Bias**:
   - 4H mum seviyeleri `.shift(1)` ile geriye kaydırılarak 5m verisine eşleştirilir. Henüz kapanmamış bir 4H mumunun High/Low'u kesinlikle işleme dahil edilmez.
3. **Long Setup (Alış)**:
   - Fiyat, önceki 4H Low seviyesinin altına sarkar (**Liquidity Sweep**).
   - 5m periyodunda tekrar 4H Low seviyesinin üzerine çıkarak kapanış yapar (**Reclaim**).
   - **Stop Loss**: Sweep sırasındaki en düşük dip fitili (Extreme Low).
   - **Take Profit**: Giriş + (Risk × 2) — 1:2 R:R (Parametrik).
4. **Short Setup (Satış)**:
   - Fiyat, önceki 4H High seviyesinin üstüne çıkar (**Liquidity Sweep**).
   - 5m periyodunda tekrar 4H High seviyesinin altına inerek kapanış yapar (**Reclaim**).
   - **Stop Loss**: Sweep sırasındaki en yüksek tepe fitili (Extreme High).
   - **Take Profit**: Giriş - (Risk × 2) — 1:2 R:R.
5. **Trend Filtresi (200 EMA)**:
   - Açık olduğunda; Fiyat > EMA200 iken sadece Long, Fiyat < EMA200 iken sadece Short alınır.
6. **Risk ve Pozisyon Yönetimi**:
   - Portföyün sabit %1'i riske edilir ($Shares = \frac{Bakiye \times \%1}{|Giriş - SL|}$).
   - Aynı anda sadece 1 pozisyon açık olabilir.
   - Gerçekçi komisyon (%0.06) ve slippage (%0.02) kesintileri uygulanır.

---

## 🚀 Hızlı Başlangıç

### 1. Web Dashboard (İnteraktif Web Uygulaması)
Web arayüzünü başlatmak için:
```bash
python main.py --web
```
Ardından tarayıcınızda açın: **`http://localhost:8080`**

**Web Arayüzü Özellikleri:**
- 🎛️ **Canlı Parametre Değişimi**: R:R oranı, EMA filtresi, SL buffer ve risk yüzdesini slider ile anında değiştirip sonuçları milisaniyeler içinde görün.
- 📈 **TradingView İnteraktif Mum Grafiği**: 5m mumlar, 4H dinamik basamak seviyeleri, 200 EMA eğrisi ve Alış/Satış okları.
- 📊 **KPI Kartları**: Net Kar, Win Rate, Profit Factor, Max Drawdown, Sharpe ve Expectancy (R).
- 📉 **Equity Curve & Drawdown Grafiği**: Bakiye büyüme eğrisi ve tepe noktadan düşüş bölgeleri.
- 📋 **İşlem Geçmişi Tablosu & CSV İndirme**: Filtrelenebilir detaylı trade ledger.

---

### 2. Terminal (CLI) Modunda Çalıştırma

Varsayılan BTC/USDT verisiyle çalıştırmak için:
```bash
python main.py
```

Farklı parametrelerle çalıştırmak için:
```bash
python main.py --symbol ETHUSDT --rr 2.5 --risk 1.5
```

EMA filtresini kapatıp çalıştırmak için:
```bash
python main.py --no-trend-filter
```

Özel bir CSV dosyasını test etmek için:
```bash
python main.py --file "C:/yol/dosyaniz.csv" --rr 2.0
```

---

## 📁 Proje Dosya Yapısı

```
turtle_soup_strategy/
├── config.py          # Strateji ve Backtest parametreleri (Dataclass)
├── data_loader.py     # CSV yükleme & gerçekçi sentetik piyasa verisi üretici
├── strategy.py        # Multi-timeframe 4H sweep/reclaim sinyal motoru
├── engine.py          # Event-driven backtest & intra-bar TP/SL simülatörü
├── metrics.py         # Win rate, Sharpe, Sortino, Expectancy hesaplayıcı
├── plotter.py         # Matplotlib grafik çizim ve kayıt modülü
├── app.py             # HTTP Server & TradingView destekli Web Dashboard
├── main.py            # CLI ve Web sunucu başlatma ana giriş noktası
├── README.md          # Kullanım kılavuzu ve teknik döküman
├── data/              # 5m CSV veri setleri (BTC, ETH, SOL, EUR/USD)
└── static/            # Üretilen grafik ve statik dosyalar
```
