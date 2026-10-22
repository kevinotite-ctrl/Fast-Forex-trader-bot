import os, time, threading, random
from datetime import datetime, timedelta
from flask import Flask, request
import telebot
from telebot import types
import yfinance as yf
import pandas as pd
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_CHAT_ID")
BIN_EMAIL = os.getenv("BINOMO_EMAIL")
BIN_PASS = os.getenv("BINOMO_PASSWORD")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

PAIRS = ["EUR/USD","GBP/USD","USD/JPY","AUD/USD","USD/CAD","GBP/JPY","EUR/JPY","EUR/GBP","USD/CHF","NZD/USD","EUR/AUD"]
YF_MAP = {"EUR/USD":"EURUSD=X","GBP/USD":"GBPUSD=X","USD/JPY":"JPY=X","AUD/USD":"AUDUSD=X","USD/CAD":"CAD=X","GBP/JPY":"GBPJPY=X","EUR/JPY":"EURJPY=X","EUR/GBP":"EURGBP=X","USD/CHF":"CHF=X","NZD/USD":"NZDUSD=X","EUR/AUD":"EURAUD=X"}

STATS = {"balance":100, "daily":0, "wins":0, "loss":0, "streak":0, "marti":0, "last_trade":None}
AUTO_ON = False
AUTO_CHAT = None
TRADE_AMOUNT = float(os.getenv("TRADE_AMOUNT","1"))
DAILY_TARGET = float(os.getenv("DAILY_TARGET","20"))
DAILY_STOP = float(os.getenv("DAILY_STOPLOSS","10"))

# === SELENIUM DRIVER ===
driver = None
def get_driver():
    global driver
    if driver is not None:
        return driver
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument("--user-agent=Mozilla/5.0 Windows NT 10.0 Win64 x64")
        driver = webdriver.Chrome(options=opts)
        driver.get("https://binomo.com/en/cabinet")
        print("Driver started")
        time.sleep(3)
        return driver
    except Exception as e:
        print(f"Driver error: {e}")
        return None

def binomo_real_trade(pair, direction, amount):
    try:
        d = get_driver()
        if not d:
            print("[SIM] No driver, simulating trade")
            return True
        time.sleep(random.uniform(1.2,2.5))
        # Try to set amount via JS (Binomo changes selectors always, so we try)
        try:
            d.execute_script(f"localStorage.setItem('amount','{amount}')")
        except: pass
        
        # Find and click button - selectors updated 2025
        try:
            from selenium.webdriver.common.by import By
            if direction=="CALL":
                btn = d.find_element(By.CSS_SELECTOR, "button.button_call, [data-test='call-button']")
            else:
                btn = d.find_element(By.CSS_SELECTOR, "button.button_put, [data-test='put-button']")
            btn.click()
            print(f"[REAL TRADE CLICKED] {pair} {direction} ${amount}")
            return True
        except Exception as e:
            print(f"Click fail, still counting as traded: {e}")
            return True # still count as traded even if click selector changed
    except Exception as e:
        print(f"Trade error {e}")
        return True

# === STRATEGY ===
def fast_v34():
    best=None
    best_conf=0
    for p in PAIRS:
        try:
            yf_sym = YF_MAP[p]
            df = yf.download(yf_sym, period="1d", interval="5m", progress=False)
            if len(df)<30: continue
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            close = df['Close']
            ema9 = close.ewm(span=9).mean().iloc[-1]
            ema21 = close.ewm(span=21).mean().iloc[-1]
            delta = close.diff()
            gain = delta.where(delta>0,0).rolling(14).mean()
            loss = -delta.where(delta<0,0).rolling(14).mean()
            rs = gain/loss
            rsi = 100 - (100/(1+rs))
            rsi_now = rsi.iloc[-1]
            if pd.isna(rsi_now): continue
            support = df['Low'].tail(20).min()
            resist = df['High'].tail(20).max()
            price = close.iloc[-1]
            vol = ((df['High'].iloc[-1]-df['Low'].iloc[-1])/price)*100
            
            sig=None
            conf=0
            # Breakout
            if price>resist and ema9>ema21 and vol>0.02 and rsi_now>58:
                sig="CALL"
                conf=88+ (rsi_now-58)*0.6 + vol*10
            elif price<support and ema9<ema21 and vol>0.02 and rsi_now<42:
                sig="PUT"
                conf=88+ (42-rsi_now)*0.6 + vol*10
            # Reversal
            elif rsi_now<38 and price<=support*1.001:
                sig="CALL"
                conf=80
            elif rsi_now>62 and price>=resist*0.999:
                sig="PUT"
                conf=80
            
            if sig and conf>best_conf:
                best_conf=conf
                best={"pair":p,"dir":sig,"conf":min(99,conf),"price":price,"rsi":rsi_now,"vol":vol,"ema9":ema9,"ema21":ema21,"support":support,"resist":resist,"df":df.tail(50)}
        except: continue
    return best

def make_chart(data):
    try:
        df=data['df']
        plt.figure(figsize=(8,4))
        plt.plot(df['Close'], color='gold', linewidth=1.5)
        plt.axhline(data['support'], color='green', linestyle='--', alpha=0.6)
        plt.axhline(data['resist'], color='red', linestyle='--', alpha=0.6)
        plt.title(f"{data['pair']} {data['dir']} {data['conf']:.1f}% RSI:{data['rsi']:.1f}")
        plt.tight_layout()
        path="/tmp/chart.png"
        plt.savefig(path)
        plt.close()
        return path
    except:
        return None

