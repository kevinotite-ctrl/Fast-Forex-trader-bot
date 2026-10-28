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

warnings.filterwarnings("ignore")
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
OWNER_ID = 8659453018
ALLOWED_IDS = [OWNER_ID]

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
    if d["pnl"]<=lim["loss"]: return False, f"🛡️💔 DAILY LOSS LIMIT HIT!\n📉 ${d['pnl']:.2f} / ${lim['loss']:.2f}\n🚫 Bot blocked today! Come back tomorrow 💤\n⚙️ Change: /setlimits"
    if d["pnl"]>=lim["win"]: return False, f"🛡️💰 DAILY WIN LIMIT HIT!\n💵 ${d['pnl']:.2f} / ${lim['win']:.2f}\n🔒💎 Profit LOCKED! Stop for today 🎉"
    return True,"OK"

def update_stats(uid,win,pnl):
    uid_s=str(uid); ensure_user(uid); s=DB["stats"][uid_s]; d=DB["daily"][uid_s]
    s["total"]+=1; d["trades"]+=1; d["pnl"]+=pnl
    if win:
        s["wins"]+=1; s["streak"]=s["streak"]+1 if s["last_result"]=="WIN" else 1
        s["best_streak"]=max(s["best_streak"],s["streak"]); s["last_result"]="WIN"
    else: s["loss"]+=1; s["streak"]=0; s["last_result"]="LOSS"
    s["profit"]+=pnl; save_db(); return s["streak"]

ALL_PAIRS=["EURUSD-OTC","GBPUSD-OTC","EURGBP-OTC","USDJPY-OTC","GBPJPY-OTC","AUDUSD-OTC","USDCHF-OTC","EURJPY-OTC","EURUSD","GBPUSD","EURGBP","USDJPY","GBPJPY","AUDUSD","USDCHF","EURJPY","EURCHF","GBPCHF","AUDJPY","NZDUSD","BTCUSD-OTC","ETHUSD-OTC","GOLD-OTC","SILVER-OTC"]
OTC_ONLY=["EURUSD-OTC","GBPUSD-OTC","EURGBP-OTC","USDJPY-OTC","GBPJPY-OTC","AUDUSD-OTC","USDCHF-OTC","EURJPY-OTC"]

STATS={"balance":100.0,"wins":0,"loss":0,"profit":0.0}
GOD_MODE={}; SMART_REC={}; AUTO_RUNNING={}; NEWS_FILTER={}; NEWS_PAUSED={}; MARKET_MODE={}
LAST_NEWS_CHECK=0; HIGH_IMPACT_NEWS=[]

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
    if is_news: NEWS_PAUSED[cid]=time.time()+3600; return False,f"📰🚨 RED NEWS ALERT!\n🔴 {news_item['title']}\n⏰ {news_item['time'].strftime('%H:%M UTC')}\n⏸️ Paused 60min 🛑"
    if cid in NEWS_PAUSED and time.time()<NEWS_PAUSED[cid]: rem=int((NEWS_PAUSED[cid]-time.time())/60); return False,f"⏸️📰 News pause {rem}min left ⏳"
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
def get_candles(pair):
    if not IQ_CONNECTED and not iq_reconnect(): return None
    for _ in range(2):
        try:
            with IQ_LOCK: c=iq.get_candles(pair,60,50,time.time())
            if c and len(c)>20: return pd.DataFrame(sorted(c,key=lambda x:x['from']))
            iq_reconnect(); time.sleep(1)
        except: iq_reconnect(); time.sleep(1)
    return None
def calc_rsi(closes,period=7):
    delta=closes.diff(); gain=delta.where(delta>0,0).rolling(period).mean(); loss=-delta.where(delta<0,0).rolling(period).mean()
    return 100-(100/(1+gain/loss))

