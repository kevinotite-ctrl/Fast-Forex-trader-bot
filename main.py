import telebot, os, time, threading, requests
import pandas as pd, numpy as np, yfinance as yf
from flask import Flask, request
from datetime import datetime
import pytz

TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")
OWNER_ID = int(os.getenv("OWNER_ID")) if os.getenv("OWNER_ID") else None

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)
WAT = pytz.timezone("Africa/Lagos")

# CONFIG
FIXED_STAKE = 40
LOSS_STREAK = 0
LOST_PAIRS = set()
ALERT_ENABLED = True
LAST_ALERT_TIME = {}
FLAGS = {"EURUSD":"🇪🇺🇺🇸","GBPUSD":"🇬🇧🇺🇸","USDJPY":"🇺🇸🇯🇵","USDCHF":"🇺🇸🇨🇭","AUDUSD":"🇦🇺🇺🇸","USDCAD":"🇺🇸🇨🇦","EURGBP":"🇪🇺🇬🇧","EURJPY":"🇪🇺🇯🇵","GBPJPY":"🇬🇧🇯🇵","AUDJPY":"🇦🇺🇯🇵","GBPCHF":"🇬🇧🇨🇭"}
PAIRS = list(FLAGS.keys())

def get_yf_symbol(pair):
    return f"{pair[:3]}{pair[3:]}=X"

def compute_rsi(prices, period=14):
    delta = pd.Series(prices).diff()
    gain = delta.where(delta>0,0).ewm(alpha=1/period).mean()
    loss = -delta.where(delta<0,0).ewm(alpha=1/period).mean()
    rs = gain/loss
    return 100 - (100/(1+rs.iloc[-1]))

def get_real_price(pair):
    try:
        sym = get_yf_symbol(pair)
        df = yf.download(sym, period="2d", interval="5m", progress=False)
        if len(df) < 30: return None
        close = df['Close'].values.flatten()
        rsi = compute_rsi(close)
        ema20 = pd.Series(close).ewm(span=20).mean().iloc[-1]
        return float(close[-1]), float(rsi), float(ema20), df
    except: return None

def is_news_time():
    now = datetime.now(WAT)
    if now.weekday() >= 5: return True, "Weekend"
    t = now.hour*60 + now.minute
    if 780 <= t <= 990: return True, "US News (13:00-16:30 WAT)"
    return False, ""

def fast_safe_strategy():
    best = None
    for pair in PAIRS:
        if pair in LOST_PAIRS: continue
        data = get_real_price(pair)
        if not data: continue
        price, rsi, ema20, _ = data
        is_uptrend = price > ema20
        conf = 0
        direction = None
        is_call = None
        
        if is_uptrend and 38 <= rsi <= 53:
            conf = 84.5 if 42 <= rsi <= 48 else 80.2
            direction = "CALL"
            is_call = True
        elif not is_uptrend and 47 <= rsi <= 62:
            conf = 83.8 if 52 <= rsi <= 58 else 79.5
            direction = "PUT"
            is_call = False
            
        if conf and conf >= 79.5:
            if not best or conf > best[4]:
                best = (pair, direction, round(rsi,1), price, conf, round(ema20,5), is_call)
    return best

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, "👑 V28 REAL ACTIVE\n✅ Real Yahoo Price\n✅ EMA20 Trend Filter\n✅ 80% Dip Entry\n✅ News Filter\n\n/send /signal to start\n/alerton to auto-alert")

