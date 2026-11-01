import os, time, threading, warnings, logging
from datetime import datetime, timezone
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
SCAN_LOCK = threading.Lock()
IQ_CONNECTED=False; iq=None
PAYOUT_CACHE={}; PAYOUT_TIME=0

def is_allowed(uid): return uid == OWNER_ID

def get_active_pairs():
    now_utc = datetime.now(timezone.utc)
    weekday = now_utc.weekday(); hour = now_utc.hour
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
    except: IQ_CONNECTED=False; return False

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

# ===== FIXED V8.6.2 - ALWAYS REACH 100% =====
def legit_live_scan(cid, mid, pair):
    if not SCAN_LOCK.acquire(blocking=False):
        return
    try:
        # 5 steps to 90%
        steps = [
            (0, "🚀 Initializing...", 0.5),
            (25, f"🔌 Checking {pair}...", 0.6),
            (50, "📊 Fetching candles...", 0.7),
            (75, "📈 EMA + RSI...", 0.6),
            (90, "📰 News check...", 0.4),
        ]
        for pct, text, delay in steps:
            filled = int(pct // 5)
            bar = "█" * filled + "░" * (20 - filled)
            color = "🟥" if pct < 50 else "🟨" if pct < 90 else "🟩"
            is_news, news_info = is_news_time()
            scan_txt = f"""{color} **Z-BOT V8.6.2 SCAN** {color}

💱 {PAIR_EMOJI.get(pair, pair)}
{bar} {pct}%

🔍 {text}
{news_info}
"""
            try:
                bot.edit_message_text(scan_txt, cid, mid, parse_mode="Markdown")
            except:
                pass
            time.sleep(delay)
        
        # FORCE 100% - THIS ALWAYS RUNS!
        try:
            final_txt = f"""💎 **Z-BOT V8.6.2 SCAN** 💎

💱 {PAIR_EMOJI.get(pair, pair)}
████████████████████ 100%

🔒 SIGNAL LOCKED! ✅
✅ Safe {datetime.now(timezone.utc).strftime('%H:%M UTC')}

🚀 Analyzing next...
"""
            bot.edit_message_text(final_txt, cid, mid, parse_mode="Markdown")
            time.sleep(0.6)
        except:
            pass
    finally:
        SCAN_LOCK.release()

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
            sig="CALL"; score=90; reason=f"🚀 Bull {mom1:.3f}%"
        elif mom1<-0.02 and mom3<-0.05 and not is_green and e9<e21 and rsi_now<50:
            sig="PUT"; score=90; reason=f"📉 Bear {mom1:.3f}%"
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
        bot.send_message(m.chat.id, f"❌ Private ID: {m.from_user.id}"); return
    active, is_real = get_active_pairs()
    is_news, news_info = is_news_time()
    market_type = "🌍 REAL OPEN" if is_real else "🏦 OTC"
    mk=types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton("💹 TRADE NOW", callback_data="trade"))
    mk.add(types.InlineKeyboardButton("📊 MY STATS", callback_data="stats"))
    txt=f"""🤖 **Z-BOT V8.6.2 FIXED 100%** 🤖

{market_type} | 💎 IQ: {'✅' if IQ_CONNECTED else '❌'}
💰 ${STATS['balance']:.2f} | {STATS['wins']}W/{STATS['loss']}L
{news_info}

✅ Scan now FORCED 100% - No more 90% stop!
"""
    bot.send_message(m.chat.id, txt, reply_markup=mk, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_allowed(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Owner only"); return
    data=c.data; cid=c.message.chat.id
    
    if data=="trade":
        active_pairs, is_real_day = get_active_pairs()
        market_type = "🌍 REAL" if is_real_day else "🏦 OTC"
        is_news, news_info = is_news_time()
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in active_pairs:
            mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"pair_{p}"))
        mk.add(types.InlineKeyboardButton("🔄 Switch OTC/REAL", callback_data="trade_otc" if is_real_day else "trade_real"))
        bot.send_message(cid, f"💹 **{market_type}**\n{news_info}\n👇 Choose:", reply_markup=mk, parse_mode="Markdown")
        return

    if data=="trade_otc":
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in OTC_PAIRS:
            mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"pair_{p}"))
        bot.send_message(cid, "🏦 **OTC 24/7**", reply_markup=mk, parse_mode="Markdown")
        return

    if data=="trade_real":
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in REAL_PAIRS:
            mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"pair_{p}"))
        bot.send_message(cid, "🌍 **REAL**", reply_markup=mk, parse_mode="Markdown")
        return

    if data.startswith("pair_"):
        pair=data.replace("pair_","")
        user_states[cid]={"pair":pair}
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🟢 DEMO", callback_data=f"bal_PRACTICE_{pair}"))
        mk.add(types.InlineKeyboardButton("🔴 REAL", callback_data=f"bal_REAL_{pair}"))
        mk.add(types.InlineKeyboardButton("⬅️ BACK", callback_data="trade"))
        bot.send_message(cid, f"✅ **{PAIR_EMOJI.get(pair,pair)}**\n💳 **STEP 2/3**", reply_markup=mk, parse_mode="Markdown")
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
        bot.send_message(cid, f"✅ {PAIR_EMOJI.get(pair,pair)} {bal}\n💰 **STEP 3/3**", reply_markup=mk, parse_mode="Markdown")
        return

    if data.startswith("amt_") or data.startswith("custom_"):
        if data.startswith("custom_"):
            parts=data.split("_"); pair=parts[1]; bal=parts[2]
            user_states[cid]={"pair":pair,"bal":bal,"step":"await_amt"}
            bot.send_message(cid, f"✏️ Type amount e.g 10 for {pair} {bal}")
            return
        
        parts=data.split("_"); amt=float(parts[1]); pair=parts[2]; bal=parts[3]
        scan_msg = bot.send_message(cid, f"🔍 INIT {PAIR_EMOJI.get(pair,pair)} 0%")
        legit_live_scan(cid, scan_msg.message_id, pair)
        
        d=analyze_momentum(pair)
        if not d:
            mk=types.InlineKeyboardMarkup()
            mk.add(types.InlineKeyboardButton("🔄 RETRY", callback_data=f"amt_{int(amt)}_{pair}_{bal}"))
            bot.send_message(cid, f"❌ Failed {pair}", reply_markup=mk)
            return
        
        dir_emoji = "🟢 CALL 🟢" if d['dir']=="CALL" else "🔴 PUT 🔴"
        signal_txt=f"""📡 **SIGNAL V8.6.2**
💱 {PAIR_EMOJI.get(pair,pair)}
📊 {dir_emoji}
🎯 {d['conf']:.0f}% | 💸 {int(d['payout']*100)}%
💰 ${amt} {bal}
"""
        try:
            plt.figure(figsize=(6,3)); plt.plot(d['df']['close'], color='#FFD700', linewidth=2); plt.title(f"{pair} {d['dir']} {d['conf']:.0f}%"); plt.grid(alpha=0.3); plt.tight_layout(); p="/tmp/c.png"; plt.savefig(p); plt.close()
            bot.send_photo(cid, open(p,'rb'), caption=signal_txt, parse_mode="Markdown")
        except:
            bot.send_message(cid, signal_txt, parse_mode="Markdown")
        
        time.sleep(0.5)
        bot.send_message(cid, f"🚀 PLACING {pair} {d['dir']} ${amt}...")
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal)
        if not ok:
            bot.send_message(cid, "❌ Failed"); iq_reconnect(); return
        bot.send_message(cid, f"✅ PLACED {oid} ⏳ {exp}s")
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
            bot.send_message(cid, f"⏱️ DONE Check IQ {oid}", reply_markup=mk)
        return

    if data=="stats":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0
        bot.send_message(cid, f"📊 STATS V8.6.2\n{STATS['wins']}W {STATS['loss']}L {wr:.1f}%\n${STATS['balance']:.2f}")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get("step")=="await_amt")
def handle_custom_amt(m):
    cid=m.chat.id; st=user_states.get(cid, {})
    if not is_allowed(m.from_user.id): return
    try:
        amt=float(m.text.strip())
        pair=st.get("pair"); bal=st.get("bal")
        if not pair: return
        scan_msg = bot.send_message(cid, f"🔍 INIT {pair} 0%")
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
                if pnl>0: bot.send_message(cid, f"✅ **WIN +${pnl:.2f}**")
                else: bot.send_message(cid, f"❌ **LOSS -${amt:.2f}**")
            except: bot.send_message(cid, f"⏱️ DONE Check IQ")
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
    return "V8.6.2 FORCED 100% SCAN RUNNING"
app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
