# -*- coding: utf-8 -*-
# 👑 KEVIN MASTER V7.4 FINAL 10/10 - PRIVATE + GOLD DUAL API + SAFE REC 3x + AUTO COMPLETE

import os, requests, time, threading, warnings, json, random, pytz
from datetime import datetime, timedelta
import telebot
from telebot import types
from flask import Flask, request
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

warnings.filterwarnings("ignore")
BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = "@KEVINTRAILBLAZE"
ADMIN_ID = os.getenv("ADMIN_ID")
OWNER_ID = 8659453018

# 🔒 PRIVATE LOCK
ALLOWED_USERS = [OWNER_ID]
def is_private_allowed(uid):
    return uid in ALLOWED_USERS

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

USER_MODE = {}
ADMIN_CHAT_ID = None
WAT = pytz.timezone("Africa/Lagos")

def master_menu():
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(types.InlineKeyboardButton("🥇 GOLD BOT", callback_data="master_gold"), types.InlineKeyboardButton("📈 IQ OPTION BOT", callback_data="master_iq"))
    mk.add(types.InlineKeyboardButton("📚 Help / Guide", callback_data="master_help"))
    return mk

# ================= GOLD V6.1 DUAL API =================
prices_history={"GOLD":[],"GOLD_1H":[]}
last_signal_time={"GOLD":0, "GOLD_1H_TS":0}
pending_signals={}
ACTIVE_FILE="active_signals.json"
PERF_FILE="performance.json"
def save_active_gold():
    try:
        with open(ACTIVE_FILE,"w") as f: json.dump(active_signals,f)
    except: pass
def load_active_gold():
    global active_signals
    try:
        if os.path.exists(ACTIVE_FILE):
            with open(ACTIVE_FILE,"r") as f: active_signals=json.load(f)
        else: active_signals=[]
    except: active_signals=[]
def load_perf_gold():
    try:
        if os.path.exists(PERF_FILE):
            with open(PERF_FILE,"r") as f: return json.load(f)
    except: pass
    return {"wins":0,"losses":0,"jackpots":0,"total":0,"streak":0,"best_streak":0,"daily_loss":0,"last_reset":str(datetime.date.today())}
def save_perf_gold(p):
    try:
        with open(PERF_FILE,"w") as f: json.dump(p,f)
    except: pass
active_signals=[]
performance=load_perf_gold()
load_active_gold()

def is_news_block_gold():
    now=datetime.now(WAT)
    red=[(7,15,7,45),(13,15,14,0),(14,15,15,30)]
    for hs,ms,he,me in red:
        s=now.replace(hour=hs,minute=ms,second=0); e=now.replace(hour=he,minute=me,second=0)
        if s <= now <= e: return True, f"🚨 RED NEWS BLOCK {hs}:{ms:02d}-{he}:{me:02d} WAT"
    return False,"✅ No High Impact News"
def calc_atr_gold(prices, period=14):
    if len(prices)<period+1: return 10.0
    tr=[abs(prices[i]-prices[i-1]) for i in range(1,len(prices))]
    return sum(tr[-period:])/period
def get_gold():
    try:
        r=requests.get("https://api.gold-api.com/price/XAU",timeout=8).json()
        price=float(r.get("price") or r.get("xau") or 0)
        if price>1000: return price
    except: pass
    try:
        r=requests.get("https://api.metals.live/v1/spot",timeout=8).json()
        if "gold" in r: return float(r["gold"])
    except: pass
    try:
        r=requests.get("https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1m&range=1d",timeout=8,headers={"User-Agent":"Mozilla/5.0"}).json()
        price=r["chart"]["result"][0]["meta"]["regularMarketPrice"]
        if price>1000: return float(price)
    except: pass
    return None
def calc_rsi_gold(prices, period=14):
    if len(prices)<period+1: return 50.0
    gains=[]; losses=[]
    for i in range(1,len(prices)):
        diff=prices[i]-prices[i-1]
        if diff>0: gains.append(diff); losses.append(0)
        else: gains.append(0); losses.append(abs(diff))
    if len(gains)<period: return 50.0
    ag=sum(gains[-period:])/period; al=sum(losses[-period:])/period
    if al==0: return 72.0
    if ag==0: return 28.0
    rs=ag/al; return 100-(100/(1+rs))
def brain_1_smc(prices):
    if len(prices)<20: return 0,"🟡 No Structure"
    rl=min(prices[-20:-1]); rh=max(prices[-20:-1]); last=prices[-1]
    if last < rl and prices[-2] > rl: return 1,f"🟢 Sweep Low {rl:.2f} + Reclaim 💧"
    if last > rh and prices[-2] < rh: return -1,f"🔴 Sweep High {rh:.2f} + Rejection 💧"
    return 0,"⚪ No Sweep"
def brain_2_pa(prices):
    if len(prices)<3: return 0,"🟡 No PA"
    if prices[-1]>prices[-2] and prices[-2]<prices[-3]: return 1,"🟢 Bullish MSS + Engulfing"
    if prices[-1]<prices[-2] and prices[-2]>prices[-3]: return -1,"🔴 Bearish MSS + Engulfing"
    return 0,"⚪ No PA"
def brain_3_trend(p,p1h):
    if len(p1h)<10: p1h=p
    if len(p1h)<20: return 0,"🟡 No Trend"
    ema50=sum(p1h[-50:])/50 if len(p1h)>=50 else sum(p1h)/len(p1h)
    ema200=sum(p1h[-200:])/200 if len(p1h)>=200 else sum(p1h)/len(p1h)
    rsi=calc_rsi_gold(p1h)
    if ema50>ema200 and rsi>40: return 1,f"📈 Uptrend EMA50>200 RSI {rsi:.0f}"
    if ema50<ema200 and rsi<60: return -1,f"📉 Downtrend EMA50<200 RSI {rsi:.0f}"
    return 0,f"⚪ Ranging RSI {rsi:.0f}"
def brain_4_session():
    now=datetime.now(WAT); h=now.hour
    blocked,msg=is_news_block_gold()
    if blocked: return -2,msg
    if 8 <= h < 12: return 1,"🟢 London Kill Zone ACTIVE 🔥"
    elif 13 <= h < 18: return 1,"🟢 New York Kill Zone ACTIVE 🔥"
    elif 23 <= h or h < 6: return -1,"🔴 Asian Low Vol AVOID"
    else: return 0,"🟡 Midday Chop"
def brain_5_risk(bull,bear,atr,price):
    total=max(bull,bear)
    if total>=4: conf=86+random.randint(0,6)
    elif total==3: conf=78+random.randint(0,5)
    else: conf=0
    vol_msg=f"📊 Vol ATR {atr:.2f} {'⚠️ High' if atr>15 else '✅ Normal'}"
    if total>=3 and conf>=80: return min(conf,94),f"🎯 {total}/5 Agree | {vol_msg}"
    return 0,f"⚪ Low Agree {total}/5 | {vol_msg}"
def analyze_gold():
    p=prices_history.get("GOLD",[]); p1h=prices_history.get("GOLD_1H",p)
    if len(p)<5: return "NEUTRAL",0,0,0,["⏳ Collecting Data...","⏳ Wait 5 mins","⏳ Building Trend","⏳ Checking Session","⚪ Low Data"]
    b1_s,b1_m=brain_1_smc(p); b2_s,b2_m=brain_2_pa(p); b3_s,b3_m=brain_3_trend(p,p1h); b4_s,b4_m=brain_4_session()
    bull=sum(1 for x in [b1_s,b2_s,b3_s,b4_s] if x==1); bear=sum(1 for x in [b1_s,b2_s,b3_s,b4_s] if x==-1)
    atr=calc_atr_gold(p)
    if b4_s==-2: return "BLOCKED",0,0,0,[b1_m,b2_m,b3_m,b4_m,f"🚨 NEWS BLOCK"]
    if bull>bear:
        conf,rm=brain_5_risk(bull,0,atr,p[-1]); return "BUY",conf,bull,bear,[b1_m,b2_m,b3_m,b4_m,rm]
    elif bear>bull:
        conf,rm=brain_5_risk(bear,0,atr,p[-1]); return "SELL",conf,bull,bear,[b1_m,b2_m,b3_m,b4_m,rm]
    else: return "NEUTRAL",0,bull,bear,[b1_m,b2_m,b3_m,b4_m,"⚪ No Edge"]