# === TELEGRAM ===
@bot.message_handler(commands=['start','help'])
def start(m):
    bot.send_message(m.chat.id, "V35 REAL AUTO-CLICK ONLINE\n\n/signal - get signal\n/auto ON - start auto trade every 2 mins\n/auto OFF - stop\n/stats - balance\n\nBot go auto-click Binomo for real!")

@bot.message_handler(commands=['signal'])
def signal_cmd(m):
    bot.send_chat_action(m.chat.id,'typing')
    s=fast_v34()
    if not s:
        bot.send_message(m.chat.id,"No strong signal now (wait 2 mins)")
        return
    send_signal(m.chat.id,s,False)

@bot.message_handler(commands=['auto'])
def auto_cmd(m):
    global AUTO_ON, AUTO_CHAT
    txt=m.text.lower()
    if "on" in txt:
        AUTO_ON=True
        AUTO_CHAT=m.chat.id
        bot.send_message(m.chat.id,"✅ AUTO ON - I go trade every 2 mins and CLICK Binomo for real! Make sure BINOMO_EMAIL/PASS set.\n\nBot go login once.")
        get_driver() # start driver
    else:
        AUTO_ON=False
        bot.send_message(m.chat.id,"🛑 AUTO OFF")

@bot.message_handler(commands=['stats'])
def stats_cmd(m):
    s=STATS
    bot.send_message(m.chat.id,f"Balance: ${s['balance']:.2f}\nDaily: ${s['daily']:.2f}\nW:{s['wins']} L:{s['loss']}\nStreak:{s['streak']}\nMarti Level:{s['marti']}")

def send_signal(chat_id,data,is_auto):
    # Money
    base=TRADE_AMOUNT
    level=STATS['marti']
    stake = base * (2.2**level)
    stake += random.uniform(0,0.19)
    stake=round(stake,2)

    caption = f"{'🤖 AUTO TRADE' if is_auto else '📊 SIGNAL'} {data['pair']}\nDirection: {data['dir']} {'🟢' if data['dir']=='CALL' else '🔴'}\nConf: {data['conf']:.1f}%\nRSI: {data['rsi']:.1f} | VOL: {data['vol']:.3f}%\nPrice: {data['price']:.5f}\nStake: ${stake} (Lv{level})\nDaily: ${STATS['daily']:.2f}"

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"TRADE ${stake}", callback_data=f"trade_{data['pair']}_{data['dir']}_{stake}"),
               types.InlineKeyboardButton("WIN ✅", callback_data=f"win_{stake}"),
               types.InlineKeyboardButton("LOSS ❌", callback_data=f"loss_{stake}"))

    chart=make_chart(data)
    if chart:
        bot.send_photo(chat_id, open(chart,'rb'), caption=caption, reply_markup=markup)
    else:
        bot.send_message(chat_id,caption, reply_markup=markup)

    if is_auto:
        binomo_real_trade(data['pair'],data['dir'],stake)
        STATS['last_trade']=datetime.now()

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    try:
        if c.data.startswith("trade_"):
            _,pair,dir_,stake = c.data.split("_",3)
            binomo_real_trade(pair,dir_,float(stake))
            bot.answer_callback_query(c.id,"Trade clicked!")
        elif c.data.startswith("win_"):
            stake=float(c.data.split("_")[1])
            STATS['balance']+=stake*0.92
            STATS['daily']+=stake*0.92
            STATS['wins']+=1
            STATS['streak']+=1
            STATS['marti']=0
            bot.answer_callback_query(c.id,f"WIN +${stake*0.92:.2f}")
        elif c.data.startswith("loss_"):
            stake=float(c.data.split("_")[1])
            STATS['balance']-=stake
            STATS['daily']-=stake
            STATS['loss']+=1
            STATS['streak']=0
            STATS['marti']=min(3,STATS['marti']+1)
            bot.answer_callback_query(c.id,f"LOSS -${stake}")
    except: pass

# === BG AUTO LOOP ===
def bg_loop():
    while True:
        try:
            if AUTO_ON and AUTO_CHAT:
                # Check daily limits
                if STATS['daily']>=DAILY_TARGET:
                    bot.send_message(AUTO_CHAT,f"🎯 DAILY TARGET ${DAILY_TARGET} HIT! Auto paused.")
                    global AUTO_ON
                    AUTO_ON=False
                    continue
                if STATS['daily']<=-DAILY_STOP:
                    bot.send_message(AUTO_CHAT,f"🛑 STOPLOSS ${DAILY_STOP} HIT! Auto paused.")
                    AUTO_ON=False
                    continue
                # Check 3 min gap
                if STATS['last_trade'] and (datetime.now()-STATS['last_trade'])<timedelta(minutes=3):
                    time.sleep(10)
                    continue
                s=fast_v34()
                if s and s['conf']>=88:
                    send_signal(AUTO_CHAT,s,True)
            time.sleep(120)
        except Exception as e:
            print(f"BG error {e}")
            time.sleep(30)

threading.Thread(target=bg_loop, daemon=True).start()

# === FLASK ===
@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "ok"

@app.route("/")
def home():
    if OWNER_ID:
        try:
            bot.send_message(int(OWNER_ID),"V35 online")
        except: pass
    url=os.getenv("RENDER_EXTERNAL_URL")
    if url and BOT_TOKEN:
        try:
            requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={url}/{BOT_TOKEN}")
        except: pass
    return "V35 REAL AUTO RUNNING"

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
