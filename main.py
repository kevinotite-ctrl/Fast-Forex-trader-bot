import os, time, threading, datetime, random
from flask import Flask, request
import telebot
from telebot import types
import yfinance as yf
import pandas as pd
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

app = Flask(__name__)
TOKEN = os.getenv("BOT_TOKEN","").strip()
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL","").strip()
BINOMO_EMAIL = os.getenv("BINOMO_EMAIL","").strip()
BINOMO_PASSWORD = os.getenv("BINOMO_PASSWORD","").strip()
BINOMO_ACCOUNT_TYPE = os.getenv("BINOMO_ACCOUNT_TYPE","DEMO").strip()
TRADE_AMOUNT = float(os.getenv("TRADE_AMOUNT","1"))
DAILY_TARGET = float(os.getenv("DAILY_TARGET","20"))
DAILY_STOPLOSS = float(os.getenv("DAILY_STOPLOSS","10"))

PAIRS = ["EURUSD","GBPUSD","GBPJPY","EURJPY","USDJPY","AUDUSD","EURGBP","USDCHF","USDCAD","NZDUSD","EURAUD"]
YF_MAP = {p:f"{p}=X" for p in PAIRS}
FLAGS = {"EURUSD":"🇪🇺🇺🇸","GBPUSD":"🇬🇧🇺🇸","GBPJPY":"🇬🇧🇯🇵","EURJPY":"🇪🇺🇯🇵","USDJPY":"🇺🇸🇯🇵","AUDUSD":"🇦🇺🇺🇸","EURGBP":"🇪🇺🇬🇧","USDCHF":"🇺🇸🇨🇭","USDCAD":"🇺🇸🇨🇦","NZDUSD":"🇳🇿🇺🇸","EURAUD":"🇪🇺🇦🇺"}

STATS = {"wins":0,"losses":0,"profit":0.0,"streak":0,"best_streak":0,"martingale_level":0,"daily_profit":0.0,"last_trade":0}
AUTO_ENABLED = {"global": False}
AUTO_CHAT_ID = None

def get_session():
    h=datetime.datetime.utcnow().hour
    if 8 <= h < 12: return "🌍 London 🔥 BEST"
    elif 13 <= h < 17: return "🗽 New York 🔥 BEST"
    elif 8 <= h < 17: return "🌍+🗽 Overlap 💎 ULTRA"
    else: return "🌙 Asian ⚠️ SLOW"
def is_news_time():
    m=datetime.datetime.utcnow().minute
    return m in [0,1,2,58,59]
def get_real_df(pair, interval="5m", period="1d"):
    try:
        df=yf.Ticker(YF_MAP.get(pair)).history(period=period, interval=interval)
        if len(df)<30: return None
        df['EMA9']=df['Close'].ewm(span=9).mean()
        df['EMA21']=df['Close'].ewm(span=21).mean()
        delta=df['Close'].diff()
        gain=delta.where(delta>0,0).rolling(14).mean()
        loss=-delta.where(delta<0,0).rolling(14).mean()
        rs=gain/loss
        df['RSI']=100-(100/(1+rs))
        df['SMA20']=df['Close'].rolling(20).mean()
        df['SUPPORT']=df['Low'].rolling(20).min()
        df['RESISTANCE']=df['High'].rolling(20).max()
        df['VOL']=(df['High']-df['Low'])/df['Close']*100
        return df
    except: return None
def multi_tf(pair, direction):
    df15=get_real_df(pair,"15m","5d")
    if df15 is None: return True
    e9=df15.iloc[-1]['EMA9']; e21=df15.iloc[-1]['EMA21']
    if direction=="CALL" and e9<e21: return False
    if direction=="PUT" and e9>e21: return False
    return True
def calc_stake():
    base=TRADE_AMOUNT; lvl=STATS["martingale_level"]
    if lvl==0: return base
    return round(base*(2.2**lvl)+random.uniform(0,0.19),2)
def binomo_trade(pair, direction, amount):
    if not BINOMO_EMAIL: return False, "ENV not set"
    delay=random.uniform(1.2,4.5); time.sleep(delay)
    try:
        from binomo_api import BinomoAPI
        api=BinomoAPI(BINOMO_EMAIL, BINOMO_PASSWORD)
        asset=f"{pair[:3]}/{pair[3:]}"
        api.set_balance_type(BINOMO_ACCOUNT_TYPE)
        api.set_asset(asset); api.set_amount(amount); api.set_duration(3)
        if direction=="CALL": api.buy()
        else: api.sell()
        return True, f"AUTO {pair} {direction} ${amount} Delay {delay:.1f}s"
    except Exception as e:
        return True, f"SIM AUTO {pair} {direction} ${amount} | {e}"
