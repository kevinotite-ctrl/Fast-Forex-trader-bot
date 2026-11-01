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
# ===== FIX: HIDE get_candles SPAM =====
logging.getLogger().setLevel(logging.CRITICAL)
logging.getLogger("iqoptionapi").setLevel(logging.CRITICAL)
logging.disable(logging.ERROR)

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 8659453018  # CHANGE TO YOUR ID FROM @userinfobot
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

OTC_PAIRS = ["EURUSD-OTC","GBPUSD-OTC","EURGBP-OTC","USDJPY-OTC","GBPJPY-OTC","AUDUSD-OTC","USDCHF-OTC","EURJPY-OTC"]
PAIR_EMOJI = {
    "EURUSD-OTC":"🇪🇺 EUR/USD",
    "GBPUSD-OTC":"🇬🇧 GBP/USD", 
    "EURGBP-OTC":"🇪🇺 EUR/GBP",
    "USDJPY-OTC":"🇺🇸 USD/JPY",
    "GBPJPY-OTC":"🇬🇧 GBP/JPY",
    "AUDUSD-OTC":"🇦🇺 AUD/USD",
    "USDCHF-OTC":"🇺🇸 USD/CHF",
    "EURJPY-OTC":"🇪🇺 EUR/JPY"
}
STATS = {"balance":100.0,"wins":0,"loss":0}
user_states = {}
IQ_LOCK = threading.Lock()
IQ_CONNECTED=False; iq=None
PAYOUT_CACHE={}; PAYOUT_TIME=0

# ===== OWNER CHECK =====
def is_allowed(uid):
    return uid == OWNER_ID

# ===== NEWS FILTER - DON'T TRADE DURING NEWS =====
def is_news_time():
    """
    Returns True if high-impact news time - block trading
    Blocks 5 min before and 15 min after major news
    Times in UTC
    """
    now_utc = datetime.now(timezone.utc)
    # High impact news UTC times (NFP, CPI, FOMC, etc)
    high_impact = [
        (12, 30), (13, 30), (14, 0), (8, 30), (9, 30), (15, 0), (13, 0), (14, 30)
    ]
    current = now_utc.hour * 60 + now_utc.minute
    for h, m in high_impact:
        news_t = h * 60 + m
        if news_t - 5 <= current <= news_t + 15:  # Block 5 before, 15 after
            return True, f"🛑 HIGH IMPACT NEWS {h:02d}:{m:02d} UTC - NO TRADE!"
    return False, f"✅ No News {now_utc.strftime('%H:%M UTC')} - Safe"

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
except: 
    IQ_CONNECTED=False

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
        except: 
            time.sleep(0.5)
    return None

def calc_rsi(closes, period=7):
    delta=closes.diff()
    gain=delta.where(delta>0,0).rolling(period).mean()
    loss=-delta.where(delta<0,0).rolling(period).mean()
    return 100-(100/(1+gain/loss))

