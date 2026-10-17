import os, time, threading, datetime, random
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

app = Flask(__name__)

TOKEN = os.getenv("BOT_TOKEN","").strip()
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL","").strip()
OWNER_ID = None
SCANNING = True

PAIRS = ["EURUSD-OTC","GBPUSD-OTC","GBPJPY-OTC","EURJPY-OTC","USDJPY-OTC","AUDUSD-OTC"]
FIXED_STAKE = 40
MARTINGALE_TRACK = {}
PRICE_HISTORY = {}

def get_price(p):
    base={"EURUSD":1.08,"GBPUSD":1.27,"GBPJPY":191,"EURJPY":162,"USDJPY":150,"AUDUSD":0.66}.get(p.replace("-OTC",""),1.08)
    return base + random.uniform(-0.01,0.01)

def calc_rsi(prices):
    if len(prices)<15: return 50
    gains=[max(0,prices[i]-prices[i-1]) for i in range(1,len(prices))]
    losses=[abs(min(0,prices[i]-prices[i-1])) for i in range(1,len(prices))]
    ag=sum(gains[-14:])/14; al=sum(losses[-14:])/14
    if al==0: return 70
    return 100-(100/(1+ag/al))

def analyze(pair):
    price=get_price(pair)
    PRICE_HISTORY.setdefault(pair, []).append(price)
    if len(PRICE_HISTORY[pair])>80: PRICE_HISTORY[pair].pop(0)
    prices=PRICE_HISTORY[pair]
    if len(prices)<15: return None
    rsi=calc_rsi(prices)
    if rsi<40: return "PUT",80,round(rsi,1),price
    if rsi>60: return "CALL",80,round(rsi,1),price
    return None

bot = telebot.TeleBot(TOKEN, threaded=False)

def build_msg(pair, direction, rsi, price, step):
    now=datetime.datetime.now()+datetime.timedelta(hours=1)
    exp=now+datetime.timedelta(minutes=3)
    return f"""🔒 PRIVATE $40 BOT

💱 {pair} | STEP {step}
{'📉 PUT 🔻' if direction=='PUT' else '📈 CALL 🔺'} - 3 MIN
💰 Stake: ${FIXED_STAKE} (Fixed)
📊 RSI: {rsi} | 80%

⏰ {now.strftime('%H:%M')} WAT → {exp.strftime('%H:%M')} WAT

{'👉 FIRST $40 TRADE' if step==1 else f'👉 MARTINGALE STEP {step} - SAME $40'}
"""

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID
    OWNER_ID=m.chat.id
    bot.send_message(m.chat.id, f"🔒 PRIVATE $40 FIXED BOT\nStake: ${FIXED_STAKE} every trade\nPairs: {', '.join(PAIRS)}\n\n/test - test\n/win PAIR - win reset\n/loss PAIR - next step same $40\n/status")

@bot.message_handler(commands=['status','test','win','loss','pause','resume'])
def cmds(m):
    global SCANNING, MARTINGALE_TRACK
    txt=m.text
    if "/status" in txt:
        track="\n".join([f"{k}: Step {v}" for k,v in MARTINGALE_TRACK.items()]) or "No active"
        bot.send_message(m.chat.id, f"🔒 ${FIXED_STAKE} FIXED\nScanning: {SCANNING}\n{track}")
    elif "/pause" in txt:
        SCANNING=False; bot.send_message(m.chat.id,"Paused")
    elif "/resume" in txt:
        SCANNING=True; bot.send_message(m.chat.id,"Resumed")
    elif "/test" in txt:
        pair=random.choice(PAIRS); d=random.choice(["CALL","PUT"])
        mk=InlineKeyboardMarkup()
        mk.add(InlineKeyboardButton(f"Send ${FIXED_STAKE}", callback_data=f"s1_{pair}_{d}"))
        bot.send_message(m.chat.id, f"TEST {pair} {d} ${FIXED_STAKE}", reply_markup=mk)
    elif "/win" in txt:
        try:
            pair=txt.split()[1].upper()
            MARTINGALE_TRACK.pop(pair,None)
            bot.send_message(m.chat.id, f"✅ {pair} WIN - Reset Step 1")
        except: bot.send_message(m.chat.id,"Use: /win GBPJPY-OTC")
    elif "/loss" in txt:
        try:
            pair=txt.split()[1].upper()
            step=MARTINGALE_TRACK.get(pair,1)+1
            MARTINGALE_TRACK[pair]=step
            d=random.choice(["CALL","PUT"])
            price=get_price(pair); rsi=35 if d=="PUT" else 65
            msg=build_msg(pair,d,rsi,price,step)
            bot.send_message(OWNER_ID, msg)
            bot.send_message(m.chat.id, f"Sent Step {step} ${FIXED_STAKE} for {pair}")
        except Exception as e: bot.send_message(m.chat.id,f"Error {e}")

@bot.callback_query_handler(func=lambda c: True)
def cb(call):
    try:
        _,pair,d=call.data.split("_")
        MARTINGALE_TRACK[pair]=1
        price=get_price(pair); rsi=30 if d=="PUT" else 70
        msg=build_msg(pair,d,rsi,price,1)
        bot.send_message(OWNER_ID, msg)
        bot.edit_message_text(f"✅ Sent PRIVATE {pair} ${FIXED_STAKE}", call.message.chat.id, call.message.message_id)
    except: pass

@app.route(f'/{TOKEN}', methods=['POST'])
def wh():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return ''
@app.route('/')
def home(): return f"PRIVATE ${FIXED_STAKE} LIVE",200

def set_hook():
    time.sleep(4)
    if RENDER_URL:
        import requests
        requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook",timeout=10)
        requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={RENDER_URL}/{TOKEN}",timeout=10)
threading.Thread(target=set_hook,daemon=True).start()

def scanner():
    while True:
        time.sleep(40)
        if not OWNER_ID or not SCANNING: continue
        for pair in PAIRS:
            res=analyze(pair)
            if not res: continue
            d,conf,rsi,price=res
            mk=InlineKeyboardMarkup()
            mk.add(InlineKeyboardButton(f"Send ${FIXED_STAKE}", callback_data=f"s1_{pair}_{d}"))
            bot.send_message(OWNER_ID, f"🔔 PRIVATE {pair} {d} RSI {rsi} ${FIXED_STAKE}", reply_markup=mk)
            time.sleep(80)
            break

threading.Thread(target=scanner,daemon=True).start()
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