def fast_v34():
    if is_news_time(): return None, "NEWS TIME"
    best=None; best_conf=0; sess=get_session()
    if "SLOW" in sess: return None, sess
    for pair in PAIRS:
        df=get_real_df(pair)
        if df is None: continue
        last=df.iloc[-1]; prev=df.iloc[-2]
        price=float(last['Close']); rsi=float(last['RSI']); sup=float(last['SUPPORT']); res=float(last['RESISTANCE'])
        ema9=float(last['EMA9']); ema21=float(last['EMA21']); vol=float(last['VOL'])
        is_green=last['Close']>last['Open']
        is_break_res=price>res and prev['Close']>=res*0.998
        is_break_sup=price<sup and prev['Close']<=sup*1.002
        strong_bull=ema9>ema21 and is_green and vol>0.02
        strong_bear=ema9<ema21 and not is_green and vol>0.02
        direction=None; reason=""; conf=0
        if is_break_res and strong_bull and rsi>58:
            direction="CALL"; reason=f"🚀 BREAKOUT {vol:.3f}%"; conf=88+(rsi-58)*0.6+vol*10
        elif is_break_sup and strong_bear and rsi<42:
            direction="PUT"; reason=f"💥 BREAKDOWN {vol:.3f}%"; conf=88+(42-rsi)*0.6+vol*10
        else:
            is_down=df['Close'].iloc[-3]>df['Close'].iloc[-2]>df['Close'].iloc[-1]
            is_up=df['Close'].iloc[-3]<df['Close'].iloc[-2]<df['Close'].iloc[-1]
            if is_down and rsi<38 and price<=sup*1.001:
                direction="CALL"; reason="↩️ REVERSAL"; conf=75+abs(rsi-50)*0.7
            elif is_up and rsi>62 and price>=res*0.999:
                direction="PUT"; reason="↩️ REVERSAL"; conf=75+abs(rsi-50)*0.7
        if not direction: continue
        if not multi_tf(pair, direction): continue
        conf=round(min(99,conf),1)
        if conf<88: continue
        if conf>best_conf:
            best_conf=conf; best=(pair,direction,rsi,price,conf,reason,vol,sup,res)
    return best, sess

bot=telebot.TeleBot(TOKEN, threaded=False)

def background_auto_trader():
    print("🤖 Background auto started")
    while True:
        try:
            time.sleep(120)
            if not AUTO_ENABLED.get("global"): continue
            if not AUTO_CHAT_ID: continue
            if STATS["daily_profit"]>=DAILY_TARGET:
                bot.send_message(AUTO_CHAT_ID, f"🎯 TARGET HIT ${STATS['daily_profit']:.2f}"); AUTO_ENABLED["global"]=False; continue
            if STATS["daily_profit"]<=-DAILY_STOPLOSS:
                bot.send_message(AUTO_CHAT_ID, f"🛑 STOP LOSS ${STATS['daily_profit']:.2f}"); AUTO_ENABLED["global"]=False; continue
            if time.time()-STATS["last_trade"]<180: continue
            res,sess=fast_v34()
            if not res: continue
            pair,direction,rsi,price,conf,reason,vol,sup,resis=res
            stake=calc_stake()
            now=datetime.datetime.now()+datetime.timedelta(hours=1)
            msg=f"👑 BG-AUTO {pair} {conf}% {direction}\nRSI {rsi} VOL {vol:.3f}% Price {price:.5f}\nStake ${stake} Today ${STATS['daily_profit']:.2f}"
            bot.send_message(AUTO_CHAT_ID, msg)
            ok,msg2=binomo_trade(pair,direction,stake)
            bot.send_message(AUTO_CHAT_ID, f"🤖 BG EXECUTED: {msg2}")
            STATS["last_trade"]=time.time()
        except Exception as e:
            print(f"BG error {e}"); time.sleep(30)

threading.Thread(target=background_auto_trader, daemon=True).start()

@bot.message_handler(commands=['start'])
def start(m):
    global AUTO_CHAT_ID; AUTO_CHAT_ID=m.chat.id
    bot.send_message(m.chat.id, f"👑 V34 BG-AUTO READY\nBG trades every 2 mins\nTarget ${DAILY_TARGET} Stop ${DAILY_STOPLOSS}\n/auto ON to start sleep trading")
@bot.message_handler(commands=['auto'])
def auto_cmd(m):
    global AUTO_CHAT_ID
    args=m.text.split()
    if len(args)<2:
        s="ON ✅" if AUTO_ENABLED.get("global") else "OFF"; bot.send_message(m.chat.id, f"BG AUTO {s} /auto ON/OFF"); return
    if args[1].upper()=="ON":
        AUTO_ENABLED["global"]=True; AUTO_CHAT_ID=m.chat.id
        bot.send_message(m.chat.id, f"🚀 BG AUTO STARTED\nBot go scan every 2 mins\nStake ${calc_stake()} on {BINOMO_ACCOUNT_TYPE}\nTarget ${DAILY_TARGET} You fit off phone")
    else:
        AUTO_ENABLED["global"]=False; bot.send_message(m.chat.id, "🛑 BG AUTO STOPPED")
@bot.message_handler(commands=['stats'])
def stats_cmd(m):
    wr=(STATS["wins"]/(STATS["wins"]+STATS["losses"])*100) if (STATS["wins"]+STATS["losses"])>0 else 0
    bg="ON ✅" if AUTO_ENABLED.get("global") else "OFF"
    bot.send_message(m.chat.id, f"📊 V34 BG {bg}\n{STATS['wins']}W/{STATS['losses']}L {wr:.1f}%\nToday ${STATS['daily_profit']:.2f}\nNext ${calc_stake()}")

@app.route(f'/{TOKEN}', methods=['POST'])
def wh():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))]); return ''
@app.route('/')
def home():
    return f"V34 BG-AUTO {STATS['daily_profit']}",200
def set_hook():
    time.sleep(4)
    if RENDER_URL:
        try:
            requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook", timeout=10)
            requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={RENDER_URL}/{TOKEN}", timeout=10)
        except: pass
threading.Thread(target=set_hook, daemon=True).start()
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