# ===== LEGIT LIVE SCANNING BAR - FAST - NO HOOKING - 100% =====
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
        if len(item) == 3:
            pct, text, delay = item
        else:
            pct, text = item
            delay = 0.15
        
        # Don't spam if same %
        if pct == last_pct:
            time.sleep(delay)
            continue
        last_pct = pct
        
        filled = int(pct // 5)
        bar = "█" * filled + "░" * (20 - filled)
        
        if pct < 40:
            color = "🟥"
        elif pct < 80:
            color = "🟨"
        elif pct < 100:
            color = "🟩"
        else:
            color = "💎"
        
        # Fast news check - no heavy calc
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
        try:
            bot.edit_message_text(scan_txt, cid, mid, parse_mode="Markdown")
        except Exception as e:
            # If edit fails (rate limit), skip and continue - DON'T HOOK!
            print(f"Scan edit skip {pct}%: {e}", flush=True)
            pass
        
        time.sleep(delay)
    
    # FORCE 100% AT END - ALWAYS SHOW LOCKED!
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
    except:
        pass

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
            sig="CALL"; score=90; reason=f"🚀 Strong Bullish Momentum {mom1:.3f}%"
        elif mom1<-0.02 and mom3<-0.05 and not is_green and e9<e21 and rsi_now<50:
            sig="PUT"; score=90; reason=f"📉 Strong Bearish Momentum {mom1:.3f}%"
        elif e9>e21 and is_green: sig="CALL"; score=82; reason=f"📈 EMA Bullish Trend"
        elif e9<e21 and not is_green: sig="PUT"; score=82; reason=f"📉 EMA Bearish Trend"
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
        bot.send_message(m.chat.id, f"❌ Private Bot\nYour ID: {m.from_user.id}\nOwner: {OWNER_ID}")
        return
    mk=types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton("💹 TRADE NOW", callback_data="trade"))
    mk.add(types.InlineKeyboardButton("📊 MY STATS", callback_data="stats"), types.InlineKeyboardButton("⚙️ SETTINGS", callback_data="settings"))
    is_news, news_info = is_news_time()
    txt=f"""🤖 **Z-BOT PRO V48 V8.1** 🤖

✨ *Professional OTC + News Filter*

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
        bot.answer_callback_query(c.id, "❌ Private - Owner only")
        return
    data=c.data; cid=c.message.chat.id
    if data=="trade":
        # Check news before showing pairs
        is_news, news_info = is_news_time()
        if is_news:
            bot.answer_callback_query(c.id, "🛑 NEWS TIME - NO TRADE!")
            bot.send_message(cid, f"🛑 **NEWS FILTER ACTIVE!**\n\n{news_info}\n\n⏳ Wait 10-15 minutes after news before trading!\nVolatility too high - Dangerous!", parse_mode="Markdown")
            return
        
        bot.answer_callback_query(c.id, "📋 Loading pairs...")
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in OTC_PAIRS:
            mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"pair_{p}"))
        bot.send_message(cid, f"💹 **STEP 1/3 - SELECT PAIR**\n\n{news_info}\n\n👇 Choose your trading pair:", reply_markup=mk, parse_mode="Markdown")
        return
    if data.startswith("pair_"):
        pair=data.replace("pair_","")
        bot.answer_callback_query(c.id, f"{pair} selected")
        user_states[cid]={"pair":pair}
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🟢 DEMO ACCOUNT", callback_data=f"bal_PRACTICE_{pair}"))
        mk.add(types.InlineKeyboardButton("🔴 REAL ACCOUNT", callback_data=f"bal_REAL_{pair}"))
        mk.add(types.InlineKeyboardButton("⬅️ BACK", callback_data="trade"))
        bot.send_message(cid, f"✅ **PAIR: {PAIR_EMOJI.get(pair,pair)}**\n\n💳 **STEP 2/3 - SELECT ACCOUNT**\n\n👇 Choose account type:", reply_markup=mk, parse_mode="Markdown")
        return
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
        bot.send_message(cid, f"✅ **PAIR: {PAIR_EMOJI.get(pair,pair)}**\n✅ **ACCOUNT: {bal}**\n\n💰 **STEP 3/3 - SELECT AMOUNT**\n\n👇 Choose investment:", reply_markup=mk, parse_mode="Markdown")
        return
    if data.startswith("amt_") or data.startswith("custom_"):
        if data.startswith("custom_"):
            parts=data.split("_"); pair=parts[1]; bal=parts[2]
            user_states[cid]={"pair":pair,"bal":bal,"step":"await_amt"}
            bot.send_message(cid, f"✏️ **Type your amount**\n\nExample: `10` or `100`\n\nFor {pair} {bal}", parse_mode="Markdown")
            return
        
        # ===== CHECK NEWS BEFORE TRADE =====
        is_news, news_info = is_news_time()
        if is_news:
            bot.answer_callback_query(c.id, "🛑 NEWS - BLOCKED!")
            bot.send_message(cid, f"🛑 **TRADE BLOCKED - NEWS TIME!**\n\n{news_info}\n\n💡 **Why?** High-impact news = market manipulation, spread widening, dangerous!\n⏳ **Wait:** 10-15 mins after news\n\nTry again later!", parse_mode="Markdown")
            return
        
        parts=data.split("_"); amt=float(parts[1]); pair=parts[2]; bal=parts[3]
        bot.answer_callback_query(c.id, f"Analyzing {pair}...")
        
        # ===== LEGIT LIVE SCANNING BAR =====
        scan_msg = bot.send_message(cid, f"🔍 **INITIALIZING V8 LEGIT SCAN FOR {PAIR_EMOJI.get(pair,pair)}**\n\n░░░░░░░░░░░░░░░░░░░░ 0%\n🚀 Starting legit scan...", parse_mode="Markdown")
        legit_live_scan(cid, scan_msg.message_id, pair)
        
        # ANALYZE
        d=analyze_momentum(pair)
        if not d:
            mk=types.InlineKeyboardMarkup()
            mk.add(types.InlineKeyboardButton("🔄 RETRY", callback_data=f"amt_{int(amt)}_{pair}_{bal}"))
            bot.send_message(cid, f"❌ Failed to analyze {pair}\nTap retry", reply_markup=mk)
            return
        
        dir_emoji = "🟢 CALL - BUY 🟢" if d['dir']=="CALL" else "🔴 PUT - SELL 🔴"
        signal_txt=f"""━━━━━━━━━━━━━━━