def build_msg_gold(price,direction,conf,bull,bear,brains):
    emoji="🟢 BUY" if direction=="BUY" else "🔴 SELL"
    atr=calc_atr_gold(prices_history["GOLD"])
    sl_dist=atr*1.5; tp1_dist=atr*2.2; tp2_dist=atr*4; tp3_dist=atr*6.5
    if direction=="BUY": sl=price-sl_dist; tp1=price+tp1_dist; tp2=price+tp2_dist; tp3=price+tp3_dist
    else: sl=price+sl_dist; tp1=price-tp1_dist; tp2=price-tp2_dist; tp3=price-tp3_dist
    msg=f"""👑 KEVIN GOLD ONLY V6.1 👑
🤖 5-Brain + News + ATR
{emoji} 🥇 XAUUSD GOLD
💠 Entry: ${round(price,2)}
🛡️ SL: ${round(sl,2)} | ATR x1.5
🎯 TP1: ${round(tp1,2)} | RR 1:1.5
🎯 TP2: ${round(tp2,2)} | RR 1:2.7
🎯 TP3: ${round(tp3,2)} | RR 1:4.3
🧠 Vote: {bull} BUY vs {bear} SELL | Conf {conf}%
{brains[4]}
📚 God Analysis:
{brains[0]}
{brains[1]}
{brains[2]}
{brains[3]}
🔒 Auto: BE at TP1 + Trail
🔗 @KEVINTRAILBLAZE"""
    data={"symbol":"GOLD","action":direction,"entry":price,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"conf":conf}
    return msg,data
def request_approval_gold(price,direction,conf,bull,bear,brains):
    global ADMIN_CHAT_ID
    target=None
    if ADMIN_ID:
        try: target=int(ADMIN_ID)
        except: pass
    if not target: target=ADMIN_CHAT_ID
    msg,data=build_msg_gold(price,direction,conf,bull,bear,brains)
    if not target:
        try:
            bot.send_message(CHANNEL_ID,msg); active_signals.append({**data,"tp1_hit":False,"tp2_hit":False,"tp3_hit":False}); save_active_gold()
        except: pass
        return
    sid="GOLD_"+str(int(time.time()))
    pending_signals[sid]=data; pending_signals[sid]["_msg"]=msg
    markup=types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ SEND 🚀",callback_data="approve_"+sid),types.InlineKeyboardButton("❌ REJECT",callback_data="reject_"+sid))
    try: bot.send_message(target,f"🔔 NEW GOLD GOD SIGNAL 🤖👑\n\n{msg}\n\n🚀 Send?",reply_markup=markup)
    except: pass
def check_tp_gold(current):
    global performance
    to_remove=[]
    for sig in active_signals[:]:
        try:
            if sig["action"]=="BUY":
                if not sig.get("tp1_hit",False) and current>=sig["tp1"]: sig["tp1_hit"]=True; save_active_gold()
                if not sig.get("tp2_hit",False) and current>=sig["tp2"]: sig["tp2_hit"]=True; performance["wins"]+=1; performance["streak"]+=1; performance["best_streak"]=max(performance["best_streak"],performance["streak"]); save_perf_gold(performance)
                if not sig.get("tp3_hit",False) and current>=sig["tp3"]: performance["jackpots"]+=1; save_perf_gold(performance); to_remove.append(sig)
                if current<=sig["sl"]: performance["losses"]+=1; performance["streak"]=0; performance["daily_loss"]+=1; save_perf_gold(performance); to_remove.append(sig)
            else:
                if not sig.get("tp1_hit",False) and current<=sig["tp1"]: sig["tp1_hit"]=True; save_active_gold()
                if not sig.get("tp2_hit",False) and current<=sig["tp2"]: sig["tp2_hit"]=True; performance["wins"]+=1; performance["streak"]+=1; save_perf_gold(performance)
                if not sig.get("tp3_hit",False) and current<=sig["tp3"]: performance["jackpots"]+=1; save_perf_gold(performance); to_remove.append(sig)
                if current>=sig["sl"]: performance["losses"]+=1; performance["streak"]=0; performance["daily_loss"]+=1; save_perf_gold(performance); to_remove.append(sig)
        except: continue
    for r in to_remove:
        if r in active_signals: active_signals.remove(r)
    if to_remove: save_active_gold()
def gold_menu_kb():
    mk=types.InlineKeyboardMarkup(row_width=2)
    mk.add(types.InlineKeyboardButton("📊 Market",callback_data="gold_market"), types.InlineKeyboardButton("📈 Active",callback_data="gold_active"), types.InlineKeyboardButton("🧠 GodMode",callback_data="gold_godmode"), types.InlineKeyboardButton("🚨 News",callback_data="gold_news"), types.InlineKeyboardButton("🛡️ Risk",callback_data="gold_risk"), types.InlineKeyboardButton("🎯 Test Signal",callback_data="gold_testsignal"), types.InlineKeyboardButton("⬅️ Back to Master",callback_data="master_back"))
    return mk

# ================= IQ V54 + SAFE REC + AUTO =================
BRAND_NAME="KEVIN TRAILBLAZER"
DB_FILE="bot_db.json"
def load_db():
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE,"r") as f: return json.load(f)
    except: pass
    return {"stats":{},"daily":{},"limits":{},"pair_mem":{},"users_keys":[],"rec_count":{}}
def save_db():
    try:
        with open(DB_FILE,"w") as f: json.dump(DB,f)
    except: pass
DB=load_db()
ALLOWED_IDS=[OWNER_ID]
if DB["users_keys"]:
    for uid in DB["users_keys"]:
        if uid not in ALLOWED_IDS: ALLOWED_IDS.append(uid)
def ensure_user(uid):
    uid_s=str(uid); today=datetime.now().strftime("%Y-%m-%d")
    if uid_s not in DB["stats"]: DB["stats"][uid_s]={"total":0,"wins":0,"loss":0,"profit":0.0,"streak":0,"best_streak":0,"last_result":None}
    if uid_s not in DB["daily"]: DB["daily"][uid_s]={"date":today,"pnl":0.0,"trades":0}
    if DB["daily"][uid_s]["date"]!=today: DB["daily"][uid_s]={"date":today,"pnl":0.0,"trades":0}
    if uid_s not in DB["limits"]: DB["limits"][uid_s]={"loss":-3.0,"win":5.0}
    if uid_s not in DB["pair_mem"]: DB["pair_mem"][uid_s]={}
    if uid_s not in DB["rec_count"]: DB["rec_count"][uid_s]=0
    save_db()
def get_pair_wr(uid,pair):
    mem=DB["pair_mem"].get(str(uid),{}).get(pair)
    if not mem or mem["total"]<3: return None
    return mem["wins"]/mem["total"]*100
def update_pair_mem(uid,pair,win):
    uid_s=str(uid); ensure_user(uid)
    if pair not in DB["pair_mem"][uid_s]: DB["pair_mem"][uid_s]={"wins":0,"losses":0,"total":0}
    DB["pair_mem"][uid_s][pair]["total"]+=1
    if win: DB["pair_mem"][uid_s][pair]["wins"]+=1
    else: DB["pair_mem"][uid_s][pair]["losses"]+=1
    save_db()
def check_daily_limits(uid):
    ensure_user(uid); d=DB["daily"][str(uid)]; lim=DB["limits"][str(uid)]
    if d["pnl"]<=lim["loss"]: return False, f"🛡️💔 DAILY LOSS LIMIT HIT!\n📉 ${d['pnl']:.2f} / ${lim['loss']:.2f}\n🚫 Blocked today! 💤"
    if d["pnl"]>=lim["win"]: return False, f"🛡️💰 DAILY WIN LIMIT HIT!\n💵 ${d['pnl']:.2f} / ${lim['win']:.2f}\n🔒 Profit LOCKED! 🎉"
    return True,"OK"
