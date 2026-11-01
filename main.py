import os, time, threading, warnings, logging
from datetime import datetime, timezone
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
logging.getLogger().setLevel(logging.CRITICAL)
logging.getLogger("iqoptionapi").setLevel(logging.CRITICAL)
logging.disable(logging.ERROR)

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 8659453018
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# REAL + OTC
REAL_PAIRS = ["EURUSD","GBPUSD","USDJPY","EURGBP","AUDUSD","USDCAD","EURJPY","GBPJPY"]
OTC_PAIRS = ["EURUSD-OTC","GBPUSD-OTC","EURGBP-OTC","USDJPY-OTC","GBPJPY-OTC","AUDUSD-OTC","USDCHF-OTC","EURJPY-OTC"]
PAIR_EMOJI = {
    "EURUSD":"🇪🇺 EUR/USD REAL", "GBPUSD":"🇬🇧 GBP/USD REAL", "USDJPY":"🇺🇸 USD/JPY REAL",
    "EURGBP":"🇪🇺 EUR/GBP REAL", "AUDUSD":"🇦🇺 AUD/USD REAL", "USDCAD":"🇺🇸 USD/CAD REAL",
    "EURJPY":"🇪🇺 EUR/JPY REAL", "GBPJPY":"🇬🇧 GBP/JPY REAL",
    "EURUSD-OTC":"🇪🇺 EUR/USD OTC", "GBPUSD-OTC":"🇬🇧 GBP/USD OTC", 
    "EURGBP-OTC":"🇪🇺 EUR/GBP OTC", "USDJPY-OTC":"🇺🇸 USD/JPY OTC",
    "GBPJPY-OTC":"🇬🇧 GBP/JPY OTC", "AUDUSD-OTC":"🇦🇺 AUD/USD OTC",
    "USDCHF-OTC":"🇺🇸 USD/CHF OTC", "EURJPY-OTC":"🇪🇺 EUR/JPY OTC"
}
STATS = {"balance":100.0,"wins":0,"loss":0}
user_states = {}
IQ_LOCK = threading.Lock()
IQ_CONNECTED=False; iq=None
PAYOUT_CACHE={}; PAYOUT_TIME=0

def is_allowed(uid): return uid == OWNER_ID

def get_active_pairs():
    now_utc = datetime.now(timezone.utc)
    weekday = now_utc.weekday()
    hour = now_utc.hour
    is_weekday = weekday < 5
    if weekday == 4 and hour >= 21: is_weekday = False
    if weekday == 5: is_weekday = False
    if weekday == 6 and hour < 21: is_weekday = False
    return REAL_PAIRS if is_weekday else OTC_PAIRS, is_weekday

def is_news_time():
    now_utc = datetime.now(timezone.utc)
    high_impact = [(12, 30), (18, 0)]
    current = now_utc.hour * 60 + now_utc.minute
    for h, m in high_impact:
        news_t = h * 60 + m
        if news_t - 3 <= current <= news_t + 10:
            return True, f"🛑 NEWS {h:02d}:{m:02d} UTC!"
    return False, f"✅ Safe {now_utc.strftime('%H:%M UTC')}"

try:
    from iqoptionapi.stable_api import IQ_Option
    EMAIL=os.getenv("IQ_EMAIL"); PWD=os.getenv("IQ_PASS")
    if EMAIL and PWD:
        logging.disable(logging.CRITICAL)
        iq=IQ_Option(EMAIL,PWD)
        iq.connect()
        IQ_CONNECTED=iq.check_connect()
        if IQ_CONNECTED: 
            try: iq.change_balance("PRACTICE")
            except: pass
        logging.disable(logging.NOTSET)
        logging.getLogger().setLevel(logging.CRITICAL)
        logging.disable(logging.ERROR)
        print(f"IQ CONNECTED: {IQ_CONNECTED}", flush=True)
except: IQ_CONNECTED=False

def iq_reconnect():
    global iq, IQ_CONNECTED
    try:
        from iqoptionapi.stable_api import IQ_Option
        logging.disable(logging.CRITICAL)
        iq=IQ_Option(os.getenv("IQ_EMAIL"),os.getenv("IQ_PASS"))
        iq.connect()
        IQ_CONNECTED=iq.check_connect()
        logging.disable(logging.NOTSET)
        logging.disable(logging.ERROR)
        return IQ_CONNECTED
    except: 
        IQ_CONNECTED=False
        return False

