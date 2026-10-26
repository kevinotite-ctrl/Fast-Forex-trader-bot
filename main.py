import os, time, threading, warnings
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

# 💱 FULL PAIRS LIST - REAL + OTC + CRYPTO
ALL_PAIRS = [
    "EURUSD-OTC","GBPUSD-OTC","EURGBP-OTC","USDJPY-OTC","GBPJPY-OTC","AUDUSD-OTC","USDCHF-OTC","EURJPY-OTC",
    "EURUSD","GBPUSD","EURGBP","USDJPY","GBPJPY","AUDUSD","USDCHF","EURJPY","EURCHF","GBPCHF","AUDJPY","NZDUSD",
    "BTCUSD-OTC","ETHUSD-OTC","GOLD-OTC","SILVER-OTC"
]
REAL_PAIRS = ["EURUSD","GBPUSD","EURGBP","USDJPY","GBPJPY","AUDUSD","USDCHF","EURJPY","EURCHF","GBPCHF","AUDJPY","NZDUSD"]
OTC_ONLY = ["EURUSD-OTC","GBPUSD-OTC","EURGBP-OTC","USDJPY-OTC","GBPJPY-OTC","AUDUSD-OTC","USDCHF-OTC","EURJPY-OTC"]
CRYPTO = ["BTCUSD-OTC","ETHUSD-OTC","GOLD-OTC","SILVER-OTC"]

PAIR_EMOJI = {
    "EURUSD-OTC":"🇪🇺 EUR/USD OTC","GBPUSD-OTC":"🇬🇧 GBP/USD OTC","EURGBP-OTC":"🇪🇺 EUR/GBP OTC",
    "USDJPY-OTC":"🇺🇸 USD/JPY OTC","GBPJPY-OTC":"🇬🇧 GBP/JPY OTC","AUDUSD-OTC":"🇦🇺 AUD/USD OTC",
    "USDCHF-OTC":"🇺🇸 USD/CHF OTC","EURJPY-OTC":"🇪🇺 EUR/JPY OTC",
    "EURUSD":"💹 EUR/USD REAL","GBPUSD":"💹 GBP/USD REAL","EURGBP":"💹 EUR/GBP REAL",
    "USDJPY":"💹 USD/JPY REAL","GBPJPY":"💹 GBP/JPY REAL","AUDUSD":"💹 AUD/USD REAL",
    "USDCHF":"💹 USD/CHF REAL","EURJPY":"💹 EUR/JPY REAL",
    "EURCHF":"💹 EUR/CHF REAL","GBPCHF":"💹 GBP/CHF REAL","AUDJPY":"💹 AUD/JPY REAL","NZDUSD":"💹 NZD/USD REAL",
    "BTCUSD-OTC":"₿ BTC OTC","ETHUSD-OTC":"Ξ ETH OTC","GOLD-OTC":"🥇 GOLD OTC","SILVER-OTC":"🥈 SILVER OTC"
}

STATS = {"balance":100.0,"wins":0,"loss":0,"profit":0.0}
user_states = {}; GOD_MODE = {}; SMART_REC = {}; AUTO_RUNNING = {}
NEWS_FILTER = {}; NEWS_PAUSED = {}; MARKET_MODE = {}
LAST_NEWS_CHECK = 0; HIGH_IMPACT_NEWS = []

def fetch_forex_news():
    global HIGH_IMPACT_NEWS, LAST_NEWS_CHECK
    if time.time() - LAST_NEWS_CHECK < 1800: return HIGH_IMPACT_NEWS
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        r = requests.get(url, timeout=10); data = r.json()
        news_list = []; now = datetime.utcnow()
        for item in data:
            if item.get('country') == 'USD' and item.get('impact') == 'High':
                try:
                    dt_str = item.get('date') + " " + item.get('time', '00:00')
                    news_time = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
                    if now - timedelta(minutes=30) <= news_time <= now + timedelta(hours=2):
                        news_list.append({"title": item.get('title'), "time": news_time})
                except: pass
        HIGH_IMPACT_NEWS = news_list; LAST_NEWS_CHECK = time.time(); return news_list
    except: return []

def is_news_time():
    news = fetch_forex_news(); now = datetime.utcnow()
    for n in news:
        diff = (n['time'] - now).total_seconds() / 60
        if -30 <= diff <= 30: return True, n
    return False, None