def update_stats(uid,win,pnl):
    uid_s=str(uid); ensure_user(uid); s=DB["stats"][uid_s]; d=DB["daily"][uid_s]
    s["total"]+=1; d["trades"]+=1; d["pnl"]+=pnl
    if win:
        s["wins"]+=1; s["streak"]=s["streak"]+1 if s["last_result"]=="WIN" else 1; s["best_streak"]=max(s["best_streak"],s["streak"]); s["last_result"]="WIN"
        DB["rec_count"][uid_s]=0
    else:
        s["loss"]+=1; s["streak"]=0; s["last_result"]="LOSS"
        DB["rec_count"][uid_s]=DB["rec_count"].get(uid_s,0)+1 if SMART_REC.get(int(uid_s),False) else 0
    s["profit"]+=pnl; save_db(); return s["streak"]
def get_smart_lot(uid, base_amt):
    uid_s=str(uid); s=DB["stats"].get(uid_s)
    if not s or s["total"]<5: return base_amt
    wr=s["wins"]/s["total"]*100
    if wr>=70: return round(base_amt*2.0,2)
    elif wr>=60: return round(base_amt*1.5,2)
    elif wr<45: return round(base_amt*0.5,2)
    else: return base_amt

ALL_PAIRS=["EURUSD-OTC","GBPUSD-OTC","EURGBP-OTC","USDJPY-OTC","GBPJPY-OTC","AUDUSD-OTC","USDCHF-OTC","EURJPY-OTC","EURUSD","GBPUSD","EURGBP","USDJPY","GBPJPY","AUDUSD","USDCHF","EURJPY","EURCHF","GBPCHF","AUDJPY","NZDUSD","BTCUSD-OTC","ETHUSD-OTC","GOLD-OTC","SILVER-OTC"]
GOD_MODE={}; SMART_REC={}; AUTO_RUNNING={}; NEWS_FILTER={}; NEWS_PAUSED={}; MARKET_MODE={}
LAST_NEWS_CHECK=0; HIGH_IMPACT_NEWS=[]
USER_STATE={}
FAKE_WR_DISPLAY={"USDSDG-OTC":83.7,"USDMXN-OTC":83.7,"USDBDT-OTC":81.4,"USDARS-OTC":81.2,"USDTRY-OTC":80.4,"USDZAR-OTC":78.5}

def animate_progress_bar(cid, mid, pair, amount_text, brand=BRAND_NAME):
    steps=[(10,"reading candles 1m"),(20,"reading candles 1m"),(35,"reading momentum"),(50,"reading momentum + MTF 5m"),(65,"checking BB + ATR"),(80,"locking signal"),(90,"verifying edge"),(100,"SIGNAL LOCKED")]
    for pct, stage in steps:
        filled=pct//10; bar="▓"*filled+"░"*(10-filled)
        txt=f"🔍 **{brand} QUICK**\nSCANNING {pair}...\n\n{bar} {pct}%\n> {stage}\nAmount {amount_text}"
        try: bot.edit_message_text(txt,cid,mid)
        except: pass
        time.sleep(0.35)
def animate_progress_bar_eok(cid, mid, pair):
    steps=[(10,"reading candles"),(25,"reading candles"),(40,"reading momentum"),(55,"verifying edge"),(70,"checking volatility"),(85,"locking signal"),(100,"SIGNAL FOUND")]
    for pct, stage in steps:
        filled=pct//10; bar="▓"*filled+"░"*(10-filled)
        txt=f"🔍 **{BRAND_NAME}**\nSCANNING MARKET...\n\n{bar} {pct}%\n> {stage}\nPair {pair}"
        try: bot.edit_message_text(txt,cid,mid)
        except: pass
        time.sleep(0.35)

def fetch_forex_news():
    global HIGH_IMPACT_NEWS,LAST_NEWS_CHECK
    if time.time()-LAST_NEWS_CHECK<1800: return HIGH_IMPACT_NEWS
    try:
        r=requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json",timeout=10); data=r.json(); news_list=[]; now=datetime.utcnow()
        for item in data:
            if item.get('country')=='USD' and item.get('impact')=='High':
                try:
                    dt_str=item.get('date')+" "+item.get('time','00:00'); news_time=datetime.strptime(dt_str,"%Y-%m-%d %H:%M")
                    if now-timedelta(minutes=30)<=news_time<=now+timedelta(hours=2): news_list.append({"title":item.get('title'),"time":news_time})
                except: pass
        HIGH_IMPACT_NEWS=news_list; LAST_NEWS_CHECK=time.time(); return news_list
    except: return []
def is_news_time():
    news=fetch_forex_news(); now=datetime.utcnow()
    for n in news:
        diff=(n['time']-now).total_seconds()/60
        if -30<=diff<=30: return True,n
    return False,None
def check_news_before_trade(cid):
    if not NEWS_FILTER.get(cid,True): return True,"OK"
    is_news,news_item=is_news_time()
    if is_news: NEWS_PAUSED[cid]=time.time()+3600; return False,f"📰🚨 RED NEWS! {news_item['title']} Paused 60min"
    if cid in NEWS_PAUSED and time.time()<NEWS_PAUSED[cid]: rem=int((NEWS_PAUSED[cid]-time.time())/60); return False,f"⏸️ News pause {rem}min"
    return True,"OK"

IQ_LOCK=threading.Lock(); IQ_CONNECTED=False; iq=None; PAYOUT_CACHE={}; PAYOUT_TIME=0
try:
    from iqoptionapi.stable_api import IQ_Option
    EMAIL=os.getenv("IQ_EMAIL"); PWD=os.getenv("IQ_PASS")
    if EMAIL and PWD: iq=IQ_Option(EMAIL,PWD); iq.connect(); IQ_CONNECTED=iq.check_connect()
    if IQ_CONNECTED: iq.change_balance("PRACTICE")
except: pass
def iq_reconnect():
    global iq,IQ_CONNECTED
    try:
        from iqoptionapi.stable_api import IQ_Option
        iq=IQ_Option(os.getenv("IQ_EMAIL"),os.getenv("IQ_PASS")); iq.connect(); IQ_CONNECTED=iq.check_connect(); return IQ_CONNECTED
    except: return False
def get_payout(pair):
    global PAYOUT_CACHE,PAYOUT_TIME
    if time.time()-PAYOUT_TIME<60 and pair in PAYOUT_CACHE: return PAYOUT_CACHE[pair]
    try:
        with IQ_LOCK:
            all_p=iq.get_all_profit()
            if pair in all_p:
                for k in ['blitz','turbo','binary']:
                    if k in all_p[pair]: PAYOUT_CACHE[pair]=float(all_p[pair][k]); PAYOUT_TIME=time.time(); return float(all_p[pair][k])
        return 0.85
    except: return PAYOUT_CACHE.get(pair,0.85)
def get_candles(pair, timeframe=60, count=50):
    if not IQ_CONNECTED and not iq_reconnect(): return None
    for _ in range(2):
        try:
            with IQ_LOCK: c=iq.get_candles(pair,timeframe,count,time.time())
            if c and len(c)>20: return pd.DataFrame(sorted(c,key=lambda x:x['from']))
            iq_reconnect(); time.sleep(1)
        except: iq_reconnect(); time.sleep(1)
    return None
def calc_rsi(closes,period=7):
    delta=closes.diff(); gain=delta.where(delta>0,0).ewm(alpha=1/period).mean(); loss=-delta.where(delta<0,0).ewm(alpha=1/period).mean()
    rs=gain/loss; return 100-(100/(1+rs))
def calc_bollinger(closes, period=20, std=2):
    sma=closes.rolling(period).mean(); std_dev=closes.rolling(period).std()
    upper=sma+std*std_dev; lower=sma-std*std_dev
    width=(upper-lower)/sma*100
    return sma, upper, lower, width
def calc_atr(df, period=14):
    high=df['max']; low=df['min']; close=df['close']
    tr1=high-low; tr2=abs(high-close.shift()); tr3=abs(low-close.shift())
    tr=pd.concat([tr1,tr2,tr3],axis=1).max(axis=1)
    return tr.rolling(period).mean()
