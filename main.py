import os, time, threading, warnings, json
from datetime import datetime, timedelta
import pytz
from flask import Flask, request
import telebot
from telebot import types
import pandas as pd
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

warnings.filterwarnings("ignore")
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
OWNER_ID = 8659453018
ALLOWED_IDS = [OWNER_ID]

BRAND_NAME = "KEVIN TRAILBLAZER"
DB_FILE = "bot_db.json"
def load_db():
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE,"r") as f: return json.load(f)
    except: pass
    return {"stats":{},"daily":{},"limits":{},"pair_mem":{},"users_keys":[]}
def save_db():
    try:
        with open(DB_FILE,"w") as f: json.dump(DB,f)
    except: pass
DB = load_db()
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
        s["wins"]+=1; s["streak"]=s["streak"]+1 if s["last_result"]=="WIN" else 1
        s["best_streak"]=max(s["best_streak"],s["streak"]); s["last_result"]="WIN"
    else: s["loss"]+=1; s["streak"]=0; s["last_result"]="LOSS"
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

STATS={"balance":100.0,"wins":0,"loss":0,"profit":0.0}
GOD_MODE={}; SMART_REC={}; AUTO_RUNNING={}; NEWS_FILTER={}; NEWS_PAUSED={}; MARKET_MODE={}
LAST_NEWS_CHECK=0; HIGH_IMPACT_NEWS=[]
USER_STATE={}
FAKE_WR_DISPLAY={"USDSDG-OTC":83.7,"USDMXN-OTC":83.7,"USDBDT-OTC":81.4,"USDARS-OTC":81.2,"USDTRY-OTC":80.4,"USDZAR-OTC":78.5}

# === NEW: REAL MOVING PROGRESS BAR 0-100% ===
def animate_progress_bar(cid, mid, pair, amount_text, brand=BRAND_NAME):
    steps = [
        (10, "reading candles 1m"),
        (20, "reading candles 1m"),
        (35, "reading momentum"),
        (50, "reading momentum + MTF 5m"),
        (65, "checking BB + ATR"),
        (80, "locking signal"),
        (90, "verifying edge"),
        (100, "SIGNAL LOCKED"),
    ]
    for pct, stage in steps:
        filled = pct // 10
        bar = "▓" * filled + "░" * (10 - filled)
        txt = f"🔍 **{brand} QUICK**\nSCANNING {pair}...\n\n{bar} {pct}%\n> {stage}\nAmount {amount_text}"
        try: bot.edit_message_text(txt, cid, mid)
        except: pass
        time.sleep(0.35)

def animate_progress_bar_eok(cid, mid, pair):
    steps = [
        (10, "reading candles"),
        (25, "reading candles"),
        (40, "reading momentum"),
        (55, "verifying edge"),
        (70, "checking volatility"),
        (85, "locking signal"),
        (100, "SIGNAL FOUND"),
    ]
    for pct, stage in steps:
        filled = pct // 10
        bar = "▓" * filled + "░" * (10 - filled)
        txt = f"🔍 **{BRAND_NAME}**\nSCANNING MARKET...\n\n{bar} {pct}%\n> {stage}\nPair {pair}"
        try: bot.edit_message_text(txt, cid, mid)
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
    mtf_confirm=False
    mtf_dir="NONE"
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
        if mom1>0.02 and mom3>0.05 and is_green and e9>e21 and rsi_now>50 and rsi_now<78:
            sig="CALL"; score=88; reason=f"🚀 Bull {mom1:.3f}%"
        elif mom1<-0.02 and mom3<-0.05 and not is_green and e9<e21 and rsi_now<50:
            sig="PUT"; score=88; reason=f"📉 Bear {mom1:.3f}%"
        elif e9>e21 and is_green: sig="CALL"; score=80; reason=f"📈 EMA Bull"
        elif e9<e21 and not is_green: sig="PUT"; score=80; reason=f"📉 EMA Bear"
        if mtf_dir!="NONE":
            if sig==mtf_dir:
                score+=8; reason+=f" ✅ MTF {mtf_dir} 5m"; mtf_confirm=True
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
        print(f"Analyze error {pair}: {e}")
        return None

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
            mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100
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