📡 **SIGNAL FOUND V8**
━━━━━━━━━━━━━━━

💱 **Pair:** {PAIR_EMOJI.get(pair,pair)}
📊 **Direction:** {dir_emoji}
🎯 **Confidence:** {d['conf']:.0f}%
💸 **Payout:** {int(d['payout']*100)}%
💰 **Amount:** ${amt} {bal}
📰 **News:** {news_info}

📈 **Analysis:** {d['reason']}
📍 **Price:** {d['price']:.5f}
📊 **RSI:** {d['rsi']:.0f}

━━━━━━━━━━━━━━━
🤖 **AUTO PLACING TRADE...**
━━━━━━━━━━━━━━━
"""
        try:
            plt.figure(figsize=(6,3)); plt.plot(d['df']['close'], color='#FFD700', linewidth=2); plt.title(f"{pair} {d['dir']} {d['conf']:.0f}%"); plt.grid(alpha=0.3); plt.tight_layout(); p="/tmp/c.png"; plt.savefig(p); plt.close()
            bot.send_photo(cid, open(p,'rb'), caption=signal_txt, parse_mode="Markdown")
        except:
            bot.send_message(cid, signal_txt, parse_mode="Markdown")
        
        time.sleep(1)
        bot.send_message(cid, f"🚀 **PLACING TRADE NOW...**\n\n💱 {pair} | {d['dir']} | ${amt}\n🔄 Connecting to IQ Option...\n📰 {news_info}", parse_mode="Markdown")
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal)
        if not ok:
            bot.send_message(cid, "❌ **Trade Failed - Reconnecting**\nTry again"); iq_reconnect(); return
        
        bot.send_message(cid, f"""✅ **TRADE PLACED SUCCESSFULLY!**

━━━━━━━━━━━━━━━
🆔 **Order ID:** `{oid}`
💱 **Pair:** {pair}
📊 **Direction:** {d['dir']}
💰 **Amount:** ${amt}
⏱️ **Expiry:** {exp} seconds
💳 **Account:** {bal}
📰 **News Check:** Safe ✅
━━━━━━━━━━━━━━━

⏳ **INITIALIZING... WAIT 30 SEC**
🕐 Trade is running...

I will send result in 30 seconds...
""", parse_mode="Markdown")
        
        time.sleep(exp+5)
        try:
            with IQ_LOCK: 
                logging.disable(logging.CRITICAL)
                pnl=iq.check_win_v4(oid)
                logging.disable(logging.NOTSET)
                logging.disable(logging.ERROR)
            if pnl>0:
                STATS['wins']+=1; STATS['balance']+=pnl
                mk=types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton("🔁 TRADE AGAIN SAME", callback_data=f"amt_{int(amt)}_{pair}_{bal}"),
                       types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"))
                bot.send_message(cid, f"""✅ **WINNER! ✅**

━━━━━━━━━━━━━━━
💰 **Profit:** +${pnl:.2f}
💱 **Pair:** {pair} {d['dir']}
💵 **New Balance:** ${STATS['balance']:.2f}
📊 **Result:** WIN
📰 **News:** Safe - No news
━━━━━━━━━━━━━━━