def analyze_momentum(pair, god_mode=False, uid=None):
    if uid:
        wr=get_pair_wr(uid,pair)
        if wr is not None and wr<40: return None
    df1=get_candles(pair, 60, 50)
    if df1 is None: return None
    df5=get_candles(pair, 300, 30)
    mtf_confirm=False; mtf_dir="NONE"
    if df5 is not None:
        close5=df5['close']; ema9_5=close5.ewm(9).mean(); ema21_5=close5.ewm(21).mean()
        if float(ema9_5.iloc[-1])>float(ema21_5.iloc[-1]): mtf_dir="CALL"
        else: mtf_dir="PUT"
    try:
        close=df1['close']; open_=df1['open']
        ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean(); rsi=calc_rsi(close,7)
        sma20, bb_up, bb_low, bb_width=calc_bollinger(close,20,2)
        atr=calc_atr(df1,14)
        rsi_now=float(rsi.iloc[-1]); e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1])
        mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100; mom3=(close.iloc[-1]-close.iloc[-4])/close.iloc[-4]*100
        is_green=float(close.iloc[-1])>float(open_.iloc[-1]); payout=get_payout(pair)
        bb_w_now=float(bb_width.iloc[-1]) if not pd.isna(bb_width.iloc[-1]) else 1.0
        atr_now=float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else 0.001
        if bb_w_now<0.15: return None
        if atr_now<close.iloc[-1]*0.0001: return None
        sig="CALL" if is_green else "PUT"; score=75; reason=""
        if mom1>0.02 and mom3>0.05 and is_green and e9>e21 and rsi_now>50 and rsi_now<78: sig="CALL"; score=88; reason=f"🚀 Bull {mom1:.3f}%"
        elif mom1<-0.02 and mom3<-0.05 and not is_green and e9<e21 and rsi_now<50: sig="PUT"; score=88; reason=f"📉 Bear {mom1:.3f}%"
        elif e9>e21 and is_green: sig="CALL"; score=80; reason=f"📈 EMA Bull"
        elif e9<e21 and not is_green: sig="PUT"; score=80; reason=f"📉 EMA Bear"
        if mtf_dir!="NONE":
            if sig==mtf_dir: score+=8; reason+=f" ✅ MTF {mtf_dir} 5m"; mtf_confirm=True
            else:
                score-=12; reason+=f" ⚠️ MTF Conflict 5m={mtf_dir}"
                if god_mode: return None
        if float(close.iloc[-1])>float(bb_up.iloc[-1]): reason+=" 🔝 BB Upper"
        elif float(close.iloc[-1])<float(bb_low.iloc[-1]): reason+=" 🔻 BB Lower"
        if uid:
            wr=get_pair_wr(uid,pair)
            if wr and wr>=65: score+=5; reason+=f" ⭐ Fav {wr:.0f}%"
        if god_mode:
            if score<88 or payout<0.85: return None
            if abs(mom3)<0.08: return None
            if not mtf_confirm and mtf_dir!="NONE": return None
            score=min(98,score+5); reason+=" 👑 GOD"
        return {"pair":pair,"dir":sig,"conf":min(98,score),"price":float(close.iloc[-1]),"rsi":rsi_now,"reason":reason,"mom":mom3,"payout":payout,"df":df1.tail(30),"mtf":mtf_dir,"bb_width":bb_w_now,"atr":atr_now}
    except Exception as e:
        print(f"Analyze error {pair}: {e}"); return None

def backtest_pair(pair, uid=None):
    df=get_candles(pair, 60, 120)
    if df is None or len(df)<50: return None
    wins=0; total=0
    for i in range(20, len(df)-5):
        try:
            slice_df=df.iloc[i-20:i]
            close=slice_df['close']; open_=slice_df['open']
            ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean(); rsi=calc_rsi(close,7)
            e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1]); rsi_now=float(rsi.iloc[-1])
            is_green=float(close.iloc[-1])>float(open_.iloc[-1])
            sig=None
            if e9>e21 and is_green and rsi_now>50 and rsi_now<78: sig="CALL"
            elif e9<e21 and not is_green and rsi_now<50: sig="PUT"
            if sig:
                future_close=df.iloc[i+1]['close']; entry=close.iloc[-1]
                if sig=="CALL" and future_close>entry: wins+=1
                elif sig=="PUT" and future_close<entry: wins+=1
                total+=1
        except: pass
    if total==0: return None
    return {"wins":wins,"total":total,"wr":wins/total*100}

def iq_trade(pair,direction,amount,bal,expiry=30):
    try:
        with IQ_LOCK:
            iq.change_balance(bal)
            try: _,oid=iq.buy_blitz(pair,amount,direction.lower(),expiry); return True,oid,expiry
            except: _,oid=iq.buy(amount,pair,direction.lower(),1); return True,oid,60
    except: return False,None,0

# ===== AUTO LOOP COMPLETE =====
def auto_trading_loop(cid, bal, base_amt):
    bot.send_message(cid, f"🤖 AUTO STARTED 🟢\nBalance {bal} Base ${base_amt}\nGOD {'✅' if GOD_MODE.get(cid,False) else '❌'} REC {'✅' if SMART_REC.get(cid,False) else '❌'} NEWS {'✅' if NEWS_FILTER.get(cid,True) else '❌'}\nScanning every 45s...\n\n[⏸️ STOP to pause]")
    scan_index = 0
    while AUTO_RUNNING.get(cid, False):
        try:
            if DB["rec_count"].get(str(cid),0) >= 3:
                bot.send_message(cid, "🛡️ AUTO REC STOPPED 3/3 🛑\n🔒 Protection - Auto Paused\nPress AUTO again to resume")
                AUTO_RUNNING[cid]=False
                break
            ok_lim,msg_lim = check_daily_limits(cid)
            if not ok_lim:
                bot.send_message(cid, msg_lim)
                AUTO_RUNNING[cid]=False
                break
            can_trade,msg = check_news_before_trade(cid)
            if not can_trade:
                time.sleep(30)
                continue
            mode = MARKET_MODE.get(cid,"ALL")
            if mode == "OTC":
                pairs = [p for p in ALL_PAIRS if "OTC" in p]
            elif mode == "REAL":
                pairs = [p for p in ALL_PAIRS if "OTC" not in p]
            else:
                pairs = ALL_PAIRS
            pair = pairs[scan_index % len(pairs)]
            scan_index+=1
            d = analyze_momentum(pair, god_mode=GOD_MODE.get(cid,False), uid=cid)
            if not d:
                time.sleep(5)
                continue
            # amount calc with SAFE REC
            amt = get_smart_lot(cid, base_amt)
            if SMART_REC.get(cid,False) and DB["stats"][str(cid)]["last_result"]=="LOSS":
                rec_c = DB["rec_count"].get(str(cid),0)
                if rec_c < 3:
                    amt = round(amt*2.2,2)
                    bot.send_message(cid, f"🧠 AUTO REC {rec_c+1}/3 2.2x → ${amt} on {pair}")
            ok,oid,exp = iq_trade(pair, d['dir'], amt, bal, 30)
            if not ok:
                time.sleep(10)
                continue
            bot.send_message(cid, f"🤖 AUTO PLACED\n{pair} {d['dir']} ${amt} {d['conf']:.0f}% {d['reason']}\nID {oid}")
            time.sleep(exp+5)
            with IQ_LOCK: pnl = iq.check_win_v4(oid)
            if pnl > 0:
                streak = update_stats(cid, True, pnl)
                update_pair_mem(cid, pair, True)
                bot.send_message(cid, f"✅💚 AUTO WIN +${pnl:.2f} {pair} Streak {streak} REC 0/3 ✅")
            else:
                update_stats(cid, False, -amt)
                update_pair_mem(cid, pair, False)
                bot.send_message(cid, f"❌ AUTO LOSS -${amt:.2f} {pair} REC {DB['rec_count'].get(str(cid),0)}/3")
            time.sleep(15)
        except Exception as e:
            print("Auto error", e)
            time.sleep(10)
    bot.send_message(cid, "⏸️ AUTO STOPPED", reply_markup=main_menu_iq(cid))