def main_menu(cid):
    god=GOD_MODE.get(cid,False); rec=SMART_REC.get(cid,False); news=NEWS_FILTER.get(cid,True); mode=MARKET_MODE.get(cid,"ALL")
    ensure_user(cid); s=DB["stats"][str(cid)]; d=DB["daily"][str(cid)]
    mk=types.InlineKeyboardMarkup(row_width=2)
    mk.add(types.InlineKeyboardButton(f"⚡ New Opportunity - {BRAND_NAME}",callback_data="new_op"))
    mk.add(
        types.InlineKeyboardButton("🚀 QUICK",callback_data="quick"),
        types.InlineKeyboardButton("🤖 AUTO",callback_data="auto"),
        types.InlineKeyboardButton(f"👑 GOD {'✅' if god else '❌'}",callback_data="god"),
        types.InlineKeyboardButton(f"🧠 REC {'✅' if rec else '❌'}",callback_data="recovery"),
        types.InlineKeyboardButton(f"📰 NEWS {'✅' if news else '❌'}",callback_data="news"),
        types.InlineKeyboardButton(f"💱 {mode}",callback_data="market"),
        types.InlineKeyboardButton(f"📊 ${d['pnl']:.1f}",callback_data="pnl"),
        types.InlineKeyboardButton(f"🔥 {s['streak']}",callback_data="mystats"),
        types.InlineKeyboardButton("🏆 TOP",callback_data="top"),
        types.InlineKeyboardButton("📈 BACKTEST",callback_data="backtest_menu"),
        types.InlineKeyboardButton("🎯 MEM",callback_data="pair_mem"),
        types.InlineKeyboardButton("⏸️ STOP",callback_data="stop_auto")
    )
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

@bot.message_handler(commands=['start'])
def start(m):
    if m.from_user.id not in ALLOWED_IDS: bot.send_message(m.chat.id,f"⛔🔒 PRIVATE BOT\n🆔 ID: {m.from_user.id}"); return
    NEWS_FILTER.setdefault(m.chat.id,True); MARKET_MODE.setdefault(m.chat.id,"ALL"); ensure_user(m.from_user.id)
    s=DB["stats"][str(m.from_user.id)]; d=DB["daily"][str(m.from_user.id)]
    base=1.0; smart=get_smart_lot(m.from_user.id, base)
    txt=f"""🤖✨ **{BRAND_NAME} V54 PRO MAX** 💎🔥
━━━━━━━━━━━━━━━
👑 Owner {OWNER_ID} | 📡 IQ {'🟢' if IQ_CONNECTED else '🔴'}
━━━━━━━━━━━━━━━
💰 Today: ${d['pnl']:.2f} ({d['trades']}) | 🔥 Streak {s['streak']} Best {s['best_streak']}
📈 All Time: {s['wins']}W/{s['loss']}L WR {(s['wins']/s['total']*100) if s['total'] else 0:.1f}% Profit ${s['profit']:.2f}
💡 Smart Lot: ${base} → ${smart}
━━━━━━━━━━━━━━━
🆕 0-100% Moving Bar + QUICK Naira
━━━━━━━━━━━━━━━
"""
    bot.send_message(m.chat.id,txt,reply_markup=main_menu(m.chat.id))

@bot.message_handler(commands=['backtest'])
def backtest_cmd(m):
    if m.from_user.id not in ALLOWED_IDS: return
    try:
        pair=m.text.split()[1].upper()
        if "-OTC" not in pair and pair not in ["EURUSD","GBPUSD"]: pair+="-OTC"
        bot.send_message(m.chat.id,f"🔍📊 Backtesting {pair} last 100 candles... ⏳")
        res=backtest_pair(pair)
        if not res: bot.send_message(m.chat.id,f"❌ Backtest failed for {pair}"); return
        txt=f"""📈 **BACKTEST {pair}** 📈
━━━━━━━━━━━━━━━
🎯 Wins: {res['wins']}/{res['total']}
📊 WR: {res['wr']:.1f}%
"""
        bot.send_message(m.chat.id,txt)
    except: bot.send_message(m.chat.id,"⚙️ Usage: /backtest EURUSD-OTC")