def analyze_momentum(pair,god_mode=False,uid=None):
    if uid:
        wr=get_pair_wr(uid,pair)
        if wr is not None and wr<40: return None
    df=get_candles(pair)
    if df is None: return None
    try:
        close=df['close']; open_=df['open']; ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean(); rsi=calc_rsi(close,7)
        rsi_now=float(rsi.iloc[-1]); e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1])
        mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100; mom3=(close.iloc[-1]-close.iloc[-4])/close.iloc[-4]*100
        is_green=float(close.iloc[-1])>float(open_.iloc[-1]); payout=get_payout(pair); sig="CALL" if is_green else "PUT"; score=75; reason=""
        if mom1>0.02 and mom3>0.05 and is_green and e9>e21 and rsi_now>50 and rsi_now<78: sig="CALL"; score=90; reason=f"🚀📈 Bull {mom1:.3f}%"
        elif mom1<-0.02 and mom3<-0.05 and not is_green and e9<e21 and rsi_now<50: sig="PUT"; score=90; reason=f"📉🔻 Bear {mom1:.3f}%"
        elif e9>e21 and is_green: sig="CALL"; score=82; reason=f"📈 EMA Bull"
        elif e9<e21 and not is_green: sig="PUT"; score=82; reason=f"📉 EMA Bear"
        if uid:
            wr=get_pair_wr(uid,pair)
            if wr and wr>=65: score+=4; reason+=f" ⭐💎 Fav {wr:.0f}% WR"
        if god_mode:
            if score<88 or payout<0.85: return None
            if abs(mom3)<0.08: return None
            score=min(96,score+5); reason+=" 👑✨ GOD"
        return {"pair":pair,"dir":sig,"conf":min(94,score),"price":float(close.iloc[-1]),"rsi":rsi_now,"reason":reason,"mom":mom3,"payout":payout,"df":df.tail(30)}
    except: return None

def iq_trade(pair,direction,amount,bal):
    try:
        with IQ_LOCK:
            iq.change_balance(bal)
            try: _,oid=iq.buy_blitz(pair,amount,direction.lower(),30); return True,oid,30
            except: _,oid=iq.buy(amount,pair,direction.lower(),1); return True,oid,60
    except: return False,None,0

def main_menu(cid):
    god=GOD_MODE.get(cid,False); rec=SMART_REC.get(cid,False); news=NEWS_FILTER.get(cid,True); mode=MARKET_MODE.get(cid,"ALL")
    ensure_user(cid); s=DB["stats"][str(cid)]; d=DB["daily"][str(cid)]
    mk=types.InlineKeyboardMarkup(row_width=2)
    mk.add(
        types.InlineKeyboardButton("🚀 QUICK TRADE",callback_data="quick"),
        types.InlineKeyboardButton("🤖 AUTO PILOT",callback_data="auto"),
        types.InlineKeyboardButton(f"👑 GOD {'✅' if god else '❌'}",callback_data="god"),
        types.InlineKeyboardButton(f"🧠 REC {'✅' if rec else '❌'}",callback_data="recovery"),
        types.InlineKeyboardButton(f"📰 NEWS {'✅' if news else '❌'}",callback_data="news"),
        types.InlineKeyboardButton(f"💱 {mode}",callback_data="market"),
        types.InlineKeyboardButton(f"📊 ${d['pnl']:.1f}",callback_data="pnl"),
        types.InlineKeyboardButton(f"🔥 {s['streak']} STREAK",callback_data="mystats"),
        types.InlineKeyboardButton("🏆 TOP",callback_data="top"),
        types.InlineKeyboardButton("🛡️ LIMITS",callback_data="limits"),
        types.InlineKeyboardButton("🎯 PAIR MEM",callback_data="pair_mem"),
        types.InlineKeyboardButton("⏸️ STOP",callback_data="stop_auto")
    )
    return mk

@bot.message_handler(commands=['start'])
def start(m):
    if m.from_user.id not in ALLOWED_IDS: bot.send_message(m.chat.id,f"⛔🔒 PRIVATE BOT\n🆔 Your ID: {m.from_user.id}\n👑 Contact owner to get access!"); return
    NEWS_FILTER.setdefault(m.chat.id,True); MARKET_MODE.setdefault(m.chat.id,"ALL"); ensure_user(m.from_user.id)
    s=DB["stats"][str(m.from_user.id)]; d=DB["daily"][str(m.from_user.id)]
    txt=f"""🤖✨ **V53.5 EMOJI PRO** 🔥💎
━━━━━━━━━━━━━━━
👑 Owner: {OWNER_ID} | 📡 IQ: {'🟢✅' if IQ_CONNECTED else '🔴❌'}
━━━━━━━━━━━━━━━
💰 Today: ${d['pnl']:.2f} | 📊 {d['trades']} trades
🔥 Streak: {s['streak']} | 🏅 Best: {s['best_streak']}
📈 All Time: {s['wins']}W/{s['loss']}L | 💵 ${s['profit']:.2f}
━━━━━━━━━━━━━━━
💱 Mode: {MARKET_MODE.get(m.chat.id)} | 📰 News: {'ON ✅' if NEWS_FILTER.get(m.chat.id) else 'OFF ❌'}
👇 **SELECT ACTION** 👇
"""
    bot.send_message(m.chat.id,txt,reply_markup=main_menu(m.chat.id),parse_mode="Markdown")