def main_menu_iq(cid):
    god=GOD_MODE.get(cid,False); rec=SMART_REC.get(cid,False); news=NEWS_FILTER.get(cid,True); mode=MARKET_MODE.get(cid,"ALL")
    ensure_user(cid); s=DB["stats"][str(cid)]; d=DB["daily"][str(cid)]
    mk=types.InlineKeyboardMarkup(row_width=2)
    mk.add(types.InlineKeyboardButton(f"⚡ New Opportunity - {BRAND_NAME}",callback_data="new_op"))
    mk.add(types.InlineKeyboardButton("🚀 QUICK",callback_data="quick"), types.InlineKeyboardButton("🤖 AUTO",callback_data="auto"), types.InlineKeyboardButton(f"👑 GOD {'✅' if god else '❌'}",callback_data="god"), types.InlineKeyboardButton(f"🧠 REC {'✅' if rec else '❌'}",callback_data="recovery"), types.InlineKeyboardButton(f"📰 NEWS {'✅' if news else '❌'}",callback_data="news"), types.InlineKeyboardButton(f"💱 {mode}",callback_data="market"), types.InlineKeyboardButton(f"📊 ${d['pnl']:.1f}",callback_data="pnl"), types.InlineKeyboardButton(f"🔥 {s['streak']}",callback_data="mystats"), types.InlineKeyboardButton("🏆 TOP",callback_data="top"), types.InlineKeyboardButton("📈 BACKTEST",callback_data="backtest_menu"), types.InlineKeyboardButton("🎯 MEM",callback_data="pair_mem"), types.InlineKeyboardButton("⏸️ STOP",callback_data="stop_auto"), types.InlineKeyboardButton("⬅️ Back to Master",callback_data="master_back"))
    return mk
def trade_type_kb():
    mk=types.InlineKeyboardMarkup(row_width=2)
    mk.add(types.InlineKeyboardButton("Trade Live 🔴",callback_data="type_REAL"),types.InlineKeyboardButton("Trade Demo 🟢",callback_data="type_PRACTICE"))
    return mk
def amount_kb():
    mk=types.InlineKeyboardMarkup(row_width=3)
    mk.add(types.InlineKeyboardButton("N1,000",callback_data="eok_amt_1000"),types.InlineKeyboardButton("N2,000",callback_data="eok_amt_2000"),types.InlineKeyboardButton("N3,000",callback_data="eok_amt_3000"))
    mk.add(types.InlineKeyboardButton("N5,000",callback_data="eok_amt_5000"),types.InlineKeyboardButton("✏️ Custom",callback_data="eok_amt_custom"),types.InlineKeyboardButton("❌ Cancel",callback_data="cancel"))
    return mk
def expiry_kb():
    mk=types.InlineKeyboardMarkup(row_width=3)
    mk.add(types.InlineKeyboardButton("30s",callback_data="eok_exp_30"),types.InlineKeyboardButton("1m",callback_data="eok_exp_60"),types.InlineKeyboardButton("5m",callback_data="eok_exp_300"))
    return mk
def eok_pairs_kb():
    mk=types.InlineKeyboardMarkup(row_width=1)
    for p,wr in sorted(FAKE_WR_DISPLAY.items(), key=lambda x:x[1], reverse=True):
        mk.add(types.InlineKeyboardButton(f"{p} - Win rate {wr}%",callback_data=f"eok_pair_{p}"))
    mk.add(types.InlineKeyboardButton("🔄 More Pairs (V54)",callback_data="quick"))
    return mk

@app.route('/')
def home(): return f"👑 MASTER V7.4 FINAL PRIVATE AUTO LIVE GOLD {len(active_signals)} IQ {'🟢' if IQ_CONNECTED else '🔴'}"
@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    try:
        json_str=request.get_data().decode('UTF-8'); update=telebot.types.Update.de_json(json_str); bot.process_new_updates([update])
    except: pass
    return "OK",200
@app.route('/setwebhook')
def set_webhook():
    try:
        bot.remove_webhook(); time.sleep(1)
        ext_url=os.getenv("RENDER_EXTERNAL_URL")
        if ext_url:
            url=f"{ext_url}/{BOT_TOKEN}"; bot.set_webhook(url=url); return f"✅ Webhook set {url}"
        return "❌ No URL"
    except Exception as e: return f"⚠️ {e}"

def signal_loop():
    while True:
        try:
            today=str(datetime.date.today())
            if performance.get("last_reset")!=today: performance["daily_loss"]=0; performance["last_reset"]=today; save_perf_gold(performance)
            if performance.get("daily_loss",0)>=3: time.sleep(300); continue
            price=get_gold()
            if price is None: time.sleep(60); continue
            prices_history["GOLD"].append(price)
            if len(prices_history["GOLD"])>250: prices_history["GOLD"].pop(0)
            if int(time.time()) // 3600 != int(last_signal_time.get("GOLD_1H_TS",0)) // 3600:
                prices_history["GOLD_1H"].append(price)
                if len(prices_history["GOLD_1H"])>250: prices_history["GOLD_1H"].pop(0)
                last_signal_time["GOLD_1H_TS"]=time.time()
            check_tp_gold(price)
            direction,conf,bull,bear,brains=analyze_gold()
            if conf>=82 and len(active_signals)==0:
                if time.time()-last_signal_time.get("GOLD",0)>3600:
                    request_approval_gold(price,direction,conf,bull,bear,brains); last_signal_time["GOLD"]=time.time()
        except Exception as e: print("GOLD loop",e,flush=True)
        time.sleep(60)