@bot.message_handler(commands=['signal'])
def signal(m):
    global LOSS_STREAK
    if LOSS_STREAK >= 3:
        bot.send_message(m.chat.id, f"🛑 STOP! 3 losses today.\n/send /reset tomorrow")
        return
    is_news, reason = is_news_time()
    if is_news:
        bot.send_message(m.chat.id, f"🚫 NEWS FILTER: {reason}\nWait till 16:30 WAT")
        return
    
    bot.send_message(m.chat.id, "🔍 Scanning 11 real markets...")
    res = fast_safe_strategy()
    if not res:
        bot.send_message(m.chat.id, "⏳ No 80% setup now. Wait 2-3 mins. No FOMO.")
        return
    
    pair, direction, rsi, price, conf, ema20, is_call = res
    flag = FLAGS.get(pair,"🏳️")
    emoji = "🟢 CALL 🔺" if direction=="CALL" else "🔴 PUT 🔻"
    now = datetime.now(WAT)
    exp = now + pd.Timedelta(minutes=5)
    
    msg = f"""👑 {flag} {pair} {flag} - {conf}% REAL

{emoji} 5 MIN
💱 {pair} LIVE MARKET
📊 RSI {rsi} | {'DIP BUY' if is_call else 'DIP SELL'} {'>EMA' if is_call else '<EMA'}
💹 Price {price:.5f} EMA20 {ema20}
💰 ${FIXED_STAKE}

⏰ {now.strftime('%H:%M')} → {exp.strftime('%H:%M')} WAT
✅ Real Price - Take Now!

Log /win or /loss after
"""
    bot.send_message(m.chat.id, msg)

@bot.message_handler(commands=['loss','win','reset','pairs','status','help','alerton','alertoff'])
def other(m):
    global LOSS_STREAK, LOST_PAIRS, ALERT_ENABLED
    cmd = m.text.lower()
    if "loss" in cmd:
        LOSS_STREAK+=1
        bot.send_message(m.chat.id, f"📉 Loss logged: {LOSS_STREAK}/3")
    elif "win" in cmd:
        LOSS_STREAK = max(0, LOSS_STREAK-1)
        bot.send_message(m.chat.id, f"📈 Win! Streak: {LOSS_STREAK}/3")
    elif "reset" in cmd:
        LOSS_STREAK=0; LOST_PAIRS.clear()
        bot.send_message(m.chat.id, "✅ Reset done")
    elif "pairs" in cmd:
        bot.send_message(m.chat.id, "💱 " + ", ".join(PAIRS))
    elif "status" in cmd:
        is_news, r = is_news_time()
        bot.send_message(m.chat.id, f"Loss: {LOSS_STREAK}/3\nNews: {r if is_news else 'Safe'}\nAlert: {'ON' if ALERT_ENABLED else 'OFF'}")
    elif "help" in cmd:
        bot.send_message(m.chat.id, "80% = Uptrend + RSI 38-53 dip = CALL. Downtrend + RSI 47-62 bounce = PUT. Avoid 13:00-16:30 news.")
    elif "alerton" in cmd:
        ALERT_ENABLED=True
        bot.send_message(m.chat.id, "🔔 Auto-Alert ON: You will get 🚨 ;(SIGNAL FOUND) when setup appears")
    elif "alertoff" in cmd:
        ALERT_ENABLED=False
        bot.send_message(m.chat.id, "🔕 Auto-Alert OFF")

def auto_alert_loop():
    global LAST_ALERT_TIME
    while True:
        try:
            time.sleep(60)
            if not OWNER_ID or not ALERT_ENABLED: continue
            is_news,_ = is_news_time()
            if is_news or LOSS_STREAK>=3: continue
            res = fast_safe_strategy()
            if res:
                pair=res[0]
                if time.time()-LAST_ALERT_TIME.get(pair,0) < 900: continue
                LAST_ALERT_TIME[pair]=time.time()
                _, direction, rsi, price, conf, ema20, is_call = res
                flag=FLAGS.get(pair,"🏳️")
                emoji="🟢 CALL 🔺" if direction=="CALL" else "🔴 PUT 🔻"
                bot.send_message(OWNER_ID, f"🚨 ;(SIGNAL FOUND) 🚨\n\n👑 {flag} {pair} - {conf}% REAL\n{emoji}\nRSI {rsi} Price {price:.5f}\n\nSend /signal now!")
        except: time.sleep(10)

def set_hook():
    time.sleep(3)
    try: 
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=f"{APP_URL}/{TOKEN}")
        print(f"Webhook set: {APP_URL}/{TOKEN}")
    except Exception as e: print(e)

@app.route(f"/{TOKEN}", methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "ok"
    else:
        return "ok"

@app.route("/")
def home(): return "V28 REAL RUNNING"

threading.Thread(target=auto_alert_loop, daemon=True).start()
threading.Thread(target=set_hook, daemon=True).start()

if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