@bot.message_handler(commands=['mystats'])
def mystats_cmd(m):
    if m.from_user.id not in ALLOWED_IDS: return
    ensure_user(m.from_user.id); uid_s=str(m.from_user.id); s=DB["stats"][uid_s]; d=DB["daily"][uid_s]; lim=DB["limits"][uid_s]
    total=s["total"]; wr=(s["wins"]/total*100) if total else 0
    txt=f"""📊💎 **YOUR STATS V53.5** 📊💎
━━━━━━━━━━━━━━━
📅 Today {d['date']}
💰 P/L: ${d['pnl']:.2f} | 📦 {d['trades']} trades
🔥 Current Streak: {s['streak']} | 🏆 Best: {s['best_streak']}
🛡️ Limits: ❌ Loss ${lim['loss']} | ✅ Win ${lim['win']}
━━━━━━━━━━━━━━━
📈 **ALL TIME**
🎯 Total: {total}
✅ Wins: {s['wins']} | ❌ Loss: {s['loss']}
📊 WinRate: {wr:.1f}% | 💵 Profit: ${s['profit']:.2f}
━━━━━━━━━━━━━━━
"""
    pm=DB["pair_mem"].get(uid_s,{})
    if pm:
        txt+="🎯 **PAIR MEMORY** 🧠\n"
        for p,dat in pm.items():
            if dat["total"]>=1: wrp=dat["wins"]/dat["total"]*100; txt+=f"{'⭐' if wrp>=65 else '⚠️' if wrp<40 else '📊'} {p}: {wrp:.0f}% ({dat['wins']}/{dat['total']})\n"
    bot.send_message(m.chat.id,txt)

@bot.message_handler(commands=['top'])
def top_cmd(m):
    leaders=sorted(DB["stats"].items(),key=lambda x:x[1]["profit"],reverse=True)[:10]
    txt="🏆💎 **TOP TRADERS LEADERBOARD** 💎🏆\n━━━━━━━━━━━━━━━\n"
    for i,(uid_s,stat) in enumerate(leaders,1):
        medal="🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"{i}."
        txt+=f"{medal} {uid_s} → 💰 ${stat['profit']:.2f} | 🔥{stat['streak']} streak\n"
    bot.send_message(m.chat.id,txt)