@bot.message_handler(commands=['start'])
def handle_start(message):
    if not is_private_allowed(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Private Bot 🔒\nAccess Denied. Owner only.")
        return
    global ADMIN_CHAT_ID
    if message.chat.type=="private": ADMIN_CHAT_ID=message.chat.id
    USER_MODE[message.chat.id]=None
    ensure_user(message.from_user.id)
    NEWS_FILTER.setdefault(message.chat.id,True); MARKET_MODE.setdefault(message.chat.id,"ALL")
    s=DB["stats"][str(message.from_user.id)]; d=DB["daily"][str(message.from_user.id)]
    base=1.0; smart=get_smart_lot(message.from_user.id, base)
    txt=f"""🤖✨ **{BRAND_NAME} MASTER V7.4 FINAL PRIVATE AUTO** 💎🔥
━━━━━━━━━━━━━━━
👑 Owner {OWNER_ID} | 📡 IQ {'🟢' if IQ_CONNECTED else '🔴'} | 🥇 GOLD DUAL API
━━━━━━━━━━━━━━━
💰 Today: ${d['pnl']:.2f} ({d['trades']}) | 🔥 Streak {s['streak']} Best {s['best_streak']}
📈 All Time: {s['wins']}W/{s['loss']}L WR {(s['wins']/s['total']*100) if s['total'] else 0:.1f}% Profit ${s['profit']:.2f}
💡 Smart Lot: ${base} → ${smart}
🧠 REC Count: {DB['rec_count'].get(str(message.from_user.id),0)}/3
━━━━━━━━━━━━━━━
👇 **PICK YOUR BOT BELOW**
━━━━━━━━━━━━━━━
"""
    bot.send_message(message.chat.id,txt,reply_markup=master_menu())

@bot.message_handler(commands=['help'])
def handle_help(message):
    if not is_private_allowed(message.from_user.id): return
    bot.send_message(message.chat.id, """👑 KEVIN MASTER V7.4 FINAL GUIDE 📚
GOLD: 5-Brain DUAL API + News block 82%+
IQ: QUICK + New Opportunity + LIVE BAR + SAFE REC 3x + BACKTEST + MEM + AUTO COMPLETE
AUTO: Scans ALL_PAIRS every 45s, GOD filter, SAFE REC 2.2x max 3, NEWS pause, DAILY LIMIT.
Type /start to begin.""")

@bot.callback_query_handler(func=lambda c: True)
def handle_all(c):
    if not is_private_allowed(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Private Bot")
        return
    cid=c.message.chat.id; data=c.data; ensure_user(cid)
    if cid not in USER_STATE: USER_STATE[cid]={}
    if data=="master_help": handle_help(c.message); bot.answer_callback_query(c.id,"Help"); return
    if data=="master_gold":
        USER_MODE[cid]="GOLD"; g=get_gold() or 0
        bot.send_message(cid,f"🥇 GOLD MODE V7.4 DUAL API 👑\nGOLD ${round(g,2)} OPEN ✅\nActive {len(active_signals)} Wins {performance['wins']}",reply_markup=gold_menu_kb())
        bot.answer_callback_query(c.id,"GOLD Mode"); return
    if data=="master_iq":
        USER_MODE[cid]="IQ"
        s=DB["stats"][str(cid)]; d=DB["daily"][str(cid)]
        bot.send_message(cid,f"📈 IQ MODE V7.4 FINAL ACTIVATED 👑\n💰 Today ${d['pnl']:.2f} Streak {s['streak']} REC {DB['rec_count'].get(str(cid),0)}/3\n\n👇 Choose:",reply_markup=main_menu_iq(cid))
        bot.answer_callback_query(c.id,"IQ Mode"); return
    if data=="master_back":
        USER_MODE[cid]=None; bot.send_message(cid,"👑 MASTER MENU\nChoose bot:",reply_markup=master_menu()); bot.answer_callback_query(c.id,"Back"); return
    if data.startswith("approve_") or data.startswith("reject_"):
        try:
            if data.startswith("approve_"):
                sid=data.replace("approve_",""); sd=pending_signals.pop(sid,None)
                if not sd: bot.answer_callback_query(c.id,"Done"); return
                msg=sd.get("_msg"); bot.send_message(CHANNEL_ID,msg); active_signals.append({**sd,"tp1_hit":False,"tp2_hit":False,"tp3_hit":False}); save_active_gold()
                bot.answer_callback_query(c.id,"✅ Sent!"); bot.edit_message_text(f"✅ SENT 🚀\n\n{msg}",c.message.chat.id,c.message.message_id)
            else:
                pending_signals.pop(data.replace("reject_",""),None); bot.answer_callback_query(c.id,"❌ Rejected"); bot.edit_message_text("❌ Rejected",c.message.chat.id,c.message.message_id)
        except: pass
        return
    if data in ["gold_market","gold_active","gold_godmode","gold_news","gold_risk","gold_testsignal"]:
        if data=="gold_market":
            g=get_gold(); atr=calc_atr_gold(prices_history['GOLD']); blocked,news_msg=is_news_block_gold(); txt=f"${round(g,2)}" if g else "API Error"
            bot.send_message(cid,f"📊 GOLD {txt} ATR {atr:.1f}\n{news_msg}\nActive {len(active_signals)} DUAL API ✅",reply_markup=gold_menu_kb())
        elif data=="gold_active":
            if len(active_signals)==0: bot.send_message(cid,f"📭 No active GOLD signals\nWins {performance['wins']} Loss {performance['losses']}",reply_markup=gold_menu_kb())
            else:
                t=f"📊 ACTIVE {len(active_signals)}\n"; 
                for s in active_signals: t+=f"{s['symbol']} {s['action']} ${round(s['entry'],2)}\n"
                bot.send_message(cid,t,reply_markup=gold_menu_kb())
        elif data=="gold_godmode": bot.send_message(cid,"🧠 GOLD V7.4 DUAL API + 7 Layers\n1 SMC 2 PA 3 Trend 4 KillZone+News 5 ATR 6 Risk 7 Protection\n82%+ only",reply_markup=gold_menu_kb())
        elif data=="gold_news": blocked,msg=is_news_block_gold(); bot.send_message(cid,f"🚨 {msg}",reply_markup=gold_menu_kb())
        elif data=="gold_risk": bot.send_message(cid,f"🛡️ Risk: 1% per trade, Daily {performance.get('daily_loss',0)}/3\nBE at TP1",reply_markup=gold_menu_kb())
        elif data=="gold_testsignal": g=get_gold() or 2650.0; request_approval_gold(g,"BUY",90,4,0,["🟢 Sweep Low","🟢 Bullish MSS","📈 Uptrend","🟢 London ACTIVE","🎯 4/5"]); bot.send_message(cid,"✅ Test signal sent",reply_markup=gold_menu_kb())
        return
    if data=="new_op": bot.send_message(cid,f"👇 **Trade Live | Trade Demo - {BRAND_NAME}**",reply_markup=trade_type_kb()); return
    if data.startswith("type_"):
        bal=data.split("_")[1]; USER_STATE[cid]['balance']=bal
        bot.send_message(cid,f"✅ {bal} Selected\n\n💰 **Enter amount:**",reply_markup=amount_kb()); return
    if data.startswith("eok_amt_"):
        if data=="eok_amt_custom": bot.send_message(cid,"✏️ Enter custom amount (e.g. 29800):"); USER_STATE[cid]['awaiting_amount']=True; return
        if data=="cancel": bot.send_message(cid,"❌ Cancelled",reply_markup=main_menu_iq(cid)); return
        amt=int(data.split("_")[2]); USER_STATE[cid]['amount']=amt; USER_STATE[cid]['awaiting_amount']=False
        bot.send_message(cid,f"✅ Amount N{amt:,}\n\n⏱️ **Pick expiry**",reply_markup=expiry_kb()); return
    if data.startswith("eok_exp_"):
        exp=int(data.split("_")[2]); USER_STATE[cid]['expiry']=exp
        txt=f"📊 **{BRAND_NAME} - Highest chance to win now**\n"
        for p,wr in sorted(FAKE_WR_DISPLAY.items(), key=lambda x:x[1], reverse=True): txt+=f"● {p} - Win rate {wr}%\n"
        txt+="\n👇 **Make your choice below**"
        bot.send_message(cid,txt,reply_markup=eok_pairs_kb()); return
    if data.startswith("eok_pair_"):
        pair=data.replace("eok_pair_",""); USER_STATE[cid]['pair']=pair
        amt=USER_STATE[cid].get('amount',5000); exp=USER_STATE[cid].get('expiry',30); bal=USER_STATE[cid].get('balance','PRACTICE')
        ok_lim,msg_lim=check_daily_limits(cid)
        if not ok_lim: bot.send_message(cid,msg_lim,reply_markup=main_menu_iq(cid)); return
        if DB["rec_count"].get(str(cid),0)>=3:
            bot.send_message(cid,"🛡️ REC STOPPED! 3 losses max reached today. Reset tomorrow or /start\n🔒 Protection to avoid blow",reply_markup=main_menu_iq(cid)); return
        can_trade,msg=check_news_before_trade(cid)
        if not can_trade: bot.send_message(cid,msg,reply_markup=main_menu_iq(cid)); return
        msg_scan=bot.send_message(cid,f"🔍 **{BRAND_NAME}**\nSCANNING MARKET...\n\n░░░░░░░░░░ 0% starting")
        animate_progress_bar_eok(cid, msg_scan.message_id, pair)
        d=analyze_momentum(pair,god_mode=GOD_MODE.get(cid,False),uid=cid)
        if not d: bot.send_message(cid,"❌ No signal",reply_markup=eok_pairs_kb()); return
        bot.send_message(cid,f"🔒 {BRAND_NAME} 🔒\nSIGNAL FOUND\nPairs: {pair}\nAction: {d['dir']}\nAmount: N{amt:,}.00\nExpiry: {exp}s\nConf: {d['conf']:.0f}%")
        ngn_to_usd=amt/1600.0
        if SMART_REC.get(cid,False) and DB["stats"][str(cid)]["last_result"]=="LOSS":
            rec_c=DB["rec_count"].get(str(cid),0)
            if rec_c<3:
                ngn_to_usd=round(ngn_to_usd*2.2,2); bot.send_message(cid,f"🧠 REC ACTIVE {rec_c+1}/3 2.2x → N{int(ngn_to_usd*1600):,}")
        ok,oid,exp_real=iq_trade(pair,d['dir'],ngn_to_usd,bal,expiry=exp)
        if not ok: bot.send_message(cid,"❌ Trade Failed",reply_markup=main_menu_iq(cid)); return
        bot.send_message(cid,f"✅ Placed {oid} {exp_real}s"); time.sleep(exp_real+5)
        try:
            with IQ_LOCK: pnl=iq.check_win_v4(oid)
            if pnl>0:
                streak=update_stats(cid,True,pnl); update_pair_mem(cid,pair,True); profit_ngn=int(pnl*1600)
                bot.send_message(cid,f"🔥 **{BRAND_NAME}**\nRESULT: ✅ WIN\nPayout: +N{profit_ngn:,}.00\nStreak {streak} REC reset 0/3 ✅",reply_markup=main_menu_iq(cid))
            else:
                update_stats(cid,False,-ngn_to_usd); update_pair_mem(cid,pair,False)
                bot.send_message(cid,f"🔥 **{BRAND_NAME}**\nRESULT: ❌ LOSS\nLoss: -N{amt:,}.00 REC {DB['rec_count'].get(str(cid),0)}/3",reply_markup=main_menu_iq(cid))
        except: bot.send_message(cid,"Check IQ manually",reply_markup=main_menu_iq(cid))
        return
    if data=="backtest_menu":
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in ALL_PAIRS[:8]: mk.add(types.InlineKeyboardButton(f"📈 {p}",callback_data=f"bt_{p}"))
        bot.send_message(cid,"📈 **BACKTEST MENU**",reply_markup=mk); return
    if data.startswith("bt_"):
        pair=data.replace("bt_",""); bot.send_message(cid,f"🔍 Backtesting {pair}..."); res=backtest_pair(pair)
        if not res: bot.send_message(cid,"❌ Failed"); return
        emoji="⭐💎 BEST" if res['wr']>=65 else "⚠️🚫 AVOID" if res['wr']<50 else "📊 OK"
        bot.send_message(cid,f"📈 {pair} Backtest: {res['wins']}/{res['total']} WR {res['wr']:.1f}% {emoji}",reply_markup=main_menu_iq(cid)); return
    if data=="quick":
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in ALL_PAIRS[:12]:
            wr=get_pair_wr(cid,p); label=p; 
            if wr: label+=f" {wr:.0f}%"
            mk.add(types.InlineKeyboardButton(label,callback_data=f"pair_{p}"))
        bot.send_message(cid,f"💹 QUICK TRADE V7.4 - {BRAND_NAME}",reply_markup=mk); return
    if data.startswith("pair_"):
        pair=data.replace("pair_",""); mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("🟢 DEMO",callback_data=f"bal_PRACTICE_{pair}"),types.InlineKeyboardButton("🔴 REAL",callback_data=f"bal_REAL_{pair}"))
        bot.send_message(cid,f"{pair} ACCOUNT?",reply_markup=mk); return
    if data.startswith("bal_") and not data.startswith("auto_bal_"):
        parts=data.split("_",2); bal=parts[1]; pair=parts[2]
        base=1.0; smart=get_smart_lot(cid, base)
        mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("N1,000",callback_data=f"qn_1000_{pair}_{bal}"),types.InlineKeyboardButton("N2,000",callback_data=f"qn_2000_{pair}_{bal}"),types.InlineKeyboardButton("N3,000",callback_data=f"qn_3000_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("N5,000",callback_data=f"qn_5000_{pair}_{bal}"),types.InlineKeyboardButton("✏️ Custom",callback_data=f"qn_custom_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton(f"💵 $1 → ${smart}",callback_data=f"amt_{smart}_{pair}_{bal}"),types.InlineKeyboardButton("💵 $5",callback_data=f"amt_5_{pair}_{bal}"),types.InlineKeyboardButton("💵 $10",callback_data=f"amt_10_{pair}_{bal}"))
        bot.send_message(cid,f"✅ {pair} {bal}\n💰 Naira + USD\n💡 Smart Lot ${smart}",reply_markup=mk); return
    if data.startswith("qn_"):
        parts=data.split("_")
        if parts[1]=="custom":
            _,_,pair,bal = data.split("_",3)
            USER_STATE[cid]['awaiting_qn']=True; USER_STATE[cid]['qn_pair']=pair; USER_STATE[cid]['qn_bal']=bal
            bot.send_message(cid,"✏️ Enter custom Naira amount e.g. 29800"); return
        amt_n=int(parts[1]); pair=parts[2]; bal=parts[3]; amt_usd=amt_n/1600.0
        if DB["rec_count"].get(str(cid),0)>=3: bot.send_message(cid,"🛡️ REC limit 3 reached, blocked"); return
        if SMART_REC.get(cid,False) and DB["stats"][str(cid)]["last_result"]=="LOSS" and DB["rec_count"].get(str(cid),0)<3:
            amt_usd=round(amt_usd*2.2,2); bot.send_message(cid,f"🧠 REC ACTIVE {DB['rec_count'].get(str(cid),0)+1}/3 2.2x → N{int(amt_usd*1600):,}")
        ok_lim,msg_lim=check_daily_limits(cid)
        if not ok_lim: bot.send_message(cid,msg_lim); return
        can_trade,msg=check_news_before_trade(cid)
        if not can_trade: bot.send_message(cid,msg); return
        msg_scan=bot.send_message(cid,f"🔍 **{BRAND_NAME} QUICK**\nSCANNING {pair}...\n\n░░░░░░░░░░ 0% starting\nAmount N{amt_n:,}")
        animate_progress_bar(cid, msg_scan.message_id, pair, f"N{amt_n:,}")
        d=analyze_momentum(pair,god_mode=GOD_MODE.get(cid,False),uid=cid)
        if not d: bot.send_message(cid,"❌ No signal"); return
        ok,oid,exp=iq_trade(pair,d['dir'],amt_usd,bal,30)
        if not ok: bot.send_message(cid,"❌ Trade Failed"); return
        bot.send_message(cid,f"✅ Placed {oid} {exp}s - N{amt_n:,}"); time.sleep(exp+5)
        try:
            with IQ_LOCK: pnl=iq.check_win_v4(oid)
            if pnl>0:
                streak=update_stats(cid,True,pnl); update_pair_mem(cid,pair,True)
                bot.send_message(cid,f"✅💚 WIN!!! +N{int(pnl*1600):,} Streak {streak} REC reset 0/3 ✅",reply_markup=main_menu_iq(cid))
            else:
                update_stats(cid,False,-amt_usd); update_pair_mem(cid,pair,False)
                bot.send_message(cid,f"❌ LOSS -N{amt_n:,} REC {DB['rec_count'].get(str(cid),0)}/3",reply_markup=main_menu_iq(cid))
        except: bot.send_message(cid,"Check IQ")
        return
    if data.startswith("amt_") and not data.startswith("auto_amt_") and not data.startswith("eok_amt_"):
        parts=data.split("_"); amt=float(parts[1]); pair=parts[2]; bal=parts[3]
        if DB["rec_count"].get(str(cid),0)>=3: bot.send_message(cid,"🛡️ REC limit 3 reached, blocked"); return
        ok_lim,msg_lim=check_daily_limits(cid)
        if not ok_lim: bot.send_message(cid,msg_lim); return
        msg_scan=bot.send_message(cid,f"🔍 **{BRAND_NAME} QUICK**\nSCANNING {pair}...\n\n░░░░░░░░░░ 0% starting\nAmount ${amt}")
        animate_progress_bar(cid, msg_scan.message_id, pair, f"${amt}")
        d=analyze_momentum(pair,god_mode=GOD_MODE.get(cid,False),uid=cid)
        if not d: bot.send_message(cid,"❌ No signal"); return
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal,30)
        if not ok: bot.send_message(cid,"❌ Trade Failed"); return
        bot.send_message(cid,f"✅ Placed {oid} {exp}s"); time.sleep(exp+5)
        try:
            with IQ_LOCK: pnl=iq.check_win_v4(oid)
            if pnl>0:
                streak=update_stats(cid,True,pnl); update_pair_mem(cid,pair,True)
                bot.send_message(cid,f"✅💚 WIN!!! +${pnl:.2f} Streak {streak} REC 0/3 ✅",reply_markup=main_menu_iq(cid))
            else:
                update_stats(cid,False,-amt); update_pair_mem(cid,pair,False)
                bot.send_message(cid,f"❌ LOSS -${amt:.2f} REC {DB['rec_count'].get(str(cid),0)}/3",reply_markup=main_menu_iq(cid))
        except: bot.send_message(cid,"Check IQ")
        return
    if data=="god": GOD_MODE[cid]=not GOD_MODE.get(cid,False); bot.send_message(cid,f"👑 GOD MODE {'✅ ON' if GOD_MODE[cid] else '❌ OFF'}",reply_markup=main_menu_iq(cid)); return
    if data=="recovery": SMART_REC[cid]=not SMART_REC.get(cid,False); bot.send_message(cid,f"🧠 REC SAFE MODE {'✅ ON (Max 3x)' if SMART_REC[cid] else '❌ OFF'} 2.2x",reply_markup=main_menu_iq(cid)); return
    if data=="news": NEWS_FILTER[cid]=not NEWS_FILTER.get(cid,True); bot.send_message(cid,f"📰 NEWS FILTER {'✅ ON' if NEWS_FILTER[cid] else '❌ OFF'}",reply_markup=main_menu_iq(cid)); return
    if data=="market":
        cur=MARKET_MODE.get(cid,"ALL"); nxt={"ALL":"OTC","OTC":"REAL","REAL":"ALL"}[cur]; MARKET_MODE[cid]=nxt
        bot.send_message(cid,f"💱 MARKET MODE → {nxt}",reply_markup=main_menu_iq(cid)); return
    if data=="stop_auto": AUTO_RUNNING[cid]=False; bot.send_message(cid,"⏸️ Stopped - AUTO OFF",reply_markup=main_menu_iq(cid)); return
    if data=="mystats" or data=="pnl" or data=="top":
        s=DB["stats"][str(cid)]; d=DB["daily"][str(cid)]; bot.send_message(cid,f"📊 Today ${d['pnl']:.2f} ({d['trades']}) Streak {s['streak']} Best {s['best_streak']} 🔥\nW {s['wins']} L {s['loss']} Profit ${s['profit']:.2f} REC {DB['rec_count'].get(str(cid),0)}/3",reply_markup=main_menu_iq(cid)); return
    if data=="pair_mem":
        pm=DB["pair_mem"].get(str(cid),{})
        if not pm: bot.send_message(cid,"📭 No pair data yet"); return
        txt=f"🎯 {BRAND_NAME} PAIR MEMORY\n━━━━━━━━━━━━━━━\n"; 
        for p,dat in sorted(pm.items(),key=lambda x:(x[1]['wins']/x[1]['total'] if x[1]['total'] else 0),reverse=True):
            wrp=dat["wins"]/dat["total"]*100 if dat["total"] else 0; txt+=f"{p}: {wrp:.0f}% {dat['wins']}/{dat['total']}\n"
        bot.send_message(cid,txt,reply_markup=main_menu_iq(cid)); return
    if data=="auto":
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🟢 DEMO $1",callback_data="auto_bal_PRACTICE_1"),types.InlineKeyboardButton("🔴 REAL $1",callback_data="auto_bal_REAL_1"))
        mk.add(types.InlineKeyboardButton("🟢 DEMO $5",callback_data="auto_bal_PRACTICE_5"),types.InlineKeyboardButton("🔴 REAL $5",callback_data="auto_bal_REAL_5"))
        mk.add(types.InlineKeyboardButton("⬅️ Back",callback_data="master_iq"))
        bot.send_message(cid,"🤖 AUTO MODE - Pick balance & base amount\nSAFE REC 2.2x Max 3 + GOD filter + NEWS",reply_markup=mk); return
    if data.startswith("auto_bal_"):
        parts=data.split("_"); bal=parts[2]; amt=float(parts[3])
        if AUTO_RUNNING.get(cid,False):
            bot.send_message(cid,"⚠️ AUTO already running! Press STOP first",reply_markup=main_menu_iq(cid)); return
        AUTO_RUNNING[cid]=True
        threading.Thread(target=auto_trading_loop, args=(cid, bal, amt), daemon=True).start()
        bot.answer_callback_query(c.id, f"AUTO {bal} ${amt} Started")
        return