def check_news_before_trade(cid):
    if not NEWS_FILTER.get(cid, True): return True, "OK"
    is_news, news_item = is_news_time()
    if is_news: NEWS_PAUSED[cid] = time.time() + 3600; return False, f"📰 RED NEWS: {news_item['title']} {news_item['time'].strftime('%H:%M UTC')} Paused 60min"
    if cid in NEWS_PAUSED and time.time() < NEWS_PAUSED[cid]:
        rem = int((NEWS_PAUSED[cid] - time.time())/60); return False, f"⏸️ News pause {rem}min"
    return True, "OK"

IQ_LOCK = threading.Lock(); IQ_CONNECTED=False; iq=None; PAYOUT_CACHE={}; PAYOUT_TIME=0
try:
    from iqoptionapi.stable_api import IQ_Option
    EMAIL=os.getenv("IQ_EMAIL"); PWD=os.getenv("IQ_PASS")
    if EMAIL and PWD: iq=IQ_Option(EMAIL,PWD); iq.connect(); IQ_CONNECTED=iq.check_connect()
    if IQ_CONNECTED: iq.change_balance("PRACTICE")
except: pass

def iq_reconnect():
    global iq, IQ_CONNECTED
    try:
        from iqoptionapi.stable_api import IQ_Option
        iq=IQ_Option(os.getenv("IQ_EMAIL"),os.getenv("IQ_PASS")); iq.connect(); IQ_CONNECTED=iq.check_connect(); return IQ_CONNECTED
    except: return False

def get_payout(pair):
    global PAYOUT_CACHE, PAYOUT_TIME
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

def calc_rsi(closes, period=7):
    delta=closes.diff(); gain=delta.where(delta>0,0).rolling(period).mean(); loss=-delta.where(delta<0,0).rolling(period).mean()
    return 100-(100/(1+gain/loss))

def analyze_momentum(pair, god_mode=False):
    df=get_candles(pair)
    if df is None: return None
    try:
        close=df['close']; open_=df['open']
        ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean(); rsi=calc_rsi(close,7)
        rsi_now=float(rsi.iloc[-1]); e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1])
        mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100; mom3=(close.iloc[-1]-close.iloc[-4])/close.iloc[-4]*100
        is_green=float(close.iloc[-1])>float(open_.iloc[-1]); payout=get_payout(pair)
        sig="CALL" if is_green else "PUT"; score=75; reason=""
        if mom1>0.02 and mom3>0.05 and is_green and e9>e21 and rsi_now>50 and rsi_now<78: sig="CALL"; score=90; reason=f"🚀 Bull {mom1:.3f}%"
        elif mom1<-0.02 and mom3<-0.05 and not is_green and e9<e21 and rsi_now<50: sig="PUT"; score=90; reason=f"📉 Bear {mom1:.3f}%"
        elif e9>e21 and is_green: sig="CALL"; score=82; reason=f"📈 EMA Bull"
        elif e9<e21 and not is_green: sig="PUT"; score=82; reason=f"📉 EMA Bear"
        if god_mode:
            if score<88 or payout<0.85: return None
            if abs(mom3)<0.08: return None
            score = min(96, score+5); reason += " 👑 GOD"
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
    god = GOD_MODE.get(cid, False); rec = SMART_REC.get(cid, False); news = NEWS_FILTER.get(cid, True); mode = MARKET_MODE.get(cid, "ALL")
    mk=types.InlineKeyboardMarkup(row_width=2)
    mk.add(
        types.InlineKeyboardButton("🚀 QUICK TRADE", callback_data="quick"),
        types.InlineKeyboardButton("🤖 AUTO", callback_data="auto"),
        types.InlineKeyboardButton(f"👑 GOD {'✅' if god else '❌'}", callback_data="god"),
        types.InlineKeyboardButton(f"🧠 REC {'✅' if rec else '❌'}", callback_data="recovery"),
        types.InlineKeyboardButton(f"📰 NEWS {'✅' if news else '❌'}", callback_data="news"),
        types.InlineKeyboardButton(f"💱 {mode}", callback_data="market"),
        types.InlineKeyboardButton("📊 DASH", callback_data="pnl"),
        types.InlineKeyboardButton("🎯 PAIRS", callback_data="pairs"),
        types.InlineKeyboardButton("⏸️ STOP", callback_data="stop_auto")
    )
    return mk