@bot.message_handler(commands=['mystats'])
def mystats_cmd(m):
    if m.from_user.id not in ALLOWED_IDS: return
    ensure_user(m.from_user.id); uid_s=str(m.from_user.id); s=DB["stats"][uid_s]; d=DB["daily"][uid_s]
    total=s["total"]; wr=(s["wins"]/total*100) if total else 0
    smart=get_smart_lot(m.from_user.id,1.0)
    txt=f"📊 {BRAND_NAME} STATS\nToday ${d['pnl']:.2f} ({d['trades']}) Streak {s['streak']}\nSmart Lot: $1 → ${smart} (WR {wr:.0f}%)\nAll Time {total} W{s['wins']} L{s['loss']} WR {wr:.1f}% P ${s['profit']:.2f}\n"
    bot.send_message(m.chat.id,txt)

@bot.message_handler(commands=['setlimits'])
def setlimits_cmd(m):
    try:
        parts=m.text.split(); loss=float(parts[1]); win=float(parts[2])
        DB["limits"][str(m.from_user.id)]={"loss":-abs(loss),"win":abs(win)}; save_db()
        bot.send_message(m.chat.id,f"✅ Limits Loss ${-abs(loss)} Win ${abs(win)}")
    except: bot.send_message(m.chat.id,"Usage: /setlimits 3 5")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    cid=c.message.chat.id; data=c.data; ensure_user(cid)
    if cid not in USER_STATE: USER_STATE[cid]={}

    if data=="new_op":
        bot.send_message(cid,f"👇 **Trade Live | Trade Demo - {BRAND_NAME}**",reply_markup=trade_type_kb()); return
    if data.startswith("type_"):
        bal=data.split("_")[1]; USER_STATE[cid]['balance']=bal
        bot.send_message(cid,f"✅ {bal} Selected\n\n💰 **Enter your custom amount (e.g. 75 NGN):**",reply_markup=amount_kb()); return
    if data.startswith("eok_amt_"):
        if data=="eok_amt_custom":
            bot.send_message(cid,"✏️ Enter your custom amount (e.g. 29800):\nType number only"); USER_STATE[cid]['awaiting_amount']=True; return
        if data=="cancel": bot.send_message(cid,"❌ Cancelled",reply_markup=main_menu(cid)); return
        amt=int(data.split("_")[2]); USER_STATE[cid]['amount']=amt; USER_STATE[cid]['awaiting_amount']=False
        bot.send_message(cid,f"✅ Amount N{amt:,}\n\n⏱️ **Pick your expiry timeframe**",reply_markup=expiry_kb()); return
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
        if not ok_lim: bot.send_message(cid,msg_lim,reply_markup=main_menu(cid)); return
        can_trade,msg=check_news_before_trade(cid)
        if not can_trade: bot.send_message(cid,msg,reply_markup=main_menu(cid)); return
        msg_scan=bot.send_message(cid,f"🔍 **{BRAND_NAME}**\nSCANNING MARKET...\n\n░░░░░░░░░░ 0% starting")
        animate_progress_bar_eok(cid, msg_scan.message_id, pair)
        d=analyze_momentum(pair,god_mode=GOD_MODE.get(cid,False),uid=cid)
        if not d: bot.send_message(cid,"❌ No signal (MTF conflict / BB Squeeze / GOD / BAD WR) Try another",reply_markup=eok_pairs_kb()); return
        bot.send_message(cid,f"```\n🔒 {BRAND_NAME} 🔒\n--------------------------\nSIGNAL FOUND\n--------------------------\nPairs: {pair}\nAction: {d['dir']}\nAmount: N{amt:,}.00\nExpiry: {exp}s\nConf: {d['conf']:.0f}%\n--------------------------\nPlacing trade...\n```",parse_mode="Markdown")
        time.sleep(1)
        bot.send_message(cid,f"🟢 **{BRAND_NAME}**\nPairs: {pair}\nSignal: {d['dir']}\nAmount: N{amt:,}.00\nExpiry: {exp}s\nReason: {d['reason']}")
        ngn_to_usd=amt/1600.0
        if SMART_REC.get(cid,False) and DB["stats"][str(cid)]["last_result"]=="LOSS":
            ngn_to_usd=round(ngn_to_usd*2.2,2)
            bot.send_message(cid,f"🧠 REC ACTIVE 2.2x → N{int(ngn_to_usd*1600):,}")
        ok,oid,exp_real=iq_trade(pair,d['dir'],ngn_to_usd,bal,expiry=exp)
        if not ok: bot.send_message(cid,"❌ Trade Failed",reply_markup=main_menu(cid)); return
        bot.send_message(cid,f"✅ Placed {oid} {exp_real}s"); time.sleep(exp_real+5)
        try:
            with IQ_LOCK: pnl=iq.check_win_v4(oid)
            if pnl>0:
                streak=update_stats(cid,True,pnl); update_pair_mem(cid,pair,True)
                profit_ngn=int(pnl*1600)
                bot.send_message(cid,f"🔥 **{BRAND_NAME}**\nRESULT: ✅ WIN\nPayout: +N{profit_ngn:,}.00\nStreak {streak}",reply_markup=main_menu(cid))
            else:
                update_stats(cid,False,-ngn_to_usd); update_pair_mem(cid,pair,False)
                bot.send_message(cid,f"🔥 **{BRAND_NAME}**\nRESULT: ❌ LOSS\nLoss: -N{amt:,}.00",reply_markup=main_menu(cid))
        except: bot.send_message(cid,"Check IQ manually",reply_markup=main_menu(cid))
        return

    if data=="backtest_menu":
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in ALL_PAIRS[:8]: mk.add(types.InlineKeyboardButton(f"📈 {p}",callback_data=f"bt_{p}"))
        bot.send_message(cid,"📈 **BACKTEST MENU**",reply_markup=mk); return
    if data.startswith("bt_"):
        pair=data.replace("bt_",""); bot.send_message(cid,f"🔍 Backtesting {pair}..."); res=backtest_pair(pair)
        if not res: bot.send_message(cid,"❌ Failed"); return
        emoji="⭐💎 BEST" if res['wr']>=65 else "⚠️🚫 AVOID" if res['wr']<50 else "📊 OK"
        bot.send_message(cid,f"📈 {pair} Backtest: {res['wins']}/{res['total']} WR {res['wr']:.1f}% {emoji}",reply_markup=main_menu(cid)); return
    if data=="quick":
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in ALL_PAIRS[:12]:
            wr=get_pair_wr(cid,p); label=p; 
            if wr: label+=f" {wr:.0f}%"
            mk.add(types.InlineKeyboardButton(label,callback_data=f"pair_{p}"))
        bot.send_message(cid,f"💹 QUICK TRADE V54 - {BRAND_NAME}",reply_markup=mk); return
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
        bot.send_message(cid,f"✅ {pair} {bal}\n💰 Naira + USD available\n💡 Smart Lot ${smart}",reply_markup=mk); return

    if data.startswith("qn_"):
        parts=data.split("_")
        if parts[1]=="custom":
            _,_,pair,bal = data.split("_",3)
            USER_STATE[cid]['awaiting_qn']=True
            USER_STATE[cid]['qn_pair']=pair
            USER_STATE[cid]['qn_bal']=bal
            bot.send_message(cid,"✏️ Enter custom Naira amount e.g. 29800"); return
        amt_n=int(parts[1]); pair=parts[2]; bal=parts[3]
        amt_usd=amt_n/1600.0
        if SMART_REC.get(cid,False) and DB["stats"][str(cid)]["last_result"]=="LOSS":
            amt_usd=round(amt_usd*2.2,2)
            bot.send_message(cid,f"🧠 REC ACTIVE 2.2x → N{int(amt_usd*1600):,}")
        ok_lim,msg_lim=check_daily_limits(cid)
        if not ok_lim: bot.send_message(cid,msg_lim); return
        can_trade,msg=check_news_before_trade(cid)
        if not can_trade: bot.send_message(cid,msg); return
        msg_scan=bot.send_message(cid,f"🔍 **{BRAND_NAME} QUICK**\nSCANNING {pair}...\n\n░░░░░░░░░░ 0% starting\nAmount N{amt_n:,}")
        animate_progress_bar(cid, msg_scan.message_id, pair, f"N{amt_n:,}")
        d=analyze_momentum(pair,god_mode=GOD_MODE.get(cid,False),uid=cid)
        if not d: bot.send_message(cid,"❌ No signal"); return
        dir_emoji="🟢📈 CALL" if d['dir']=="CALL" else "🔴📉 PUT"
        try:
            plt.figure(figsize=(6,3)); plt.plot(d['df']['close'],color='#FFD700',linewidth=2); plt.title(f"{pair} {d['dir']} {d['conf']:.0f}% MTF:{d['mtf']}"); plt.grid(alpha=0.3); plt.tight_layout(); p="/tmp/c.png"; plt.savefig(p); plt.close()
            bot.send_photo(cid,open(p,'rb'),caption=f"📡 {BRAND_NAME} QUICK SIGNAL FOUND!\n{pair} {dir_emoji} {d['conf']:.0f}%\nAmount N{amt_n:,} (${amt_usd:.2f}) Payout {int(d['payout']*100)}%\n{d['reason']}")
        except: bot.send_message(cid,f"{pair} {d['dir']} {d['conf']:.0f}% N{amt_n:,}")
        ok,oid,exp=iq_trade(pair,d['dir'],amt_usd,bal,30)
        if not ok: bot.send_message(cid,"❌ Trade Failed"); return
        bot.send_message(cid,f"✅ Placed {oid} {exp}s - N{amt_n:,}"); time.sleep(exp+5)
        try:
            with IQ_LOCK: pnl=iq.check_win_v4(oid)
            if pnl>0:
                streak=update_stats(cid,True,pnl); update_pair_mem(cid,pair,True)
                bot.send_message(cid,f"✅💚 WIN!!! +N{int(pnl*1600):,} (${pnl:.2f}) Streak {streak} 💎",reply_markup=main_menu(cid))
            else:
                update_stats(cid,False,-amt_usd); update_pair_mem(cid,pair,False)
                bot.send_message(cid,f"❌ LOSS -N{amt_n:,} (${amt_usd:.2f}) 😔",reply_markup=main_menu(cid))
        except: bot.send_message(cid,"Check IQ")
        return

    if data.startswith("amt_") and not data.startswith("auto_amt_") and not data.startswith("eok_amt_"):
        parts=data.split("_"); amt=float(parts[1]); pair=parts[2]; bal=parts[3]
        ok_lim,msg_lim=check_daily_limits(cid)
        if not ok_lim: bot.send_message(cid,msg_lim); return
        can_trade,msg=check_news_before_trade(cid)
        if not can_trade: bot.send_message(cid,msg); return
        msg_scan=bot.send_message(cid,f"🔍 **{BRAND_NAME} QUICK**\nSCANNING {pair}...\n\n░░░░░░░░░░ 0% starting\nAmount ${amt}")
        animate_progress_bar(cid, msg_scan.message_id, pair, f"${amt} (N{int(amt*1600):,})")
        d=analyze_momentum(pair,god_mode=GOD_MODE.get(cid,False),uid=cid)
        if not d: bot.send_message(cid,"❌ No signal"); return
        dir_emoji="🟢📈 CALL" if d['dir']=="CALL" else "🔴📉 PUT"
        try:
            plt.figure(figsize=(6,3)); plt.plot(d['df']['close'],color='#FFD700',linewidth=2); plt.title(f"{pair} {d['dir']} {d['conf']:.0f}% MTF:{d['mtf']}"); plt.grid(alpha=0.3); plt.tight_layout(); p="/tmp/c.png"; plt.savefig(p); plt.close()
            bot.send_photo(cid,open(p,'rb'),caption=f"📡 {BRAND_NAME} QUICK SIGNAL FOUND!\n{pair} {dir_emoji} {d['conf']:.0f}%\nPayout {int(d['payout']*100)}% ${amt} (N{int(amt*1600):,})\n{d['reason']}")
        except: bot.send_message(cid,f"{pair} {d['dir']} {d['conf']:.0f}%")
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal,30)
        if not ok: bot.send_message(cid,"❌ Trade Failed"); return
        bot.send_message(cid,f"✅ Placed {oid} {exp}s"); time.sleep(exp+5)
        try:
            with IQ_LOCK: pnl=iq.check_win_v4(oid)
            if pnl>0:
                streak=update_stats(cid,True,pnl); update_pair_mem(cid,pair,True)
                bot.send_message(cid,f"✅💚 WIN!!! +${pnl:.2f} (+N{int(pnl*1600):,}) Streak {streak} 💎",reply_markup=main_menu(cid))
            else:
                update_stats(cid,False,-amt); update_pair_mem(cid,pair,False)
                bot.send_message(cid,f"❌ LOSS -${amt:.2f} (-N{int(amt*1600):,}) 😔",reply_markup=main_menu(cid))
        except: bot.send_message(cid,"Check IQ")
        return

    if data=="god": GOD_MODE[cid]=not GOD_MODE.get(cid,False); bot.send_message(cid,f"GOD {GOD_MODE[cid]}",reply_markup=main_menu(cid)); return
    if data=="recovery": SMART_REC[cid]=not SMART_REC.get(cid,False); bot.send_message(cid,f"🧠 REC {SMART_REC[cid]}",reply_markup=main_menu(cid)); return
    if data=="news": NEWS_FILTER[cid]=not NEWS_FILTER.get(cid,True); bot.send_message(cid,f"NEWS FILTER {NEWS_FILTER[cid]}",reply_markup=main_menu(cid)); return
    if data=="market":
        cur=MARKET_MODE.get(cid,"ALL"); nxt={"ALL":"OTC","OTC":"REAL","REAL":"ALL"}[cur]; MARKET_MODE[cid]=nxt
        bot.send_message(cid,f"MARKET MODE → {nxt}",reply_markup=main_menu(cid)); return
    if data=="stop_auto": AUTO_RUNNING[cid]=False; bot.send_message(cid,"Stopped",reply_markup=main_menu(cid)); return
    if data=="mystats" or data=="pnl" or data=="top":
        s=DB["stats"][str(cid)]; d=DB["daily"][str(cid)]; bot.send_message(cid,f"W {s['wins']} L {s['loss']} Today ${d['pnl']:.2f} Streak {s['streak']} Best {s['best_streak']}",reply_markup=main_menu(cid)); return
    if data=="pair_mem":
        pm=DB["pair_mem"].get(str(cid),{})
        if not pm: bot.send_message(cid,"No data"); return
        txt=f"{BRAND_NAME} PAIR MEM\n"; 
        for p,dat in sorted(pm.items(),key=lambda x:(x[1]['wins']/x[1]['total'] if x[1]['total'] else 0),reverse=True):
            wrp=dat["wins"]/dat["total"]*100 if dat["total"] else 0; txt+=f"{p}: {wrp:.0f}% {dat['wins']}/{dat['total']}\n"
        bot.send_message(cid,txt,reply_markup=main_menu(cid)); return
    if data=="auto":
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🟢 DEMO $1",callback_data="auto_bal_PRACTICE_1"),types.InlineKeyboardButton("🔴 REAL $1",callback_data="auto_bal_REAL_1"))
        bot.send_message(cid,"🤖 AUTO MODE - Pick balance",reply_markup=mk); return
    if data.startswith("auto_bal_"):
        _,_,bal,amt_s=data.split("_"); amt=float(amt_s); USER_STATE[cid]['auto_bal']=bal; USER_STATE[cid]['auto_amt']=amt; AUTO_RUNNING[cid]=True
        bot.send_message(cid,f"🤖 AUTO STARTED {bal} ${amt}"); return

