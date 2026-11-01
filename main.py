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

REAL_PAIRS = ["EURUSD","GBPUSD","USDJPY","EURGBP","AUDUSD","USDCAD","EURJPY","GBPJPY"]
OTC_PAIRS = ["EURUSD-OTC","GBPUSD-OTC","EURGBP-OTC","USDJPY-OTC","GBPJPY-OTC","AUDUSD-OTC","USDCHF-OTC","EURJPY-OTC"]

PAIR_EMOJI = {
    "EURUSD":"🇪🇺 EUR/USD REAL", "GBPUSD":"🇬🇧 GBP/USD REAL", "USDJPY":"🇺🇸 USD/JPY REAL",
    "EURGBP":"🇪🇺 EUR/GBP REAL", "AUDUSD":"🇦🇺 AUD/USD REAL", "USDCAD":"🇺🇸 USD/CAD REAL",
    "EURJPY":"🇪🇺 EUR/JPY REAL", "GBPJPY":"🇬🇧 GBP/JPY REAL",
    "EURUSD-OTC":"🇪🇺 EUR/USD", "GBPUSD-OTC":"🇬🇧 GBP/USD", "EURGBP-OTC":"🇪🇺 EUR/GBP",
    "USDJPY-OTC":"🇺🇸 USD/JPY", "GBPJPY-OTC":"🇬🇧 GBP/JPY", "AUDUSD-OTC":"🇦🇺 AUD/USD",
    "USDCHF-OTC":"🇺🇸 USD/CHF", "EURJPY-OTC":"🇪🇺 EUR/JPY"
}
STATS = {"balance":100.0,"wins":0,"loss":0}
user_states = {}
IQ_LOCK = threading.Lock()
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
    return REAL_PAIRS if is_weekday else OTC_PAIRS

def is_news_time():
    now_utc = datetime.now(timezone.utc)
    high_impact = [(12,30),(13,30),(14,0),(8,30),(9,30),(15,0),(13,0),(14,30)]
    current = now_utc.hour*60+now_utc.minute
    for h,m in high_impact:
        news_t = h*60+m
        if news_t-5 <= current <= news_t+15:
            return True, f"🛑 HIGH IMPACT NEWS {h:02d}:{m:02d} UTC - NO TRADE!"
    return False, f"✅ No News {now_utc.strftime('%H:%M UTC')} - Safe"

try:
    from iqoptionapi.stable_api import IQ_Option
    EMAIL=os.getenv("IQ_EMAIL"); PWD=os.getenv("IQ_PASS")
    if EMAIL and PWD:
        logging.disable(logging.CRITICAL)
        iq=IQ_Option(EMAIL,PWD); iq.connect()
        IQ_CONNECTED=iq.check_connect()
        if IQ_CONNECTED:
            try: iq.change_balance("PRACTICE")
            except: pass
        logging.disable(logging.NOTSET); logging.getLogger().setLevel(logging.CRITICAL); logging.disable(logging.ERROR)
        print(f"IQ CONNECTED: {IQ_CONNECTED}", flush=True)
except: IQ_CONNECTED=False

def iq_reconnect():
    global iq, IQ_CONNECTED
    try:
        from iqoptionapi.stable_api import IQ_Option
        logging.disable(logging.CRITICAL)
        iq=IQ_Option(os.getenv("IQ_EMAIL"),os.getenv("IQ_PASS")); iq.connect()
        IQ_CONNECTED=iq.check_connect()
        logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
        return IQ_CONNECTED
    except: IQ_CONNECTED=False; return False

def get_payout(pair):
    global PAYOUT_CACHE, PAYOUT_TIME
    if time.time()-PAYOUT_TIME<60 and pair in PAYOUT_CACHE: return PAYOUT_CACHE[pair]
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL); all_p=iq.get_all_profit()
            logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
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
                logging.disable(logging.CRITICAL); c=iq.get_candles(pair,60,50,time.time())
                logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            if c and len(c)>20: return pd.DataFrame(sorted(c,key=lambda x:x['from']))
            time.sleep(0.5)
        except: time.sleep(0.5)
    return None

def calc_rsi(closes, period=7):
    delta=closes.diff()
    gain=delta.where(delta>0,0).rolling(period).mean()
    loss=-delta.where(delta<0,0).rolling(period).mean()
    return 100-(100/(1+gain/loss))