@bot.message_handler(commands=['adduser'])
def add_user(m):
    if m.from_user.id != OWNER_ID: return
    try: new_id = int(m.text.split()[1]); 
    except: bot.send_message(m.chat.id, "Usage: /adduser ID"); return
    if new_id not in ALLOWED_IDS: ALLOWED_IDS.append(new_id); bot.send_message(m.chat.id, f"✅ Added {new_id} Total {len(ALLOWED_IDS)}")
    else: bot.send_message(m.chat.id, "Already")

@bot.message_handler(commands=['removeuser'])
def remove_user(m):
    if m.from_user.id != OWNER_ID: return
    try: rem_id = int(m.text.split()[1])
    except: return
    if rem_id == OWNER_ID: bot.send_message(m.chat.id, "❌ Can't remove owner"); return
    if rem_id in ALLOWED_IDS: ALLOWED_IDS.remove(rem_id); bot.send_message(m.chat.id, f"✅ Removed {rem_id}")

@bot.message_handler(commands=['users'])
def list_users(m):
    if m.from_user.id != OWNER_ID: return
    txt = f"🔒 Users ({len(ALLOWED_IDS)}):\n"; 
    for uid in ALLOWED_IDS: txt += f"• {uid} {'👑' if uid==OWNER_ID else ''}\n"
    bot.send_message(m.chat.id, txt)

@bot.message_handler(commands=['id'])
def get_id_cmd(m): bot.send_message(m.chat.id, f"ID: {m.from_user.id}")

@bot.message_handler(commands=['start'])
def start(m):
    if m.from_user.id not in ALLOWED_IDS: bot.send_message(m.chat.id, f"⛔ PRIVATE ID: {m.from_user.id}"); return
    NEWS_FILTER.setdefault(m.chat.id, True); MARKET_MODE.setdefault(m.chat.id, "ALL")
    txt=f"""🤖 **V52 REAL+OTC+CRYPTO** 🔒
Owner {OWNER_ID} | IQ {'✅' if IQ_CONNECTED else '❌'}
Bal ${STATS['balance']:.2f} W/L {STATS['wins']}/{STATS['loss']} P ${STATS['profit']:.2f}
Mode {MARKET_MODE.get(m.chat.id)} | News {'ON' if NEWS_FILTER.get(m.chat.id) else 'OFF'}
👇 SELECT
"""
    bot.send_message(m.chat.id, txt, reply_markup=main_menu(m.chat.id), parse_mode="Markdown")