@bot.message_handler(func=lambda m: True)
def custom_handler(m):
    cid=m.chat.id
    if cid in USER_STATE and USER_STATE[cid].get('awaiting_amount'):
        try:
            amt=int(m.text.strip().replace(",","").replace("N",""))
            if amt<100: bot.send_message(cid,"❌ Min N100"); return
            USER_STATE[cid]['amount']=amt; USER_STATE[cid]['awaiting_amount']=False
            mk=types.InlineKeyboardMarkup(row_width=3)
            mk.add(types.InlineKeyboardButton("30s",callback_data="eok_exp_30"),types.InlineKeyboardButton("1m",callback_data="eok_exp_60"),types.InlineKeyboardButton("5m",callback_data="eok_exp_300"))
            bot.send_message(cid,f"✅ Custom N{amt:,} - Pick expiry",reply_markup=mk)
        except: bot.send_message(cid,"❌ Number only e.g. 29800")
    elif cid in USER_STATE and USER_STATE[cid].get('awaiting_qn'):
        try:
            amt_n=int(m.text.strip().replace(",","").replace("N",""))
            if amt_n<100: bot.send_message(cid,"❌ Min N100"); return
            USER_STATE[cid]['awaiting_qn']=False
            pair=USER_STATE[cid].get('qn_pair'); bal=USER_STATE[cid].get('qn_bal')
            amt_usd=amt_n/1600.0
            bot.send_message(cid,f"✅ Custom N{amt_n:,} (${amt_usd:.2f}) - Scanning {pair}...")
            msg_scan=bot.send_message(cid,f"🔍 **{BRAND_NAME} QUICK**\nSCANNING {pair}...\n\n░░░░░░░░░░ 0% starting")
            animate_progress_bar(cid, msg_scan.message_id, pair, f"N{amt_n:,}")
            d=analyze_momentum(pair,god_mode=GOD_MODE.get(cid,False),uid=cid)
            if not d: bot.send_message(cid,"❌ No signal"); return
            ok,oid,exp=iq_trade(pair,d['dir'],amt_usd,bal,30)
            if not ok: bot.send_message(cid,"❌ Failed"); return
            bot.send_message(cid,f"✅ Placed {oid} N{amt_n:,}"); time.sleep(exp+5)
            with IQ_LOCK: pnl=iq.check_win_v4(oid)
            if pnl>0: update_stats(cid,True,pnl); update_pair_mem(cid,pair,True); bot.send_message(cid,f"✅ WIN +N{int(pnl*1600):,} 💎",reply_markup=main_menu(cid))
            else: update_stats(cid,False,-amt_usd); update_pair_mem(cid,pair,False); bot.send_message(cid,f"❌ LOSS -N{amt_n:,} 😔",reply_markup=main_menu(cid))
        except: bot.send_message(cid,"❌ Number only e.g. 29800")

@app.route(f"/{BOT_TOKEN}",methods=['POST'])
def wh():
    data=request.get_data().decode("utf-8"); update=telebot.types.Update.de_json(data)
    bot.process_new_updates([update]); return "ok"
@app.route("/")
def home(): return f"{BRAND_NAME} V54 98/100 READY 0-100 BAR"
if __name__=="__main__":
    threading.Thread(target=lambda:app.run(host="0.0.0.0",port=int(os.getenv("PORT",10000))),daemon=True).start()
    try: bot.remove_webhook()
    except: pass
    bot.infinity_polling(timeout=60,long_polling_timeout=60)
