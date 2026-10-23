import os, time, threading, warnings
from datetime import datetime, timedelta
import pytz
from flask import Flask, request
import telebot
from telebot import types
import yfinance as yf
import pandas as pd
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# CONFIG
WAT = pytz.timezone("Africa/Lagos")
PAIRS = ["EUR/USD","GBP/USD","USD/JPY","AUD/USD","USD/CAD","EUR/JPY","EUR/GBP","GBP/JPY","USD/CHF","NZD/USD"]
YF_MAP = {"EUR/USD":"EURUSD=X","GBP/USD":"GBPUSD=X","USD/JPY":"JPY=X","AUD/USD":"AUDUSD=X","USD/CAD":"CAD=X","EUR/JPY":"EURJPY=X","EUR/GBP":"EURGBP=X","GBP/JPY":"GBPJPY=X","USD/CHF":"CHF=X","NZD/USD":"NZDUSD=X"}
STATS = {"balance":100.0,"daily":0.0,"wins":0,"loss":0,"marti":0,"last_trade":None,"signals_today":0}
AUTO_ON=False
AUTO_CHAT=None
BASE=float(os.getenv("TRADE_AMOUNT","1"))

def is_news_time():
    now=datetime.now(WAT)
    # Block high impact: 8:30-9:00, 10:00-10:30, 13:30-14:30, 15:00-15:30 WAT (covers US news)
    block = [(8,30,9,30),(10,0,10,40),(13,30,14,30),(15,0,15,40)]
    for h1,m1,h2,m2 in block:
        s=now.replace(hour=h1,minute=m1,second=0); e=now.replace(hour=h2,minute=m2,second=0)
        if s <= now <= e: return True
    # Weekend block
    if now.weekday()>=5: return True
    return False

def get_signal():
    if is_news_time(): return None, "NEWS"
    best=None; best_score=0
    for p in PAIRS:
        try:
            df=yf.download(YF_MAP[p], period="2d", interval="5m", progress=False, auto_adjust=True)
            if len(df)<50: continue
            if isinstance(df.columns, pd.MultiIndex): df.columns=df.columns.get_level_values(0)
            close=df['Close']; open_=df['Open']
            ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean()
            delta=close.diff(); gain=delta.where(delta>0,0).rolling(14).mean(); loss=-delta.where(delta<0,0).rolling(14).mean()
            rs= gain/loss; rsi=100-(100/(1+rs))
            rsi_now=float(rsi.iloc[-1]); price=float(close.iloc[-1])
            e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1])
            # 3-candle check
            last3=close.tail(3); last3_o=open_.tail(3)
            three_bull = all(last3.iloc[i] > last3_o.iloc[i] for i in range(3)) and last3.iloc[2] > last3.iloc[1] > last3.iloc[0]
            three_bear = all(last3.iloc[i] < last3_o.iloc[i] for i in range(3)) and last3.iloc[2] < last3.iloc[1] < last3.iloc[0]
            support=float(df['Low'].tail(20).min()); resist=float(df['High'].tail(20).max())
            # Scoring
            score=0; sig=None
            if price < support*1.0005 and rsi_now<32 and e9>e21 and three_bull:
                sig="CALL"; score=88 + (32-rsi_now)
            elif price > resist*0.9995 and rsi_now>68 and e9<e21 and three_bear:
                sig="PUT"; score=88 + (rsi_now-68)
            elif rsi_now<28 and three_bull and e9>e21:
                sig="CALL"; score=85
            elif rsi_now>72 and three_bear and e9<e21:
                sig="PUT"; score=85
            
            if sig and score>best_score and score>=85:
                best_score=score
                best={"pair":p,"dir":sig,"conf":min(98,score),"price":price,"rsi":rsi_now,"df":df.tail(60),"sup":support,"res":resist,"three": "3 BULL" if three_bull else "3 BEAR"}
        except: continue
    return best, None

def stake(): return round(BASE * (2.2 ** STATS['marti']),2)

