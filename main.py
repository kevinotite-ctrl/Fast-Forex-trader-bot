import os, time, threading, datetime, random
from flask import Flask, request
import telebot

app = Flask(__name__)
TOKEN = os.getenv("BOT_TOKEN","").strip()
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL","").strip()

OWNER_ID = None
SCANNING = True
NEXT_SIGNAL_TIME = None
PAIRS = ["EURUSD-OTC","GBPUSD-OTC","GBPJPY-OTC","EURJPY-OTC","USDJPY-OTC","AUDUSD-OTC","EURGBP-OTC"]
FIXED_STAKE = 40
PRICE_HISTORY = {}
FLAGS = {"EURUSD":"🇪🇺🇺🇸","GBPUSD":"🇬🇧🇺🇸","GBPJPY":"🇬🇧🇯🇵","EURJPY":"🇪🇺🇯🇵","USDJPY":"🇺🇸🇯🇵","AUDUSD":"🇦🇺🇺🇸","EURGBP":"🇪🇺🇬🇧"}

def get_price(p):
    base = {"EURUSD":1.08,"GBPUSD":1.27,"GBPJPY":191,"EURJPY":162,"USDJPY":150,"AUDUSD":0.66,"EURGBP":0.85}.get(p.replace("-OTC",""),1.08)
    return base + random.uniform(-0.015, 0.015)

def calc_rsi(prices):
    if len(prices) < 15: return 50
    gains = [max(0, prices[i] - prices[i-1]) for i in range(1, len(prices))]
    losses = [abs(min(0, prices[i] - prices[i-1])) for i in range(1, len(prices))]
    ag = sum(gains[-14:]) / 14
    al = sum(losses[-14:]) / 14
    if al == 0: return 75
    return 100 - (100 / (1 + ag / al))

def get_best_random_signal():
    best = None
    best_score = 0
    for pair in PAIRS:
        price = get_price(pair)
        PRICE_HISTORY[pair].append(price)
        if len(PRICE_HISTORY[pair]) > 80: PRICE_HISTORY[pair].pop(0)
        rsi = calc_rsi(PRICE_HISTORY[pair])
        score = abs(rsi - 50)
        if score > best_score:
            best_score = score
            direction = "PUT" if rsi < 50 else "CALL"
            best = (pair, direction, round(rsi, 1), price)
    return best

bot = telebot.TeleBot(TOKEN, threaded=False)

def build_msg(pair, direction, rsi, price):
    now = datetime.datetime.now() + datetime.timedelta(hours=1)
    exp = now + datetime.timedelta(minutes=3)
    next_sig = exp + datetime.timedelta(minutes=2)
    clean = pair.replace("-OTC","")
    flag = FLAGS.get(clean,"🏳️")
    emoji = "🔴 PUT 🔻" if direction=="PUT" else "🟢 CALL 🔺"
    return f"""👑 {flag} {clean} {flag}

{emoji}
💱 {pair}
💰 ${FIXED_STAKE} | 📊 RSI {rsi}

⏰ {now.strftime('%H:%M')} → {exp.strftime('%H:%M')} WAT
⏭️ Next {next_sig.strftime('%H:%M')} WAT
"""

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID, NEXT_SIGNAL_TIME, PRICE_HISTORY
    OWNER_ID = m.chat.id
    PRICE_HISTORY = {}
    for pair in PAIRS:
        base = {"EURUSD":1.08,"GBPUSD":1.27,"GBPJPY":191,"EURJPY":162,"USDJPY":150,"AUDUSD":0.66,"EURGBP":0.85}.get(pair.replace("-OTC",""),1.08)
        PRICE_HISTORY[pair] = [base + random.uniform(-0.02,0.02) for _ in range(20)]
    NEXT_SIGNAL_TIME = time.time() + 120
    bot.send_message(m.chat.id, f"👑 ${FIXED_STAKE} BOT STARTED\n✅ First in 2m\n⏱️ Every 5m auto\n7 Pairs { ' '.join(FLAGS.values()) }")

@bot.message_handler(commands=['status','pause','resume'])
def cmds(m):
    global SCANNING, NEXT_SIGNAL_TIME
    txt = m.text.lower()
    if "/status" in txt:
        remain = int(NEXT_SIGNAL_TIME - time.time()) if NEXT_SIGNAL_TIME else 0
        remain = max(0, remain)
        bot.send_message(m.chat.id, f"👑 ${FIXED_STAKE} | {remain//60}m {remain%60}s to next")
    elif "/pause" in txt:
        SCANNING = False
        bot.send_message(m.chat.id, "⏸️ Paused")
    elif "/resume" in txt:
        SCANNING = True
        NEXT_SIGNAL_TIME = time.time() + 120
        bot.send_message(m.chat.id, "▶️ Resumed - 2m")

@app.route(f'/{TOKEN}', methods=['POST'])
def wh():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return ''

@app.route('/')
def home():
    return f"VIP ${FIXED_STAKE} LIVE", 200

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
            res = get_best_random_signal()
            if not res:
                pair = random.choice(PAIRS)
                direction = random.choice(["CALL","PUT"])
                res = (pair, direction, 50.0, get_price(pair))
            pair, direction, rsi, price = res
            try:
                bot.send_message(OWNER_ID, build_msg(pair, direction, rsi, price))
            except: pass
            NEXT_SIGNAL_TIME = time.time() + 300

threading.Thread(target=scanner, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