@bot.message_handler(func=lambda m: True)
def custom_handler(m):
    if not is_private_allowed(m.from_user.id): return
    cid=m.chat.id
    if cid in USER_STATE and USER_STATE[cid].get('awaiting_amount'):
        try:
            amt=int(m.text.strip().replace(",","").replace("N",""))
            if amt<100: bot.send_message(cid,"❌ Min N100"); return
            USER_STATE[cid]['amount']=amt; USER_STATE[cid]['awaiting_amount']=False
            mk=types.InlineKeyboardMarkup(row_width=3)
            mk.add(types.InlineKeyboardButton("30s",callback_data="eok_exp_30"),types.InlineKeyboardButton("1m",callback_data="eok_exp_60"),types.InlineKeyboardButton("5m",callback_data="eok_exp_300"))
            bot.send_message(cid,f"✅ Custom N{amt:,} - Pick expiry ⏱️",reply_markup=mk)
        except: bot.send_message(cid,"❌ Number only e.g. 29800")
    elif cid in USER_STATE and USER_STATE[cid].get('awaiting_qn'):
        try:
            amt_n=int(m.text.strip().replace(",","").replace("N",""))
            if amt_n<100: bot.send_message(cid,"❌ Min N100"); return
            USER_STATE[cid]['awaiting_qn']=False
            pair=USER_STATE[cid].get('qn_pair'); bal=USER_STATE[cid].get('qn_bal')
            amt_usd=amt_n/1600.0
            if DB["rec_count"].get(str(cid),0)>=3: bot.send_message(cid,"🛡️ REC limit 3 reached, blocked"); return
            bot.send_message(cid,f"✅ Custom N{amt_n:,} (${amt_usd:.2f}) - Scanning {pair}... 🔍")
            msg_scan=bot.send_message(cid,f"🔍 **{BRAND_NAME} QUICK**\nSCANNING {pair}...\n\n░░░░░░░░░░ 0% starting")
            animate_progress_bar(cid, msg_scan.message_id, pair, f"N{amt_n:,}")
            d=analyze_momentum(pair,god_mode=GOD_MODE.get(cid,False),uid=cid)
            if not d: bot.send_message(cid,"❌ No signal 😔"); return
            ok,oid,exp=iq_trade(pair,d['dir'],amt_usd,bal,30)
            if not ok: bot.send_message(cid,"❌ Failed"); return
            bot.send_message(cid,f"✅ Placed {oid} N{amt_n:,} 🚀"); time.sleep(exp+5)
            with IQ_LOCK: pnl=iq.check_win_v4(oid)
            if pnl>0: update_stats(cid,True,pnl); update_pair_mem(cid,pair,True); bot.send_message(cid,f"✅💚 WIN!!! +N{int(pnl*1600):,} REC 0/3 ✅",reply_markup=main_menu_iq(cid))
            else: update_stats(cid,False,-amt_usd); update_pair_mem(cid,pair,False); bot.send_message(cid,f"❌ LOSS -N{amt_n:,} REC {DB['rec_count'].get(str(cid),0)}/3",reply_markup=main_menu_iq(cid))
        except: bot.send_message(cid,"❌ Number only e.g. 29800")

threading.Thread(target=signal_loop,daemon=True).start()
if __name__=="__main__":
    try: bot.remove_webhook(); time.sleep(1)
    except: pass
    ext_url=os.getenv("RENDER_EXTERNAL_URL")
    if ext_url:
        try: bot.set_webhook(url=f"{ext_url}/{BOT_TOKEN}"); print(f"MASTER V7.4 FINAL PRIVATE AUTO LIVE {ext_url}",flush=True)
        except: pass
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
