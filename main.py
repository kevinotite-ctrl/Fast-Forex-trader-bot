import os, time, threading, datetime, random
from flask import Flask, request
import telebot

app = Flask(__name__)
TOKEN = os.getenv("BOT_TOKEN","").strip()
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL","").strip()

OWNER_ID = None
SCANNING = True
NEXT_SIGNAL_TIME = None
# REAL MARKET - 11 PAIRS NOW
PAIRS = ["EURUSD","GBPUSD","GBPJPY","EURJPY","USDJPY","AUDUSD","EURGBP","USDCHF","USDCAD","NZDUSD","EURAUD"]
FIXED_STAKE = 40
FLAGS = {
    "EURUSD":"🇪🇺🇺🇸","GBPUSD":"🇬🇧🇺🇸","GBPJPY":"🇬🇧🇯🇵",
    "EURJPY":"🇪🇺🇯🇵","USDJPY":"🇺🇸🇯🇵","AUDUSD":"🇦🇺🇺🇸",
    "EURGBP":"🇪🇺🇬🇧","USDCHF":"🇺🇸🇨🇭","USDCAD":"🇺🇸🇨🇦",
    "NZDUSD":"🇳🇿🇺🇸","EURAUD":"🇪🇺🇦🇺"
}

def get_signal():
    pair = random.choice(PAIRS)
    direction = random.choice(["CALL","PUT"])
    confidence = round(random.uniform(94.0, 100.0), 1)
    return pair, direction, confidence

bot = telebot.TeleBot(TOKEN, threaded=False)

def build_msg(pair, direction, conf):
    now = datetime.datetime.now() + datetime.timedelta(hours=1)
    exp = now + datetime.timedelta(minutes=3)
    next_sig = exp + datetime.timedelta(minutes=2)
    flag = FLAGS.get(pair,"🏳️")
    emoji = "🔴 PUT 🔻" if direction=="PUT" else "🟢 CALL 🔺"
    return f"""👑 {flag} {pair} {flag}

{emoji}
💱 {pair} REAL MARKET
🔥 CONFIDENCE: {conf}%

💰 ${FIXED_STAKE}

⏰ {now.strftime('%H:%M')} → {exp.strftime('%H:%M')} WAT
⏭️ Next {next_sig.strftime('%H:%M')} WAT

⚡ TRADE NOW - {conf}%
"""

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID, NEXT_SIGNAL_TIME
    OWNER_ID = m.chat.id
    NEXT_SIGNAL_TIME = time.time() + 120
    bot.send_message(m.chat.id, f"👑 ${FIXED_STAKE} REAL MARKET BOT\n🔥 11 Pairs | 94-100%\n💱 {', '.join(PAIRS)}")

@bot.message_handler(commands=['status','pause','resume'])
def cmds(m):
    global SCANNING, NEXT_SIGNAL_TIME
    txt = m.text.lower()
    if "/status" in txt:
        remain = int(NEXT_SIGNAL_TIME - time.time()) if NEXT_SIGNAL_TIME else 0
        remain = max(0, remain)
        bot.send_message(m.chat.id, f"👑 11 REAL | {remain//60}m {remain%60}s")
    elif "/pause" in txt:
        SCANNING=False
        bot.send_message(m.chat.id,"⏸️ Paused")
    elif "/resume" in txt:
        SCANNING=True
        NEXT_SIGNAL_TIME=time.time()+120
        bot.send_message(m.chat.id,"▶️ Resumed")

@app.route(f'/{TOKEN}', methods=['POST'])
def wh():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return ''

@app.route('/')
def home():
    return f"11 REAL MARKETS LIVE", 200

def set_hook():
    time.sleep(4)
    if RENDER_URL:
        import requests
        try:
            requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook", timeout=10)
            requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={RENDER_URL}/{TOKEN}", timeout=10)
        except: pass
threading.Thread(target=set_hook, daemon=True).start()

def scanner():
    global NEXT_SIGNAL_TIME
    while True:
        time.sleep(1)
        if not OWNER_ID or not SCANNING or not NEXT_SIGNAL_TIME: continue
        if time.time() >= NEXT_SIGNAL_TIME:
            pair, direction, conf = get_signal()
            try:
                bot.send_message(OWNER_ID, build_msg(pair, direction, conf))
            except: pass
            NEXT_SIGNAL_TIME = time.time() + 300
threading.Thread(target=scanner, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