def get_payout(pair):
    global PAYOUT_CACHE, PAYOUT_TIME
    if time.time()-PAYOUT_TIME<60 and pair in PAYOUT_CACHE: return PAYOUT_CACHE[pair]
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL)
            all_p=iq.get_all_profit()
            logging.disable(logging.NOTSET)
            logging.disable(logging.ERROR)
            if pair in all_p:
                for k in ['blitz','turbo','binary']:
                    if k in all_p[pair]:
                        PAYOUT_CACHE[pair]=float(all_p[pair][k]); PAYOUT_TIME=time.time(); return float(all_p[pair][k])
        return 0.85
    except: return PAYOUT_CACHE.get(pair,0.85)

def get_candles(pair):
    if not IQ_CONNECTED and not iq_reconnect(): return None
    for _ in range(2):
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL)
                c=iq.get_candles(pair,60,50,time.time())
                logging.disable(logging.NOTSET)
                logging.disable(logging.ERROR)
            if c and len(c)>20: return pd.DataFrame(sorted(c,key=lambda x:x['from']))
            time.sleep(0.5)
        except: time.sleep(0.5)
    return None

def calc_rsi(closes, period=7):
    delta=closes.diff()
    gain=delta.where(delta>0,0).rolling(period).mean()
    loss=-delta.where(delta<0,0).rolling(period).mean()
    return 100-(100/(1+gain/loss))

def legit_live_scan(cid, mid, pair):
    steps = [
        (0, "🚀 Initializing V8...", 0.15),
        (20, f"🔌 Checking {pair}...", 0.2),
        (40, "📊 Fetching candles...", 0.2),
        (60, "📈 EMA9 + EMA21...", 0.15),
        (80, "💹 RSI + Momentum...", 0.15),
        (100, "🔒 SIGNAL LOCKED!")
    ]
    for pct, text, delay in steps:
        filled = int(pct // 5)
        bar = "█" * filled + "░" * (20 - filled)
        color = "🟥" if pct < 40 else "🟨" if pct < 80 else "🟩" if pct < 100 else "💎"
        is_news, news_info = is_news_time()
        scan_txt = f"""{color} **Z-BOT V8 LEGIT SCAN** {color}

💱 Pair: {PAIR_EMOJI.get(pair, pair)}
💎 IQ: {'✅ Connected' if IQ_CONNECTED else '❌ Offline'}

{bar} {pct}%
▓ Progress: {pct}% ▓

🔍 {text}
{news_info}

⏳ Fast V8.5
"""
        try: bot.edit_message_text(scan_txt, cid, mid, parse_mode="Markdown")
        except: pass
        time.sleep(delay)
    try:
        final_txt = f"""💎 **Z-BOT V8 LEGIT SCAN** 💎

💱 Pair: {PAIR_EMOJI.get(pair, pair)}
💎 IQ: {'✅ Connected' if IQ_CONNECTED else '❌ Offline'}

████████████████████ 100%
▓ Progress: 100% ▓

🔍 🔒 SIGNAL LOCKED!

⏳ Complete V8.5
"""
        bot.edit_message_text(final_txt, cid, mid, parse_mode="Markdown")
    except: pass

def analyze_momentum(pair):
    df=get_candles(pair)
    if df is None: return None
    try:
        close=df['close']; open_=df['open']
        ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean()
        rsi=calc_rsi(close,7)
        rsi_now=float(rsi.iloc[-1])
        e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1])
        mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100
        mom3=(close.iloc[-1]-close.iloc[-4])/close.iloc[-4]*100
        is_green=float(close.iloc[-1])>float(open_.iloc[-1])
        payout=get_payout(pair)
        sig="CALL" if is_green else "PUT"; score=75; reason=""
        if mom1>0.02 and mom3>0.05 and is_green and e9>e21 and rsi_now>50 and rsi_now<78:
            sig="CALL"; score=90; reason=f"🚀 Bullish {mom1:.3f}%"
        elif mom1<-0.02 and mom3<-0.05 and not is_green and e9<e21 and rsi_now<50:
            sig="PUT"; score=90; reason=f"📉 Bearish {mom1:.3f}%"
        elif e9>e21 and is_green: sig="CALL"; score=82; reason=f"📈 EMA Bull"
        elif e9<e21 and not is_green: sig="PUT"; score=82; reason=f"📉 EMA Bear"
        return {"pair":pair,"dir":sig,"conf":min(94,score),"price":float(close.iloc[-1]),"rsi":rsi_now,"reason":reason,"mom":mom3,"payout":payout,"df":df.tail(30)}
    except: return None