# ===== YOUR LIVE SCANNING - NOT TOUCHED =====
def legit_live_scan(cid, mid, pair):
    steps = [
        (0, "🚀 Initializing V8...", 0.15),
        (15, f"🔌 IQ Check {pair}...", 0.2),
        (30, "📊 Fetching candles...", 0.25),
        (50, "📈 EMA9 + EMA21...", 0.2),
        (70, "💹 RSI + ATR...", 0.2),
        (85, "📰 News check...", 0.2),
        (100, "🔒 SIGNAL LOCKED!")
    ]
    last_pct = -1
    for item in steps:
        if len(item) == 3: pct, text, delay = item
        else: pct, text = item; delay = 0.15
        if pct == last_pct: time.sleep(delay); continue
        last_pct = pct
        filled = int(pct // 5); bar = "█" * filled + "░" * (20 - filled)
        if pct < 40: color = "🟥"
        elif pct < 80: color = "🟨"
        elif pct < 100: color = "🟩"
        else: color = "💎"
        is_news, news_info = is_news_time()
        scan_txt = f"""{color} **Z-BOT V8 LEGIT SCAN** {color}

💱 Pair: {PAIR_EMOJI.get(pair, pair)}
💎 IQ: {'✅ Connected' if IQ_CONNECTED else '❌ Offline'}

{bar} {pct}%
▓ Progress: {pct}% ▓

🔍 {text}
{news_info}

⏳ Fast scan - V8.2
"""
        try: bot.edit_message_text(scan_txt, cid, mid, parse_mode="Markdown")
        except Exception as e:
            print(f"Scan edit skip {pct}%: {e}", flush=True); pass
        time.sleep(delay)
    try:
        final_txt = f"""💎 **Z-BOT V8 LEGIT SCAN** 💎

💱 Pair: {PAIR_EMOJI.get(pair, pair)}
💎 IQ: {'✅ Connected' if IQ_CONNECTED else '❌ Offline'}

████████████████████ 100%
▓ Progress: 100% ▓

🔍 🔒 SIGNAL LOCKED! READY TO TRADE!
✅ Safe - No News

⏳ Scan complete - Fast V8.2!
"""
        bot.edit_message_text(final_txt, cid, mid, parse_mode="Markdown")
        time.sleep(0.3)
    except: pass

def analyze_momentum(pair):
    df=get_candles(pair)
    if df is None: return None
    try:
        close=df['close']; open_=df['open']
        ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean()
        rsi=calc_rsi(close,7)
        rsi_now=float(rsi.iloc[-1]); e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1])
        mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100
        mom3=(close.iloc[-1]-close.iloc[-4])/close.iloc[-4]*100
        is_green=float(close.iloc[-1])>float(open_.iloc[-1])
        payout=get_payout(pair); sig="CALL" if is_green else "PUT"; score=75; reason=""
        if mom1>0.02 and mom3>0.05 and is_green and e9>e21 and rsi_now>50 and rsi_now<78:
            sig="CALL"; score=90; reason=f"🚀 Strong Bullish Momentum {mom1:.3f}%"
        elif mom1<-0.02 and mom3<-0.05 and not is_green and e9<e21 and rsi_now<50:
            sig="PUT"; score=90; reason=f"📉 Strong Bearish Momentum {mom1:.3f}%"
        elif e9>e21 and is_green: sig="CALL"; score=82; reason=f"📈 EMA Bullish Trend"
        elif e9<e21 and not is_green: sig="PUT"; score=82; reason=f"📉 EMA Bearish Trend"
        return {"pair":pair,"dir":sig,"conf":min(94,score),"price":float(close.iloc[-1]),"rsi":rsi_now,"reason":reason,"mom":mom3,"payout":payout,"df":df.tail(30)}
    except: return None

def iq_trade(pair,direction,amount,bal,expiry_sec=30):
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL); iq.change_balance(bal)
            logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            if expiry_sec <= 90:
                try:
                    logging.disable(logging.CRITICAL)
                    _,oid=iq.buy_blitz(pair,amount,direction.lower(),expiry_sec)
                    logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
                    return True,oid,expiry_sec
                except: pass
            mins = max(1, int(expiry_sec/60))
            logging.disable(logging.CRITICAL)
            _,oid=iq.buy(amount,pair,direction.lower(),mins)
            logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            return True,oid,expiry_sec
    except Exception as e:
        print(f"Trade err {e}"); return False,None,0

