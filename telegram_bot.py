# -*- coding: utf-8 -*-
"""
Telegram Signal Alert Service for Turtle Soup Engine
Bot: @Cry2pto_Signal_Bot
"""
import os
import json
import urllib.request
import urllib.parse
from datetime import datetime

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "telegram_config.json")

class TelegramNotifier:
    DEFAULT_TOKEN = "8797366527:AAGGQoXx9p9mJzFbV63Suqkj5sl6ShYb7Zg"

    @classmethod
    def load_config(cls):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "token": cls.DEFAULT_TOKEN,
            "chat_id": "",
            "enabled": True,
            "bot_username": "Cry2pto_Signal_Bot"
        }

    @classmethod
    def save_config(cls, data):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    @classmethod
    def send_message(cls, text: str, chat_id: str = None, token: str = None) -> bool:
        cfg = cls.load_config()
        t = token or cfg.get("token", cls.DEFAULT_TOKEN)
        c = chat_id or cfg.get("chat_id", "")

        if not t or not c:
            return False

        url = f"https://api.telegram.org/bot{t}/sendMessage"
        payload = {
            "chat_id": str(c),
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            res = urllib.request.urlopen(req, timeout=8)
            resp_data = json.loads(res.read().decode("utf-8"))
            return resp_data.get("ok", False)
        except Exception as e:
            print(f"[Telegram Send Error] {e}")
            return False

    @classmethod
    def detect_chat_id(cls, token: str = None):
        """
        Kullanıcı Telegram'da bota /start veya herhangi bir mesaj attığında
        Chat ID'sini otomatik olarak tespit eder.
        """
        cfg = cls.load_config()
        t = token or cfg.get("token", cls.DEFAULT_TOKEN)
        url = f"https://api.telegram.org/bot{t}/getUpdates?offset=-10"

        try:
            req = urllib.request.Request(url)
            res = urllib.request.urlopen(req, timeout=8)
            data = json.loads(res.read().decode("utf-8"))
            
            if data.get("ok") and data.get("result"):
                # En son mesaj atan kullanıcının chat id'sini bul
                updates = data["result"]
                for u in reversed(updates):
                    if "message" in u and "chat" in u["message"]:
                        chat = u["message"]["chat"]
                        chat_id = str(chat["id"])
                        username = chat.get("username", chat.get("first_name", "Kullanıcı"))
                        
                        # Yapılandırmayı otomatik kaydet
                        cfg["chat_id"] = chat_id
                        cls.save_config(cfg)
                        return {
                            "success": True,
                            "chat_id": chat_id,
                            "username": username,
                            "message": f"Chat ID başarıyla bulundu: {chat_id} ({username})"
                        }
                        
            return {
                "success": False,
                "message": "Henüz bota mesaj atılmamış. Lütfen Telegram'da @Cry2pto_Signal_Bot adresine gidip /start yazın ve tekrar deneyin."
            }
        except Exception as e:
            return {"success": False, "message": f"Bağlantı hatası: {e}"}

    @classmethod
    def send_signal_alert(cls, signal: dict):
        """
        Zengin HTML formatında canlı sinyal mesajı hazırlar ve gönderir.
        """
        cfg = cls.load_config()
        if not cfg.get("enabled", True) or not cfg.get("chat_id"):
            return False

        sym = signal.get("symbol", "N/A")
        name = signal.get("name", "")
        sig_type = signal.get("signal_type", "LONG")
        price = signal.get("price", 0)
        sl = signal.get("sl", 0)
        tp = signal.get("tp", 0)
        h4_high = signal.get("h4_high", 0)
        h4_low = signal.get("h4_low", 0)
        ema_state = signal.get("ema_state", "N/A")
        tv_sym = signal.get("tv", "BINANCE:BTCUSDT")
        
        is_long = sig_type == "LONG"
        emoji = "🟢" if is_long else "🔴"
        action = "LONG (ALIM)" if is_long else "SHORT (SATIŞ)"
        ref_level = f"4H Low (${h4_low})" if is_long else f"4H High (${h4_high})"
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S (UTC)")

        msg = f"""<b>🎯 TURTLE SOUP CANLI SİNYAL ALARMI 🎯</b>

{emoji} <b>Varlık:</b> #{sym.replace('/', '')} ({name})
⚡ <b>Sinyal Türü:</b> <b>{action}</b>
📊 <b>Likidite Avı:</b> {ref_level} Reclaim Edildi!

━━━━━━━━━━━━━━━━━━━━
📍 <b>Giriş Fiyatı:</b> <code>${price}</code>
🛑 <b>Stop Loss:</b> <code>${sl}</code> (Fitil Extremum)
🎯 <b>Take Profit (1:2):</b> <code>${tp}</code>
📈 <b>200 EMA Trend:</b> {ema_state}
⏰ <b>Zaman:</b> {now_str}
━━━━━━━━━━━━━━━━━━━━

🔗 <a href="https://www.tradingview.com/chart/?symbol={tv_sym}&interval=5">TradingView'da 5m Grafiği Aç ↗</a>

<i>🤖 @Cry2pto_Signal_Bot tarafından otomatik iletilmiştir.</i>"""

        return cls.send_message(msg)
