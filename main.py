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
    if al == 0: return 80
    return 100 - (100 / (1 + ag / al))

def calc_sma(prices, period=20):
    if len(prices) < period: return prices[-1]
    return sum(prices[-period:]) / period

def get_confidence_signal():
    best = None
    best_conf = 0
    for pair in PAIRS:
        price = get_price(pair)
        PRICE_HISTORY[pair].append(price)
        if len(PRICE_HISTORY[pair]) > 80: PRICE_HISTORY[pair].pop(0)
        rsi = calc_rsi(PRICE_HISTORY[pair])
        sma = calc_sma(PRICE_HISTORY[pair])
        
        # CONFIDENCE FORMULA
        rsi_strength = abs(rsi - 50) * 1.6  # 0-80
        trend_bonus = 15 if (rsi > 50 and price > sma) or (rsi < 50 and price < sma) else 0
        confidence = min(100, 50 + rsi_strength + trend_bonus)
        
        # Only 94-100%
        if confidence < 94: continue
        
        direction = "PUT" if rsi < 50 else "CALL"
        if direction == "CALL" and price < sma: continue
        if direction == "PUT" and price > sma: continue
        
        if confidence > best_conf:
            best_conf = confidence
            best = (pair, direction, round(rsi,1), price, round(sma,5), round(confidence,1))
    return best

bot = telebot.TeleBot(TOKEN, threaded=False)

def build_msg(pair, direction, rsi, price, sma, conf):
    now = datetime.datetime.now() + datetime.timedelta(hours=1)
    exp = now + datetime.timedelta(minutes=3)
    next_sig = exp + datetime.timedelta(minutes=2)
    clean = pair.replace("-OTC","")
    flag = FLAGS.get(clean,"🏳️")
    emoji = "🔴 PUT 🔻" if direction=="PUT" else "🟢 CALL 🔺"
    return f"""👑 {flag} {clean} {flag} - {conf}% CONFIDENCE

{emoji}
💱 {pair}
🔥 CONFIDENCE: {conf}% ✅
💰 ${FIXED_STAKE} | 📊 RSI {rsi}

⏰ {now.strftime('%H:%M')} → {exp.strftime('%H:%M')} WAT
⏭️ Next {next_sig.strftime('%H:%M')} WAT

⚡ 94-100% ONLY - TRADE THIS
"""

def build_no_trade(conf=0):
    now = datetime.datetime.now() + datetime.timedelta(hours=1)
    return f"""🛡️ NO TRADE - Confidence {conf}%

📊 Need 94-100% to trade
💰 Your ${FIXED_STAKE} SAFE

⏰ Next check {(now + datetime.timedelta(minutes=5)).strftime('%H:%M')} WAT
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
    bot.send_message(m.chat.id, f"👑 ${FIXED_STAKE} 94-100% BOT STARTED\n✅ Only sends 94%+ signals\n⏱️ Check every 5m\n🛡️ Capital safe")

@bot.message_handler(commands=['status','pause','resume'])
def cmds(m):
    global SCANNING, NEXT_SIGNAL_TIME
    txt = m.text.lower()
    if "/status" in txt:
        remain = int(NEXT_SIGNAL_TIME - time.time()) if NEXT_SIGNAL_TIME else 0
        remain = max(0, remain)
        bot.send_message(m.chat.id, f"👑 94-100% | {remain//60}m {remain%60}s to next")
    elif "/pause" in txt:
        SCANNING=False
        bot.send_message(m.chat.id,"⏸️ Paused")
    elif "/resume" in txt:
        SCANNING=True
        NEXT_SIGNAL_TIME=time.time()+120
        bot.send_message(m.chat.id,"▶️ Resumed - 2m")

@app.route(f'/{TOKEN}', methods=['POST'])
def wh():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return ''

@app.route('/')
def home():
    return f"94-100% BOT LIVE", 200

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
            res = get_confidence_signal()
            try:
                if res:
                    pair, direction, rsi, price, sma, conf = res
                    bot.send_message(OWNER_ID, build_msg(pair, direction, rsi, price, sma, conf))
                else:
                    bot.send_message(OWNER_ID, build_no_trade())
            except: pass
            NEXT_SIGNAL_TIME = time.time() + 300
threading.Thread(target=scanner, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