@bot.message_handler(commands=['start'])
def start(m):
    mk=types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("▶️ AUTO ON 2min", callback_data="on"), types.InlineKeyboardButton("⏸️ PAUSE", callback_data="off"))
    mk.add(types.InlineKeyboardButton("📊 SIGNAL NOW", callback_data="now"), types.InlineKeyboardButton("📈 STATS", callback_data="stats"))
    bot.send_message(m.chat.id, f"V41 85% BOT\nBal ${STATS['balance']:.1f} Daily ${STATS['daily']:.1f} Win {STATS['wins']}/{STATS['wins']+STATS['loss']}\nNews Filter ON\nTP $20 SL $10", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    global AUTO_ON, AUTO_CHAT
    if c.data=="on":
        AUTO_ON=True; AUTO_CHAT=c.message.chat.id; bot.answer_callback_query(c.id,"Auto ON"); bot.send_message(c.message.chat.id,"✅ AUTO ON every 2min - 85% only")
    elif c.data=="off":
        AUTO_ON=False; bot.answer_callback_query(c.id,"Paused")
    elif c.data=="stats":
        total=STATS['wins']+STATS['loss']; wr= (STATS['wins']/total*100) if total else 0
        bot.send_message(c.message.chat.id, f"Stats: {STATS['wins']}W {STATS['loss']}L {wr:.0f}% WR\nDaily ${STATS['daily']:.2f}\nMarti Step {STATS['marti']}\nSignals Today {STATS['signals_today']}")
    elif c.data=="now" or c.data.startswith("trade_"):
        s,reason=get_signal()
        if reason=="NEWS": bot.send_message(c.message.chat.id,"🚫 NEWS TIME - Blocked 30min, avoid fake move")
        elif s: send_sig(c.message.chat.id, s)
        else: bot.send_message(c.message.chat.id,"No 85% signal now - 3-candle + RSI not aligned")
    elif c.data.startswith("win_"):
        st=float(c.data.split("_")[1]); pf=st*0.92; STATS['balance']+=pf; STATS['daily']+=pf; STATS['wins']+=1; STATS['marti']=0
        if STATS['daily']>=20: AUTO_ON=False; bot.send_message(c.message.chat.id,f"✅ WIN +${pf:.2f} 🎯 TP $20 HIT - Auto Paused")
        else: bot.send_message(c.message.chat.id,f"✅ WIN +${pf:.2f} Daily ${STATS['daily']:.2f}")
    elif c.data.startswith("loss_"):
        st=float(c.data.split("_")[1]); STATS['balance']-=st; STATS['daily']-=st; STATS['loss']+=1; STATS['marti']=min(3, STATS['marti']+1)
        if STATS['daily']<=-10: AUTO_ON=False; bot.send_message(c.message.chat.id,f"❌ LOSS -${st} 🛑 SL $10 HIT - Paused")
        else: bot.send_message(c.message.chat.id,f"❌ LOSS -${st} Next ${stake()}")

def send_sig(chat_id, d):
    st=stake()
    link=f"https://iqoption.com/en/trading?asset={d['pair'].replace('/','')}"
    cap=f"{'🤖 AUTO' if AUTO_ON else '📊'} {d['pair']} {d['dir']} {d['conf']:.0f}%\n{d['three']} | RSI {d['rsi']:.0f}\nSup {d['sup']:.5f} Res {d['res']:.5f}\nStake ${st} | Use 5m expiry"
    mk=types.InlineKeyboardMarkup(row_width=2)
    mk.add(types.InlineKeyboardButton(f"✅ WIN", callback_data=f"win_{st}"), types.InlineKeyboardButton(f"❌ LOSS", callback_data=f"loss_{st}"))
    mk.add(types.InlineKeyboardButton(f"🚀 TRADE {d['pair']} ON IQ", url=link))
    try:
        plt.figure(figsize=(7,3)); plt.plot(d['df']['Close'], color='gold'); plt.axhline(d['sup'], ls='--', c='green'); plt.axhline(d['res'], ls='--', c='red'); plt.title(f"{d['pair']} {d['dir']} {d['conf']:.0f}%"); plt.tight_layout(); p="/tmp/c.png"; plt.savefig(p); plt.close()
        bot.send_photo(chat_id, open(p,'rb'), caption=cap, reply_markup=mk)
    except: bot.send_message(chat_id, cap, reply_markup=mk)
    STATS['last_trade']=datetime.now(WAT); STATS['signals_today']+=1

def loop():
    while True:
        try:
            if AUTO_ON and AUTO_CHAT and (not STATS['last_trade'] or datetime.now(WAT)-STATS['last_trade']>=timedelta(minutes=2)):
                s,r=get_signal()
                if s: send_sig(AUTO_CHAT, s)
            time.sleep(60)
        except: time.sleep(20)
threading.Thread(target=loop, daemon=True).start()

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def wh(): bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode("utf-8"))]); return "ok"
@app.route("/")
def home():
    u=os.getenv("RENDER_EXTERNAL_URL")
    if u:
        try: requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={u}/{BOT_TOKEN}", timeout=5)
        except: pass
    return "V41 RUNNING"
app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