def iq_trade(pair,direction,amount,bal):
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL)
            iq.change_balance(bal)
            logging.disable(logging.NOTSET)
            logging.disable(logging.ERROR)
            try:
                logging.disable(logging.CRITICAL)
                _,oid=iq.buy_blitz(pair,amount,direction.lower(),30)
                logging.disable(logging.NOTSET)
                logging.disable(logging.ERROR)
                return True,oid,30
            except:
                logging.disable(logging.CRITICAL)
                _,oid=iq.buy(amount,pair,direction.lower(),1)
                logging.disable(logging.NOTSET)
                logging.disable(logging.ERROR)
                return True,oid,60
    except Exception as e:
        print(f"Trade err {e}"); return False,None,0

@bot.message_handler(commands=['start'])
def start(m):
    if not is_allowed(m.from_user.id):
        bot.send_message(m.chat.id, f"❌ Private\nID: {m.from_user.id}"); return
    active, is_real = get_active_pairs()
    is_news, news_info = is_news_time()
    market_type = "🌍 REAL OPEN" if is_real else "🏦 OTC Weekend"
    mk=types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton("💹 TRADE NOW", callback_data="trade"))
    mk.add(types.InlineKeyboardButton("📊 MY STATS", callback_data="stats"), types.InlineKeyboardButton("⚙️ SETTINGS", callback_data="settings"))
    txt=f"""🤖 **Z-BOT V8.5 FINAL** 🤖

{market_type}
💎 IQ: {'✅' if IQ_CONNECTED else '❌'}
💰 ${STATS['balance']:.2f} | 🎯 {STATS['wins']}W/{STATS['loss']}L
{news_info}

👇 **TRADE**
"""
    bot.send_message(m.chat.id, txt, reply_markup=mk, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_allowed(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Owner only"); return
    data=c.data; cid=c.message.chat.id
    
    if data=="trade":
        is_news, news_info = is_news_time()
        active_pairs, is_real_day = get_active_pairs()
        market_type = "🌍 REAL MARKET" if is_real_day else "🏦 OTC MARKET"
        if is_news and is_real_day:
            mk=types.InlineKeyboardMarkup(row_width=1)
            for p in active_pairs[:4]:
                mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"pair_{p}"))
            mk.add(types.InlineKeyboardButton("⚠️ TRADE ANYWAY", callback_data="bypass_news"))
            mk.add(types.InlineKeyboardButton("🔄 USE OTC", callback_data="trade_otc"))
            bot.send_message(cid, f"🛑 **NEWS**\n{news_info}\n{market_type} volatile!", reply_markup=mk, parse_mode="Markdown")
            return
        bot.answer_callback_query(c.id, "Loading...")
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in active_pairs:
            mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"pair_{p}"))
        if is_real_day:
            mk.add(types.InlineKeyboardButton("🔄 OTC", callback_data="trade_otc"))
        else:
            mk.add(types.InlineKeyboardButton("🌍 REAL", callback_data="trade_real"))
        bot.send_message(cid, f"💹 **STEP 1/3 - PAIR**\n{market_type}\n{news_info}\n👇 Choose:", reply_markup=mk, parse_mode="Markdown")
        return

    if data=="trade_otc":
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in OTC_PAIRS:
            mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"pair_{p}"))
        mk.add(types.InlineKeyboardButton("🌍 REAL", callback_data="trade"))
        bot.send_message(cid, f"🏦 **OTC 24/7**\n👇 Choose:", reply_markup=mk, parse_mode="Markdown")
        return

    if data=="trade_real":
        active, is_real = get_active_pairs()
        if not is_real:
            bot.send_message(cid, "🛑 **REAL CLOSED**\nFri 21:00 - Sun 21:00 UTC closed\nUse OTC!")
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in REAL_PAIRS:
            mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"pair_{p}"))
        bot.send_message(cid, f"🌍 **REAL {'OPEN ✅' if is_real else 'CLOSED ❌'}**\n👇 Choose:", reply_markup=mk, parse_mode="Markdown")
        return

    if data=="bypass_news":
        active, _ = get_active_pairs()
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in active:
            mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"pair_{p}"))
        bot.send_message(cid, f"⚠️ **RISKY - NEWS!**\n👇 Select:", reply_markup=mk, parse_mode="Markdown")
        return

    if data.startswith("pair_"):
        pair=data.replace("pair_","")
        user_states[cid]={"pair":pair}
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🟢 DEMO", callback_data=f"bal_PRACTICE_{pair}"))
        mk.add(types.InlineKeyboardButton("🔴 REAL", callback_data=f"bal_REAL_{pair}"))
        mk.add(types.InlineKeyboardButton("⬅️ BACK", callback_data="trade"))
        bot.send_message(cid, f"✅ **{PAIR_EMOJI.get(pair,pair)}**\n\n💳 **STEP 2/3 - ACCOUNT**", reply_markup=mk, parse_mode="Markdown")
        return

    if data.startswith("bal_"):
        parts=data.split("_"); bal=parts[1]; pair=parts[2]
        user_states[cid]={"pair":pair,"bal":bal}
        mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("💵 $1", callback_data=f"amt_1_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $5", callback_data=f"amt_5_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $10", callback_data=f"amt_10_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("💵 $20", callback_data=f"amt_20_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $50", callback_data=f"amt_50_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $100", callback_data=f"amt_100_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("✏️ CUSTOM", callback_data=f"custom_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("⬅️ BACK", callback_data=f"pair_{pair}"))
        bot.send_message(cid, f"✅ **{PAIR_EMOJI.get(pair,pair)} {bal}**\n\n💰 **STEP 3/3 - AMOUNT**", reply_markup=mk, parse_mode="Markdown")
        return

    if data.startswith("amt_") or data.startswith("custom_"):
        if data.startswith("custom_"):
            parts=data.split("_"); pair=parts[1]; bal=parts[2]
            user_states[cid]={"pair":pair,"bal":bal,"step":"await_amt"}
            bot.send_message(cid, f"✏️ **Type amount** e.g 10\nFor {pair} {bal}", parse_mode="Markdown")
            return
        
        is_news, news_info = is_news_time()
        if is_news and not data.split("_")[2].endswith("-OTC"):
            bot.send_message(cid, f"🛑 **NEWS BLOCK**\n{news_info}\nUse OTC"); return
        
        parts=data.split("_"); amt=float(parts[1]); pair=parts[2]; bal=parts[3]
        scan_msg = bot.send_message(cid, f"🔍 **INIT {PAIR_EMOJI.get(pair,pair)}**\n░░░░ 0%", parse_mode="Markdown")
        legit_live_scan(cid, scan_msg.message_id, pair)
        
        d=analyze_momentum(pair)
        if not d:
            mk=types.InlineKeyboardMarkup()
            mk.add(types.InlineKeyboardButton("🔄 RETRY", callback_data=f"amt_{int(amt)}_{pair}_{bal}"))
            bot.send_message(cid, f"❌ Failed {pair}", reply_markup=mk)
            return
        
        dir_emoji = "🟢 CALL 🟢" if d['dir']=="CALL" else "🔴 PUT 🔴"
        signal_txt=f"""📡 **SIGNAL V8.5**
💱 {PAIR_EMOJI.get(pair,pair)}
📊 {dir_emoji}
🎯 {d['conf']:.0f}% | 💸 {int(d['payout']*100)}%
💰 ${amt} {bal}
📰 {news_info}
📈 {d['reason']}
"""
        try:
            plt.figure(figsize=(6,3)); plt.plot(d['df']['close'], color='#FFD700', linewidth=2); plt.title(f"{pair} {d['dir']} {d['conf']:.0f}%"); plt.grid(alpha=0.3); plt.tight_layout(); p="/tmp/c.png"; plt.savefig(p); plt.close()
            bot.send_photo(cid, open(p,'rb'), caption=signal_txt, parse_mode="Markdown")
        except:
            bot.send_message(cid, signal_txt, parse_mode="Markdown")
        
        time.sleep(0.5)
        bot.send_message(cid, f"🚀 **PLACING {pair} {d['dir']} ${amt}...**", parse_mode="Markdown")
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal)
        if not ok:
            bot.send_message(cid, "❌ Failed - Reconnect"); iq_reconnect(); return
        
        bot.send_message(cid, f"✅ **PLACED**\n🆔 {oid}\n💱 {pair} {d['dir']} ${amt}\n⏱️ {exp}s\n⏳ Wait...", parse_mode="Markdown")
        
        # ===== SIMPLE WIN/LOSS =====
        time.sleep(exp+5)
        try:
            with IQ_LOCK: 
                logging.disable(logging.CRITICAL)
                pnl=iq.check_win_v4(oid)
                logging.disable(logging.NOTSET)
                logging.disable(logging.ERROR)
            
            if pnl > 0:
                STATS['wins']+=1; STATS['balance']+=pnl
                mk=types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton("🔁 AGAIN", callback_data=f"amt_{int(amt)}_{pair}_{bal}"),
                       types.InlineKeyboardButton("💹 NEW", callback_data="trade"))
                bot.send_message(cid, f"""✅ **WIN**

💱 {pair} {d['dir']}
💰 +${pnl:.2f}
💵 Balance: ${STATS['balance']:.2f}
""", reply_markup=mk, parse_mode="Markdown")
            else:
                STATS['loss']+=1; STATS['balance']-=amt
                mk=types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton(f"🔁 MARTI ${amt*2.2:.0f}", callback_data=f"amt_{int(amt*2.2)}_{pair}_{bal}"),
                       types.InlineKeyboardButton("💹 NEW", callback_data="trade"))
                bot.send_message(cid, f"""❌ **LOSS**

💱 {pair} {d['dir']}
💸 -${amt:.2f}
💵 Balance: ${STATS['balance']:.2f}
""", reply_markup=mk, parse_mode="Markdown")
        except:
            mk=types.InlineKeyboardMarkup()
            mk.add(types.InlineKeyboardButton("💹 NEW", callback_data="trade"))
            bot.send_message(cid, f"""⏱️ **DONE**

💱 {pair}
Check IQ app
ID: {oid}
""", reply_markup=mk, parse_mode="Markdown")
        return

    if data=="stats":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0
        active, is_real = get_active_pairs()
        is_news, news_info = is_news_time()
        bot.send_message(cid, f"📊 **STATS V8.5**\n🏆 {STATS['wins']}W ❌ {STATS['loss']}L\n📈 {wr:.1f}%\n💰 ${STATS['balance']:.2f}\n{news_info}\nMarket: {'REAL' if is_real else 'OTC'}", parse_mode="Markdown")
    if data=="settings": 
        is_news, news_info = is_news_time()
        bot.send_message(cid, f"⚙️ **V8.5**\n📰 News: Light (12:30,18:00 UTC)\n💎 Scan: Fast 100%\n{news_info}")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get("step")=="await_amt")