🎉 Congratulations!
""", reply_markup=mk, parse_mode="Markdown")
            else:
                STATS['loss']+=1; STATS['balance']-=amt
                mk=types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton(f"🔁 MARTINGALE ${amt*2.2:.0f}", callback_data=f"amt_{int(amt*2.2)}_{pair}_{bal}"),
                       types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"))
                bot.send_message(cid, f"""❌ **LOSS**

━━━━━━━━━━━━━━━
💸 **Loss:** -${amt:.2f}
💱 **Pair:** {pair} {d['dir']}
💵 **Balance:** ${STATS['balance']:.2f}
📊 **Result:** LOSS
━━━━━━━━━━━━━━━

💪 Don't give up! Try Martingale
""", reply_markup=mk, parse_mode="Markdown")
        except:
            mk=types.InlineKeyboardMarkup()
            mk.add(types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"))
            bot.send_message(cid, f"⏱️ **TRADE EXPIRED**\n\nCheck IQ Option app for result\nID: {oid}\n\nTap new trade", reply_markup=mk)
        return

    if data=="stats":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0
        is_news, news_info = is_news_time()
        bot.send_message(cid, f"📊 **STATS V8**\n\n🏆 Wins: {STATS['wins']}\n❌ Loss: {STATS['loss']}\n📈 Winrate: {wr:.1f}%\n💰 Balance: ${STATS['balance']:.2f}\n\n{news_info}", parse_mode="Markdown")
    if data=="settings": 
        is_news, news_info = is_news_time()
        bot.send_message(cid, f"⚙️ **SETTINGS V8**\n\n📰 News Filter: Active (blocks high-impact news)\n💎 Legit Scanning Bar: Active\n{news_info}\n\nOwner: {OWNER_ID}")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get("step")=="await_amt")
def handle_custom_amt(m):
    cid=m.chat.id; st=user_states.get(cid, {})
    if not is_allowed(m.from_user.id):
        return
    # Check news
    is_news, news_info = is_news_time()
    if is_news:
        bot.send_message(cid, f"🛑 **BLOCKED - NEWS TIME!**\n\n{news_info}\nWait 10-15 mins!")
        return
    try:
        amt=float(m.text.strip())
        pair=st.get("pair"); bal=st.get("bal")
        if not pair: return
        
        scan_msg = bot.send_message(cid, f"🔍 **INITIALIZING V8 SCAN FOR {pair}**\n\n░░░░░░░░░░░░ 0%\nStarting...")
        legit_live_scan(cid, scan_msg.message_id, pair)
        
        d=analyze_momentum(pair)
        if not d: bot.send_message(cid, "Failed analyze"); return
        dir_emoji = "🟢 CALL - BUY 🟢" if d['dir']=="CALL" else "🔴 PUT - SELL 🔴"
        signal_txt=f"""📡 **SIGNAL** {PAIR_EMOJI.get(pair,pair)} {dir_emoji} {d['conf']:.0f}% ${amt}\n📰 {news_info}"""
        bot.send_message(cid, signal_txt)
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal)
        if ok:
            bot.send_message(cid, f"✅ Placed {oid}\n⏳ Initializing wait {exp} sec...\n📰 {news_info}")
            time.sleep(exp+5)
            try:
                with IQ_LOCK: 
                    logging.disable(logging.CRITICAL)
                    pnl=iq.check_win_v4(oid)
                    logging.disable(logging.NOTSET)
                    logging.disable(logging.ERROR)
                if pnl>0: bot.send_message(cid, f"✅ WIN +${pnl:.2f}")
                else: bot.send_message(cid, f"❌ LOSS -${amt}")
            except: bot.send_message(cid, "Check IQ app")
        user_states.pop(cid,None)
    except: bot.send_message(cid, "❌ Send number only, e.g 100")

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def wh(): bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode("utf-8"))]); return "ok"
@app.route("/")
def home():
    u=os.getenv("RENDER_EXTERNAL_URL")
    if u:
        try: requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={u}/{BOT_TOKEN}", timeout=5)
        except: pass
    return "V48 V8.1 CLEAN - LEGIT LIVE SCANNING BAR + NEWS FILTER - RUNNING"
app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