@bot.message_handler(commands=['start'])
def start(m):
    if not is_allowed(m.from_user.id):
        bot.send_message(m.chat.id, f"❌ Private Bot\nYour ID: {m.from_user.id}\nOwner: {OWNER_ID}"); return
    mk=types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton("💹 TRADE NOW", callback_data="trade"))
    mk.add(types.InlineKeyboardButton("📊 MY STATS", callback_data="stats"), types.InlineKeyboardButton("⚙️ SETTINGS", callback_data="settings"))
    is_news, news_info = is_news_time()
    txt=f"""🤖 **Z-BOT PRO V48 V8.2 + EXPIRY** 🤖

✨ *REAL+OTC + Expiry Select*

💎 IQ Connected: {'✅' if IQ_CONNECTED else '❌'}
💰 Balance: ${STATS['balance']:.2f}
🎯 Win Rate: {STATS['wins']}/{STATS['wins']+STATS['loss'] if STATS['wins']+STATS['loss']>0 else 0}
{news_info}

👇 **Click TRADE to Start**
"""
    bot.send_message(m.chat.id, txt, reply_markup=mk, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_allowed(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Private - Owner only"); return
    data=c.data; cid=c.message.chat.id
    if data=="trade":
        is_news, news_info = is_news_time()
        if is_news:
            bot.answer_callback_query(c.id, "🛑 NEWS TIME - NO TRADE!")
            bot.send_message(cid, f"🛑 **NEWS FILTER ACTIVE!**\n\n{news_info}\n\n⏳ Wait 10-15 minutes!", parse_mode="Markdown"); return
        bot.answer_callback_query(c.id, "📋 Loading pairs...")
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in get_active_pairs():
            mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"pair_{p}"))
        bot.send_message(cid, f"💹 **STEP 1/4 - SELECT PAIR**\n\n{news_info}\n\n👇 Choose:", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("pair_"):
        pair=data.replace("pair_","")
        bot.answer_callback_query(c.id, f"{pair} selected")
        user_states[cid]={"pair":pair}
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🟢 DEMO ACCOUNT", callback_data=f"bal_PRACTICE_{pair}"))
        mk.add(types.InlineKeyboardButton("🔴 REAL ACCOUNT", callback_data=f"bal_REAL_{pair}"))
        mk.add(types.InlineKeyboardButton("⬅️ BACK", callback_data="trade"))
        bot.send_message(cid, f"✅ **PAIR: {PAIR_EMOJI.get(pair,pair)}**\n\n💳 **STEP 2/4 - SELECT ACCOUNT**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("bal_"):
        parts=data.split("_"); bal=parts[1]; pair=parts[2]
        bot.answer_callback_query(c.id, f"{bal}")
        user_states[cid]={"pair":pair,"bal":bal}
        mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("💵 $1", callback_data=f"amt_1_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $5", callback_data=f"amt_5_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $10", callback_data=f"amt_10_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("💵 $20", callback_data=f"amt_20_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $50", callback_data=f"amt_50_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $100", callback_data=f"amt_100_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("✏️ CUSTOM AMOUNT", callback_data=f"custom_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("⬅️ BACK", callback_data=f"pair_{pair}"))
        bot.send_message(cid, f"✅ **PAIR: {PAIR_EMOJI.get(pair,pair)}**\n✅ **ACCOUNT: {bal}**\n\n💰 **STEP 3/4 - SELECT AMOUNT**", reply_markup=mk, parse_mode="Markdown"); return

    if data.startswith("amt_") or data.startswith("custom_"):
        if data.startswith("custom_"):
            parts=data.split("_"); pair=parts[1]; bal=parts[2]
            user_states[cid]={"pair":pair,"bal":bal,"step":"await_amt"}
            bot.send_message(cid, f"✏️ **Type your amount**\n\nExample: `10` or `100`\n\nFor {pair} {bal}", parse_mode="Markdown"); return
        parts=data.split("_"); amt=float(parts[1]); pair=parts[2]; bal=parts[3]
        user_states[cid]={"pair":pair,"bal":bal,"amt":amt}
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("⏱️ 30 SEC", callback_data=f"exp_30_{pair}_{bal}_{int(amt)}"),
               types.InlineKeyboardButton("⏱️ 1 MIN", callback_data=f"exp_60_{pair}_{bal}_{int(amt)}"))
        mk.add(types.InlineKeyboardButton("⏱️ 2 MIN", callback_data=f"exp_120_{pair}_{bal}_{int(amt)}"),
               types.InlineKeyboardButton("⏱️ 5 MIN", callback_data=f"exp_300_{pair}_{bal}_{int(amt)}"))
        mk.add(types.InlineKeyboardButton("⏱️ 15 MIN", callback_data=f"exp_900_{pair}_{bal}_{int(amt)}"))
        mk.add(types.InlineKeyboardButton("⬅️ BACK", callback_data=f"pair_{pair}"))
        bot.send_message(cid, f"""✅ **PAIR: {PAIR_EMOJI.get(pair,pair)}**
✅ **ACCOUNT: {bal}**
✅ **AMOUNT: ${amt}**

⏱️ **STEP 4/4 - SELECT EXPIRY**

👇 Choose expiration:""", reply_markup=mk, parse_mode="Markdown"); return

    if data.startswith("exp_"):
        parts=data.split("_"); expiry=int(parts[1]); pair=parts[2]; bal=parts[3]; amt=float(parts[4])
        is_news, news_info = is_news_time()
        if is_news:
            bot.send_message(cid, f"🛑 **BLOCKED - NEWS!**\n\n{news_info}"); return
        bot.answer_callback_query(c.id, f"Analyzing {pair}...")
        scan_msg = bot.send_message(cid, f"🔍 **INITIALIZING V8 LEGIT SCAN FOR {PAIR_EMOJI.get(pair,pair)}**\n\n░░░░░░░░░░░░ 0%\n🚀 Starting...")
        legit_live_scan(cid, scan_msg.message_id, pair)
        d=analyze_momentum(pair)
        if not d:
            mk=types.InlineKeyboardMarkup()
            mk.add(types.InlineKeyboardButton("🔄 RETRY", callback_data=f"exp_{expiry}_{pair}_{bal}_{int(amt)}"))
            bot.send_message(cid, f"❌ Failed to analyze {pair}\nTap retry", reply_markup=mk); return
        dir_emoji = "🟢 CALL - BUY 🟢" if d['dir']=="CALL" else "🔴 PUT - SELL 🔴"
        expiry_txt = f"{expiry}s" if expiry < 60 else f"{expiry//60} min"
        signal_txt=f"""━━━━━━━━━━━━━━━
📡 **SIGNAL FOUND V8 + {expiry_txt.upper()}**
━━━━━━━━━━━━━━━

💱 **Pair:** {PAIR_EMOJI.get(pair,pair)}
📊 **Direction:** {dir_emoji}
🎯 **Confidence:** {d['conf']:.0f}%
💸 **Payout:** {int(d['payout']*100)}%
💰 **Amount:** ${amt} {bal}
⏱️ **Expiry:** {expiry_txt}
📰 **News:** {news_info}

📈 **Analysis:** {d['reason']}
📍 **Price:** {d['price']:.5f}
📊 **RSI:** {d['rsi']:.0f}

━━━━━━━━━━━━━━━
🤖 **AUTO PLACING {expiry_txt} TRADE...**
━━━━━━━━━━━━━━━
"""
        try:
            plt.figure(figsize=(6,3)); plt.plot(d['df']['close'], color='#FFD700', linewidth=2); plt.title(f"{pair} {d['dir']} {d['conf']:.0f}%"); plt.grid(alpha=0.3); plt.tight_layout(); p="/tmp/c.png"; plt.savefig(p); plt.close()
            bot.send_photo(cid, open(p,'rb'), caption=signal_txt, parse_mode="Markdown")
        except: bot.send_message(cid, signal_txt, parse_mode="Markdown")
        time.sleep(1)
        bot.send_message(cid, f"🚀 **PLACING {expiry_txt} TRADE...**\n\n💱 {pair} | {d['dir']} | ${amt}\n🔄 IQ Option...\n📰 {news_info}", parse_mode="Markdown")
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal,expiry)
        if not ok:
            bot.send_message(cid, "❌ **Trade Failed - Reconnecting**\nTry again"); iq_reconnect(); return
        bot.send_message(cid, f"""✅ **TRADE PLACED!**

🆔 `{oid}`
💱 {pair} | {d['dir']} | ${amt}
⏱️ Expiry: {expiry_txt} ({expiry}s)
💳 {bal}
📰 Safe ✅

⏳ WAIT {expiry}s...
""", parse_mode="Markdown")
        time.sleep(exp+5)
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL); pnl=iq.check_win_v4(oid)
                logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            if pnl>0:
                STATS['wins']+=1; STATS['balance']+=pnl
                mk=types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton("🔁 SAME TRADE", callback_data=f"exp_{expiry}_{pair}_{bal}_{int(amt)}"),
                       types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"))
                bot.send_message(cid, f"✅ **WIN +${pnl:.2f}**\n💱 {pair} {expiry_txt}", reply_markup=mk, parse_mode="Markdown")
            else:
                STATS['loss']+=1; STATS['balance']-=amt
                mk=types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton(f"🔁 MARTINGALE ${amt*2.2:.0f}", callback_data=f"exp_{expiry}_{pair}_{bal}_{int(amt*2.2)}"),
                       types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"))
                bot.send_message(cid, f"❌ **LOSS -${amt}**\n💱 {pair} {expiry_txt}", reply_markup=mk, parse_mode="Markdown")
        except:
            mk=types.InlineKeyboardMarkup()
            mk.add(types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"))
            bot.send_message(cid, f"⏱️ **EXPIRED**\nCheck IQ app\nID: {oid}", reply_markup=mk)
        return

    if data=="stats":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0
        is_news, news_info = is_news_time()
        bot.send_message(cid, f"📊 **STATS V8**\n\n🏆 Wins: {STATS['wins']}\n❌ Loss: {STATS['loss']}\n📈 Winrate: {wr:.1f}%\n💰 Balance: ${STATS['balance']:.2f}\n\n{news_info}", parse_mode="Markdown")
    if data=="settings":
        is_news, news_info = is_news_time()
        bot.send_message(cid, f"⚙️ **SETTINGS V8**\n\n📰 News Filter: Active\n💎 Fast Scan: Active (No Hook)\n⏱️ Expiry Buttons: Active\n{news_info}\n\nOwner: {OWNER_ID}")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get("step")=="await_amt")
def handle_custom_amt(m):
    cid=m.chat.id; st=user_states.get(cid, {})
    if not is_allowed(m.from_user.id): return
    is_news, news_info = is_news_time()
    if is_news:
        bot.send_message(cid, f"🛑 **BLOCKED - NEWS TIME!**\n\n{news_info}"); return
    try:
        amt=float(m.text.strip())
        pair=st.get("pair"); bal=st.get("bal")
        if not pair: return
        user_states[cid]={"pair":pair,"bal":bal,"amt":amt}
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("⏱️ 30 SEC", callback_data=f"exp_30_{pair}_{bal}_{int(amt)}"),
               types.InlineKeyboardButton("⏱️ 1 MIN", callback_data=f"exp_60_{pair}_{bal}_{int(amt)}"))
        mk.add(types.InlineKeyboardButton("⏱️ 2 MIN", callback_data=f"exp_120_{pair}_{bal}_{int(amt)}"),
               types.InlineKeyboardButton("⏱️ 5 MIN", callback_data=f"exp_300_{pair}_{bal}_{int(amt)}"))
        mk.add(types.InlineKeyboardButton("⏱️ 15 MIN", callback_data=f"exp_900_{pair}_{bal}_{int(amt)}"))
        bot.send_message(cid, f"✅ Custom ${amt} for {pair}\n\n⏱️ **STEP 4/4 - SELECT EXPIRY**\n\n👇 Choose:", reply_markup=mk, parse_mode="Markdown")
    except: bot.send_message(cid, "❌ Send number only, e.g 100")

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def wh(): bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode("utf-8"))]); return "ok"
@app.route("/")
def home():
    u=os.getenv("RENDER_EXTERNAL_URL")
    if u:
        try: requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={u}/{BOT_TOKEN}", timeout=5)
        except: pass
    return "V8.2 FAST SCAN + REAL+OTC + EXPIRY - RUNNING"
app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