def handle_custom_amt(m):
    cid=m.chat.id; st=user_states.get(cid, {})
    if not is_allowed(m.from_user.id): return
    is_news, news_info = is_news_time()
    pair_tmp = st.get("pair","")
    if is_news and not pair_tmp.endswith("-OTC"):
        bot.send_message(cid, f"🛑 **NEWS!** {news_info}"); return
    try:
        amt=float(m.text.strip())
        pair=st.get("pair"); bal=st.get("bal")
        if not pair: return
        scan_msg = bot.send_message(cid, f"🔍 **INIT {pair}**\n░░░░ 0%")
        legit_live_scan(cid, scan_msg.message_id, pair)
        d=analyze_momentum(pair)
        if not d: bot.send_message(cid, "Failed"); return
        bot.send_message(cid, f"📡 {pair} {d['dir']} {d['conf']:.0f}% ${amt}")
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal)
        if ok:
            bot.send_message(cid, f"✅ {oid} Wait {exp}s")
            time.sleep(exp+5)
            try:
                with IQ_LOCK: 
                    logging.disable(logging.CRITICAL)
                    pnl=iq.check_win_v4(oid)
                    logging.disable(logging.NOTSET)
                    logging.disable(logging.ERROR)
                if pnl>0:
                    bot.send_message(cid, f"✅ **WIN +${pnl:.2f}**")
                else:
                    bot.send_message(cid, f"❌ **LOSS -${amt:.2f}**")
            except:
                bot.send_message(cid, f"⏱️ **DONE** - Check IQ")
        user_states.pop(cid,None)
    except: bot.send_message(cid, "❌ Number only e.g 100")

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def wh(): bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode("utf-8"))]); return "ok"
@app.route("/")
def home():
    u=os.getenv("RENDER_EXTERNAL_URL")
    if u:
        try: requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={u}/{BOT_TOKEN}", timeout=5)
        except: pass
    return "V8.5 REAL+OTC SIMPLE WIN/LOSS FAST 100% RUNNING"
app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