def auto_loop(cid, pair, bal, base_amt):
    loss_streak=0; curr_amt=base_amt
    while AUTO_RUNNING.get(cid, False):
        try:
            can_trade, msg = check_news_before_trade(cid)
            if not can_trade: bot.send_message(cid, msg); time.sleep(1800); continue
            if MARKET_MODE.get(cid, "ALL") == "ALL":
                best_pair=pair; best_payout=0
                for test_p in ALL_PAIRS:
                    pay=get_payout(test_p)
                    if pay>best_payout: best_payout=pay; best_pair=test_p
                if best_payout>get_payout(pair)+0.05: bot.send_message(cid, f"💹 Switched to {best_pair} {int(best_payout*100)}%"); pair=best_pair
            d=analyze_momentum(pair, god_mode=GOD_MODE.get(cid,False))
            if not d: time.sleep(10); continue
            if d['payout']<0.80: time.sleep(15); continue
            bot.send_message(cid, f"🤖 AUTO {PAIR_EMOJI.get(pair,pair)} {d['dir']} ${curr_amt} {d['conf']:.0f}%")
            ok,oid,exp=iq_trade(pair,d['dir'],curr_amt,bal)
            if not ok: time.sleep(5); continue
            time.sleep(exp+5)
            with IQ_LOCK: pnl=iq.check_win_v4(oid)
            if pnl>0: STATS['wins']+=1; STATS['profit']+=pnl; curr_amt=base_amt; loss_streak=0; bot.send_message(cid, f"✅ WIN +${pnl:.2f}")
            else: STATS['loss']+=1; STATS['profit']-=curr_amt; loss_streak+=1; bot.send_message(cid, f"❌ LOSS -${curr_amt:.0f} Streak {loss_streak}")
            if SMART_REC.get(cid, False):
                if loss_streak==1: curr_amt=round(base_amt*2.2,2)
                elif loss_streak==2: curr_amt=round(base_amt*5,2)
                else: time.sleep(600); curr_amt=base_amt; loss_streak=0
            if STATS['wins']>=3 and STATS['profit']>=20: bot.send_message(cid, "🔒 Profit Lock Paused"); AUTO_RUNNING[cid]=False; break
            time.sleep(10)
        except Exception as e: print(e); time.sleep(5)

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    cid=c.message.chat.id
    if c.from_user.id not in ALLOWED_IDS: return
    data=c.data
    if data=="market":
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🔥 OTC 24/7", callback_data="mode_OTC"), types.InlineKeyboardButton("💹 REAL Mon-Fri", callback_data="mode_REAL"),
               types.InlineKeyboardButton("🌍 ALL Best Payout", callback_data="mode_ALL"), types.InlineKeyboardButton("₿ CRYPTO/GOLD", callback_data="mode_CRYPTO"))
        bot.send_message(cid, "💱 SELECT MARKET", reply_markup=mk); return
    if data.startswith("mode_"):
        mode=data.replace("mode_",""); MARKET_MODE[cid]=mode; bot.send_message(cid, f"✅ Market {mode}", reply_markup=main_menu(cid)); return
    if data=="quick":
        mode=MARKET_MODE.get(cid, "ALL")
        if mode=="OTC": show=OTC_ONLY
        elif mode=="REAL": show=REAL_PAIRS
        elif mode=="CRYPTO": show=CRYPTO
        else: show=ALL_PAIRS
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in show: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"pair_{p}"))
        bot.send_message(cid, f"💹 QUICK {mode} ({len(show)})", reply_markup=mk); return
    if data=="auto":
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in ALL_PAIRS[:8]: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"auto_pair_{p}"))
        bot.send_message(cid, "🤖 AUTO SELECT", reply_markup=mk); return
    if data.startswith("auto_pair_"):
        pair=data.replace("auto_pair_","")
        mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("🟢 DEMO", callback_data=f"auto_bal_PRACTICE_{pair}"), types.InlineKeyboardButton("🔴 REAL", callback_data=f"auto_bal_REAL_{pair}"))
        bot.send_message(cid, f"✅ {pair} ACCOUNT?", reply_markup=mk); return
    if data.startswith("auto_bal_"):
        parts=data.split("_"); bal=parts[2]; pair=parts[3]
        mk=types.InlineKeyboardMarkup(row_width=3); mk.add(types.InlineKeyboardButton("$1", callback_data=f"auto_amt_1_{pair}_{bal}"), types.InlineKeyboardButton("$5", callback_data=f"auto_amt_5_{pair}_{bal}"), types.InlineKeyboardButton("$10", callback_data=f"auto_amt_10_{pair}_{bal}"))
        bot.send_message(cid, f"✅ {pair} {bal} AMOUNT?", reply_markup=mk); return
    if data.startswith("auto_amt_"):
        parts=data.split("_"); amt=float(parts[2]); pair=parts[3]; bal=parts[4]
        can_trade, msg = check_news_before_trade(cid)
        if not can_trade: bot.send_message(cid, msg); return
        AUTO_RUNNING[cid]=True; bot.send_message(cid, f"🚀 AUTO {pair} ${amt} {bal}"); threading.Thread(target=auto_loop, args=(cid,pair,bal,amt), daemon=True).start(); return
    if data=="god": GOD_MODE[cid]=not GOD_MODE.get(cid,False); bot.send_message(cid, f"👑 GOD {'ON' if GOD_MODE[cid] else 'OFF'}", reply_markup=main_menu(cid)); return
    if data=="recovery": SMART_REC[cid]=not SMART_REC.get(cid,False); bot.send_message(cid, f"🧠 REC {'ON' if SMART_REC[cid] else 'OFF'}", reply_markup=main_menu(cid)); return
    if data=="news": NEWS_FILTER[cid]=not NEWS_FILTER.get(cid, True); bot.send_message(cid, f"📰 NEWS {'ON' if NEWS_FILTER[cid] else 'OFF'}", reply_markup=main_menu(cid)); return
    if data=="pnl":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0
        news_list = fetch_forex_news(); news_txt = "\n".join([f"{n['title']} {n['time'].strftime('%H:%M')}" for n in news_list]) if news_list else "No high USD news"
        bot.send_message(cid, f"📊 W {STATS['wins']} L {STATS['loss']} WR {wr:.1f}% P ${STATS['profit']:.2f}\nMode {MARKET_MODE.get(cid)} News {NEWS_FILTER.get(cid)}\n\n📰 {news_txt}", reply_markup=main_menu(cid)); return
    if data=="stop_auto": AUTO_RUNNING[cid]=False; bot.send_message(cid, "⏸️ Stopped", reply_markup=main_menu(cid)); return
    if data=="pairs":
        mode=MARKET_MODE.get(cid, "ALL")
        if mode=="OTC": show=OTC_ONLY
        elif mode=="REAL": show=REAL_PAIRS
        elif mode=="CRYPTO": show=CRYPTO
        else: show=ALL_PAIRS
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in show: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"pair_{p}"))
        bot.send_message(cid, f"🎯 {mode} PAIRS", reply_markup=mk); return
    if data.startswith("pair_"):
        pair=data.replace("pair_","")
        mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("🟢 DEMO", callback_data=f"bal_PRACTICE_{pair}"), types.InlineKeyboardButton("🔴 REAL", callback_data=f"bal_REAL_{pair}"))
        bot.send_message(cid, f"✅ {PAIR_EMOJI.get(pair,pair)} ACCOUNT?", reply_markup=mk); return
    if data.startswith("bal_") and not data.startswith("auto_bal_"):
        parts=data.split("_"); bal=parts[1]; pair=parts[2]
        mk=types.InlineKeyboardMarkup(row_width=3); mk.add(types.InlineKeyboardButton("$1", callback_data=f"amt_1_{pair}_{bal}"), types.InlineKeyboardButton("$5", callback_data=f"amt_5_{pair}_{bal}"), types.InlineKeyboardButton("$10", callback_data=f"amt_10_{pair}_{bal}"), types.InlineKeyboardButton("$20", callback_data=f"amt_20_{pair}_{bal}"))
        bot.send_message(cid, f"✅ {PAIR_EMOJI.get(pair,pair)} {bal} AMOUNT?", reply_markup=mk); return
    if data.startswith("amt_") and not data.startswith("auto_amt_"):
        parts=data.split("_"); amt=float(parts[1]); pair=parts[2]; bal=parts[3]
        can_trade, msg = check_news_before_trade(cid)
        if not can_trade: bot.send_message(cid, msg); return
        bot.send_message(cid, f"🔍 {PAIR_EMOJI.get(pair,pair)}..."); d=analyze_momentum(pair, god_mode=GOD_MODE.get(cid,False))
        if not d: bot.send_message(cid, "No signal"); return
        dir_emoji = "🟢 CALL" if d['dir']=="CALL" else "🔴 PUT"
        try: plt.figure(figsize=(6,3)); plt.plot(d['df']['close'], color='#FFD700', linewidth=2); plt.title(f"{pair} {d['dir']} {d['conf']:.0f}%"); plt.grid(alpha=0.3); plt.tight_layout(); p="/tmp/c.png"; plt.savefig(p); plt.close(); bot.send_photo(cid, open(p,'rb'), caption=f"📡 {PAIR_EMOJI.get(pair,pair)} {dir_emoji} {d['conf']:.0f}% Payout {int(d['payout']*100)}% ${amt}\n{d['reason']}")
        except: bot.send_message(cid, f"📡 {pair} {d['dir']} {d['conf']:.0f}%")
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal)
        if not ok: bot.send_message(cid, "❌ Trade Failed"); return
        bot.send_message(cid, f"✅ Placed {oid} {exp}s"); time.sleep(exp+5)
        try:
            with IQ_LOCK: pnl=iq.check_win_v4(oid)
            if pnl>0: STATS['wins']+=1; STATS['balance']+=pnl; STATS['profit']+=pnl; bot.send_message(cid, f"✅ WIN +${pnl:.2f}")
            else: STATS['loss']+=1; STATS['balance']-=amt; STATS['profit']-=amt; bot.send_message(cid, f"❌ LOSS -${amt:.2f}")
        except: bot.send_message(cid, "⏱️ Check IQ")

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def wh():
    data = request.get_data().decode("utf-8"); update = telebot.types.Update.de_json(data)
    if update.message and update.message.from_user.id not in ALLOWED_IDS: return "blocked"
    if update.callback_query and update.callback_query.from_user.id not in ALLOWED_IDS: return "blocked"
    bot.process_new_updates([update]); return "ok"

@app.route("/")
def home():
    u=os.getenv("RENDER_EXTERNAL_URL")
    if u:
        try: requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={u}/{BOT_TOKEN}", timeout=5)
        except: pass
    return f"V52 REAL+OTC OWNER {OWNER_ID} READY"

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000))), daemon=True).start()
    try: bot.remove_webhook()
    except: pass
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