@bot.message_handler(commands=['setlimits'])
def setlimits_cmd(m):
    try:
        parts=m.text.split(); loss=float(parts[1]); win=float(parts[2])
        DB["limits"][str(m.from_user.id)]={"loss":-abs(loss),"win":abs(win)}; save_db()
        bot.send_message(m.chat.id,f"✅🛡️ **LIMITS SET!** 🛡️✅\n❌ Loss: ${-abs(loss)}\n✅ Win: ${abs(win)}\n💪 Protected!")
    except: bot.send_message(m.chat.id,"⚙️ Usage: /setlimits 3 5\n💡 Example: Stop at -$3 loss, +$5 win (for 20k)")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    cid=c.message.chat.id; data=c.data; ensure_user(cid)
    if data=="quick":
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in ALL_PAIRS[:12]:
            wr=get_pair_wr(cid,p); label=p; 
            if wr: label+=f" {wr:.0f}% {'⭐' if wr>=65 else '⚠️' if wr<40 else ''}"
            mk.add(types.InlineKeyboardButton(label,callback_data=f"pair_{p}"))
        bot.send_message(cid,f"💹🚀 **QUICK TRADE** 🚀💹\n💱 {len(ALL_PAIRS)} pairs\n⭐ = Fav | ⚠️ = BAD <40%\n👇 Pick pair:",reply_markup=mk); return
    if data.startswith("pair_"):
        pair=data.replace("pair_",""); wr=get_pair_wr(cid,pair)
        if wr and wr<40: bot.send_message(cid,f"⚠️😰 **WARNING!** {pair} low WR {wr:.0f}% for you!\n🤔 Bot suggests AVOID! Still trade?")
        mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("🟢 DEMO 💵",callback_data=f"bal_PRACTICE_{pair}"),types.InlineKeyboardButton("🔴 REAL 💰",callback_data=f"bal_REAL_{pair}"))
        bot.send_message(cid,f"✅💱 {pair}\n🏦 Choose account:",reply_markup=mk); return
    if data.startswith("bal_") and not data.startswith("auto_bal_"):
        parts=data.split("_"); bal=parts[1]; pair=parts[2]
        mk=types.InlineKeyboardMarkup(row_width=3); mk.add(types.InlineKeyboardButton("💵 $1",callback_data=f"amt_1_{pair}_{bal}"),types.InlineKeyboardButton("💵 $5",callback_data=f"amt_5_{pair}_{bal}"),types.InlineKeyboardButton("💵 $10",callback_data=f"amt_10_{pair}_{bal}"),types.InlineKeyboardButton("💰 $20",callback_data=f"amt_20_{pair}_{bal}"))
        bot.send_message(cid,f"✅ {pair} {bal}\n💵 **AMOUNT?**",reply_markup=mk); return
    if data.startswith("amt_") and not data.startswith("auto_amt_"):
        parts=data.split("_"); amt=float(parts[1]); pair=parts[2]; bal=parts[3]
        ok_lim,msg_lim=check_daily_limits(cid)
        if not ok_lim: bot.send_message(cid,msg_lim); return
        can_trade,msg=check_news_before_trade(cid)
        if not can_trade: bot.send_message(cid,msg); return
        bot.send_message(cid,f"🔍📊 Scanning {pair}... ⏳"); d=analyze_momentum(pair,god_mode=GOD_MODE.get(cid,False),uid=cid)
        if not d: bot.send_message(cid,"❌😕 No signal! Weak market or GOD filter or BAD pair WR 🚫"); return
        dir_emoji="🟢📈 CALL" if d['dir']=="CALL" else "🔴📉 PUT"
        try:
            plt.figure(figsize=(6,3)); plt.plot(d['df']['close'],color='#FFD700',linewidth=2); plt.title(f"{pair} {d['dir']} {d['conf']:.0f}%"); plt.grid(alpha=0.3); plt.tight_layout(); p="/tmp/c.png"; plt.savefig(p); plt.close()
            bot.send_photo(cid,open(p,'rb'),caption=f"📡💎 **SIGNAL FOUND!** 💎📡\n💱 {pair}\n{dir_emoji} {d['conf']:.0f}%\n💰 Payout {int(d['payout']*100)}% | 💵 ${amt}\n🧠 {d['reason']}\n🚀 Trading...")
        except: bot.send_message(cid,f"📡 {pair} {d['dir']} {d['conf']:.0f}%")
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal)
        if not ok: bot.send_message(cid,"❌💔 Trade Failed! Check IQ connection 📡❌"); return
        bot.send_message(cid,f"✅🚀 Trade Placed! ID {oid} ⏱️ {exp}s\n⏳ Waiting for result... 🎯"); time.sleep(exp+5)
        try:
            with IQ_LOCK: pnl=iq.check_win_v4(oid)
            if pnl>0:
                streak=update_stats(cid,True,pnl); update_pair_mem(cid,pair,True)
                if streak>=5: msg=f"🔥🔥🔥 **MEGA WIN STREAK!!!** 🔥🔥🔥\n💰💰💰 +${pnl:.2f} 💰💰💰\n🚀 {streak} WINS IN A ROW!!! 🚀\n💎💎💎 YOU ARE ON FIRE!!! 💎💎💎\n🎉🎉🎉🎉🎉🎉🎉"
                elif streak>=3: msg=f"🔥🔥 **WIN STREAK!!!** 🔥🔥\n✅💰 +${pnl:.2f} 💰✅\n🔥 {streak} WINS! 🔥\n💪 Keep going champion! 🏆"
                elif streak==2: msg=f"✨✅ **WINNER!** ✅✨\n💵 +${pnl:.2f} 💵\n🔥 2 in a row! 🔥\n🚀 Momentum building! 📈"
                else: msg=f"✅💚 **WIN!!!** 💚✅\n💰 +${pnl:.2f} 💰\n🎯 {pair} {d['dir']} hit! 🎯\n💎 Nice trade! 👏"
                bot.send_message(cid,msg,reply_markup=main_menu(cid))
            else:
                update_stats(cid,False,-amt); update_pair_mem(cid,pair,False)
                loss_msg=[
                    f"❌💔 **LOSS** 💔❌\n💸 -${amt:.2f}\n😔 Don't worry, next one! 💪",
                    f"📉❌ **LOSS** -${amt:.2f}\n🔄 Market tricked us! Recovery next! 🎯",
                    f"❌😅 Oops! -${amt:.2f}\n🧠 Bot learning... Better pair next! 💡"
                ]
                import random; bot.send_message(cid,random.choice(loss_msg),reply_markup=main_menu(cid))
        except: bot.send_message(cid,"⏱️⚠️ Check IQ manually - trade expired!")

    if data=="mystats": 
        s=DB["stats"][str(cid)]; d=DB["daily"][str(cid)]; lim=DB["limits"][str(cid)]; total=s["total"]; wr=(s["wins"]/total*100) if total else 0
        bot.send_message(cid,f"📊💎 W {s['wins']} L {s['loss']} WR {wr:.1f}%\n💰 Today ${d['pnl']:.2f} ({d['trades']}) 🔥{s['streak']} Best {s['best_streak']} P ${s['profit']:.2f}\n🛡️ L${lim['loss']} W${lim['win']}",reply_markup=main_menu(cid)); return
    if data=="top": 
        leaders=sorted(DB["stats"].items(),key=lambda x:x[1]["profit"],reverse=True)[:10]; txt="🏆 **TOP** 🏆\n"
        for i,(uid_s,stat) in enumerate(leaders,1): txt+=f"{i}. {uid_s} ${stat['profit']:.2f} 🔥{stat['streak']}\n"
        bot.send_message(cid,txt,reply_markup=main_menu(cid)); return
    if data=="limits": lim=DB["limits"][str(cid)]; d=DB["daily"][str(cid)]; bot.send_message(cid,f"🛡️💰 **LIMITS**\n📅 Today: ${d['pnl']:.2f}\n❌ Loss Limit: ${lim['loss']}\n✅ Win Limit: ${lim['win']}\n⚙️ Change: /setlimits 3 5",reply_markup=main_menu(cid)); return
    if data=="pair_mem":
        pm=DB["pair_mem"].get(str(cid),{})
        if not pm: bot.send_message(cid,"🎯🤷 No pair data yet!\n📊 Trade to build memory! 🚀"); return
        txt="🎯🧠 **PAIR MEMORY** Bot learns! 🧠🎯\n━━━━━━━━━━━━━━━\n"
        sorted_pairs=sorted(pm.items(),key=lambda x:(x[1]['wins']/x[1]['total'] if x[1]['total'] else 0),reverse=True)
        for p,dat in sorted_pairs:
            wrp=dat["wins"]/dat["total"]*100 if dat["total"] else 0; status="⭐💎 BEST" if wrp>=65 else "⚠️🚫 AVOID" if wrp<40 else "📊 OK"
            txt+=f"{'⭐' if wrp>=65 else '⚠️' if wrp<40 else '📊'} {p}: {wrp:.0f}% {dat['wins']}/{dat['total']} {status}\n"
        txt+="━━━━━━━━━━━━━━━\n🤖 Bot auto skips <40% pairs 🚫"; bot.send_message(cid,txt,reply_markup=main_menu(cid)); return
    if data=="god": GOD_MODE[cid]=not GOD_MODE.get(cid,False); bot.send_message(cid,f"{'👑✨ GOD MODE ON! ✨👑' if GOD_MODE[cid] else '👑💤 GOD MODE OFF'}",reply_markup=main_menu(cid)); return
    if data=="stop_auto": AUTO_RUNNING[cid]=False; bot.send_message(cid,"⏸️🛑 **STOPPED!** 🛑⏸️\n✅ Bot paused! 💤",reply_markup=main_menu(cid)); return

@app.route(f"/{BOT_TOKEN}",methods=['POST'])
def wh():
    data=request.get_data().decode("utf-8"); update=telebot.types.Update.de_json(data)
    if update.message and update.message.from_user.id not in ALLOWED_IDS: return "blocked"
    bot.process_new_updates([update]); return "ok"
@app.route("/")
def home(): return "V53.5 EMOJI READY"
if __name__=="__main__":
    import threading
    threading.Thread(target=lambda:app.run(host="0.0.0.0",port=int(os.getenv("PORT",10000))),daemon=True).start()
    try: bot.remove_webhook()
    except: pass
    bot.infinity_polling(timeout=60,long_polling_timeout=60)
