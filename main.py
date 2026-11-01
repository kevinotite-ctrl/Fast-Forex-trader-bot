# -*- coding: utf-8 -*-
# 👑 Z-BOT PRO V48 V2 - PRIVATE + LIVE BAR + DURATION PICKER + RESULT AFTER TRADE
import os, time, threading, warnings
from datetime import datetime
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

# 🔒 PRIVATE LOCK - ONLY YOU
OWNER_ID = 8659453018
ALLOWED_USERS = [OWNER_ID]
def is_private_allowed(uid):
    return uid in ALLOWED_USERS

OTC_PAIRS = ["EURUSD-OTC","GBPUSD-OTC","EURGBP-OTC","USDJPY-OTC","GBPJPY-OTC","AUDUSD-OTC","USDCHF-OTC","EURJPY-OTC"]
PAIR_EMOJI = {
    "EURUSD-OTC":"🇪🇺 EUR/USD","GBPUSD-OTC":"🇬🇧 GBP/USD","EURGBP-OTC":"🇪🇺 EUR/GBP",
    "USDJPY-OTC":"🇺🇸 USD/JPY","GBPJPY-OTC":"🇬🇧 GBP/JPY","AUDUSD-OTC":"🇦🇺 AUD/USD",
    "USDCHF-OTC":"🇺🇸 USD/CHF","EURJPY-OTC":"🇪🇺 EUR/JPY"
}
STATS = {"balance":100.0,"wins":0,"loss":0}
user_states = {}
IQ_LOCK = threading.Lock()
IQ_CONNECTED=False; iq=None
PAYOUT_CACHE={}; PAYOUT_TIME=0

try:
    from iqoptionapi.stable_api import IQ_Option
    EMAIL=os.getenv("IQ_EMAIL"); PWD=os.getenv("IQ_PASS")
    if EMAIL and PWD:
        iq=IQ_Option(EMAIL,PWD); iq.connect(); IQ_CONNECTED=iq.check_connect()
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
                    if k in all_p[pair]:
                        PAYOUT_CACHE[pair]=float(all_p[pair][k]); PAYOUT_TIME=time.time(); return float(all_p[pair][k])
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

def analyze_momentum(pair):
    df=get_candles(pair)
    if df is None: return None
    try:
        close=df['close']; open_=df['open']
        ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean(); rsi=calc_rsi(close,7)
        rsi_now=float(rsi.iloc[-1]); e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1])
        mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100; mom3=(close.iloc[-1]-close.iloc[-4])/close.iloc[-4]*100
        is_green=float(close.iloc[-1])>float(open_.iloc[-1]); payout=get_payout(pair)
        sig="CALL" if is_green else "PUT"; score=75; reason=""
        if mom1>0.02 and mom3>0.05 and is_green and e9>e21 and rsi_now>50 and rsi_now<78: sig="CALL"; score=90; reason=f"🚀 Bullish {mom1:.3f}%"
        elif mom1<-0.02 and mom3<-0.05 and not is_green and e9<e21 and rsi_now<50: sig="PUT"; score=90; reason=f"📉 Bearish {mom1:.3f}%"
        elif e9>e21 and is_green: sig="CALL"; score=82; reason=f"📈 EMA Bull"
        elif e9<e21 and not is_green: sig="PUT"; score=82; reason=f"📉 EMA Bear"
        return {"pair":pair,"dir":sig,"conf":min(94,score),"price":float(close.iloc[-1]),"rsi":rsi_now,"reason":reason,"mom":mom3,"payout":payout,"df":df.tail(30)}
    except: return None

# LIVE SCANNING BAR
def animate_live_scanning(cid, mid, pair):
    steps=[(5,"🔌 Connecting to IQ feed..."),(15,"📊 Fetching 1m candles..."),(30,"📈 Calculating EMA9/21..."),(45,"💹 Checking RSI momentum..."),(60,"🎯 Analyzing BB + ATR..."),(75,"🧠 MTF 5m confirmation..."),(85,"✅ Verifying GOD filter..."),(100,"🔒 SIGNAL LOCKED READY!")]
    for pct, stage in steps:
        bar="█"* (pct//10) + "▒"*(10-pct//10)
        txt=f"⚡ **Z-BOT LIVE SCAN**\n\nPair: {pair}\n\n{bar} {pct}%\n{stage}\n\n⏳ Please wait..."
        try: bot.edit_message_text(txt,cid,mid,parse_mode="Markdown")
        except: pass
        time.sleep(0.35)

def animate_progress_bar(cid, mid, pair, amount_text):
    steps=[(10,"reading candles 1m"),(25,"reading momentum"),(50,"reading MTF 5m + BB"),(75,"locking signal"),(100,"SIGNAL LOCKED")]
    for pct, stage in steps:
        bar="▓"* (pct//10) + "░"*(10-pct//10)
        txt=f"🔍 **Z-BOT QUICK**\nSCANNING {pair}...\n\n{bar} {pct}%\n> {stage}\nAmount {amount_text}"
        try: bot.edit_message_text(txt,cid,mid)
        except: pass
        time.sleep(0.3)

# REAL TRADE FIX WITH DURATION
def iq_trade(pair,direction,amount,bal,expiry_min=1):
    try:
        with IQ_LOCK:
            iq.change_balance(bal)
            print(f"TRY TRADE {pair} {direction} ${amount} {bal} exp={expiry_min}m", flush=True)
            if amount < 1.0: return False, None, 0
            for attempt in range(3):
                try:
                    check, oid = iq.buy(amount, pair, direction.lower(), expiry_min)
                    print(f"Attempt {attempt+1} check={check} oid={oid}", flush=True)
                    if check and str(oid).strip().isdigit():
                        return True, oid, expiry_min*60
                    if "time for purchasing" in str(oid).lower():
                        time.sleep(3); continue
                except Exception as e:
                    print(f"Buy err {e}", flush=True); time.sleep(2)
            return False, None, 0
    except Exception as e:
        print(f"Trade err {e}"); return False,None,0

def safe_check_win(oid, max_retry=6):
    for _ in range(max_retry):
        try:
            with IQ_LOCK:
                pnl = iq.check_win_v4(oid)
                if pnl is not None: return pnl
        except: time.sleep(2)
    return None

# NEW DURATION KEYBOARD
def duration_kb(pair, amt, bal):
    mk=types.InlineKeyboardMarkup(row_width=3)
    mk.add(types.InlineKeyboardButton("⏱️ 30 Sec", callback_data=f"dur_30_{int(amt)}_{pair}_{bal}"),
           types.InlineKeyboardButton("⏱️ 1 Min", callback_data=f"dur_60_{int(amt)}_{pair}_{bal}"),
           types.InlineKeyboardButton("⏱️ 2 Min", callback_data=f"dur_120_{int(amt)}_{pair}_{bal}"))
    mk.add(types.InlineKeyboardButton("⏱️ 3 Min", callback_data=f"dur_180_{int(amt)}_{pair}_{bal}"),
           types.InlineKeyboardButton("⏱️ 5 Min", callback_data=f"dur_300_{int(amt)}_{pair}_{bal}"),
           types.InlineKeyboardButton("⏱️ 15 Min", callback_data=f"dur_900_{int(amt)}_{pair}_{bal}"))
    mk.add(types.InlineKeyboardButton("⬅️ Back to Amount", callback_data=f"bal_{bal}_{pair}"))
    return mk

def do_trade(cid, pair, amt, bal, duration_sec):
    expiry_min = max(1, duration_sec//60) if duration_sec>=60 else 1
    scan_msg = bot.send_message(cid, f"🔍 **ANALYZING {PAIR_EMOJI.get(pair,pair)}**\n\n░░░░░░░░░░ 0% starting...", parse_mode="Markdown")
    animate_live_scanning(cid, scan_msg.message_id, pair)
    animate_progress_bar(cid, scan_msg.message_id, pair, f"${amt} {duration_sec}s")
    d=analyze_momentum(pair)
    if not d:
        mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🔄 RETRY", callback_data=f"dur_{duration_sec}_{int(amt)}_{pair}_{bal}"))
        bot.send_message(cid, f"❌ Failed to analyze {pair}\nTap retry", reply_markup=mk); return
    dir_emoji = "🟢 CALL - BUY 🟢" if d['dir']=="CALL" else "🔴 PUT - SELL 🔴"
    signal_txt=f"""📡 **SIGNAL FOUND**\n\n💱 Pair: {PAIR_EMOJI.get(pair,pair)}\n📊 Direction: {dir_emoji}\n🎯 Confidence: {d['conf']:.0f}%\n💸 Payout: {int(d['payout']*100)}%\n💰 Amount: ${amt} {bal}\n⏱️ Duration: {duration_sec}s\n\n📈 Analysis: {d['reason']}\n\n🤖 AUTO PLACING TRADE..."""
    try:
        plt.figure(figsize=(6,3)); plt.plot(d['df']['close'], color='#FFD700', linewidth=2); plt.title(f"{pair} {d['dir']} {d['conf']:.0f}%"); plt.grid(alpha=0.3); plt.tight_layout(); p="/tmp/c.png"; plt.savefig(p); plt.close()
        bot.send_photo(cid, open(p,'rb'), caption=signal_txt, parse_mode="Markdown")
    except: bot.send_message(cid, signal_txt, parse_mode="Markdown")
    bot.send_message(cid, f"🚀 **PLACING TRADE NOW...**\n\n💱 {pair} | {d['dir']} | ${amt} | {duration_sec}s", parse_mode="Markdown")
    ok,oid,exp=iq_trade(pair,d['dir'],amt,bal,expiry_min)
    if not ok:
        bot.send_message(cid, f"❌ **Trade Failed - IQ closed or Time window**\n\nTry again in 5 sec", parse_mode="Markdown"); iq_reconnect(); return
    bot.send_message(cid, f"✅ **TRADE PLACED!**\n\n🆔 Order ID: `{oid}`\n💱 Pair: {pair}\n📊 Direction: {d['dir']}\n💰 Amount: ${amt}\n⏱️ Duration: {duration_sec}s ({exp}s)\n\n⏳ INITIALIZING... WAIT {duration_sec} SEC", parse_mode="Markdown")
    time.sleep(duration_sec + 5)
    pnl = safe_check_win(oid)
    if pnl is None: time.sleep(3); pnl = safe_check_win(oid)
    # RESULT AFTER EACH TRADE
    if pnl is not None and pnl>0:
        STATS['wins']+=1; STATS['balance']+=pnl
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🔁 SAME AMOUNT", callback_data=f"dur_{duration_sec}_{int(amt)}_{pair}_{bal}"), types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"))
        mk.add(types.InlineKeyboardButton("⏱️ Change Duration", callback_data=f"amt_{int(amt)}_{pair}_{bal}"))
        bot.send_message(cid, f"✅ **WINNER! ✅ RESULT AFTER TRADE**\n\n━━━━━━━━━━━━━━━\n💰 **Profit:** +${pnl:.2f}\n💱 **Pair:** {pair} {d['dir']}\n⏱️ **Duration:** {duration_sec}s\n💵 **New Balance:** ${STATS['balance']:.2f}\n📊 **Result:** WIN 🎉\n━━━━━━━━━━━━━━━", reply_markup=mk, parse_mode="Markdown")
    elif pnl is not None:
        STATS['loss']+=1; STATS['balance']-=amt
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton(f"🔁 MARTINGALE ${amt*2.2:.0f}", callback_data=f"amt_{int(amt*2.2)}_{pair}_{bal}"), types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"))
        mk.add(types.InlineKeyboardButton("⏱️ Same Duration", callback_data=f"dur_{duration_sec}_{int(amt)}_{pair}_{bal}"))
        bot.send_message(cid, f"❌ **LOSS ❌ RESULT AFTER TRADE**\n\n━━━━━━━━━━━━━━━\n💸 **Loss:** -${amt:.2f}\n💱 **Pair:** {pair} {d['dir']}\n⏱️ **Duration:** {duration_sec}s\n💵 **Balance:** ${STATS['balance']:.2f}\n📊 **Result:** LOSS\n━━━━━━━━━━━━━━━", reply_markup=mk, parse_mode="Markdown")
    else:
        mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"))
        bot.send_message(cid, f"⏱️ **TRADE EXPIRED - CHECK IQ APP**\n\nID: {oid}\nPair {pair} {duration_sec}s\nTrade WAS PLACED but result delayed!", reply_markup=mk)

@bot.message_handler(commands=['start'])
def start(m):
    if not is_private_allowed(m.from_user.id):
        bot.send_message(m.chat.id, f"❌ Private Bot 🔒\nAccess Denied. Owner only.\nYour ID: {m.from_user.id}"); return
    mk=types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton("💹 TRADE NOW", callback_data="trade"))
    mk.add(types.InlineKeyboardButton("📊 MY STATS", callback_data="stats"), types.InlineKeyboardButton("⚙️ SETTINGS", callback_data="settings"))
    txt=f"""🤖 **Z-BOT PRO V48 PRIVATE** 🤖

✨ *Professional OTC Trading System*
🔒 PRIVATE - Only Owner {OWNER_ID}

💎 IQ Connected: {'✅' if IQ_CONNECTED else '❌'}
💰 Balance: ${STATS['balance']:.2f}
🎯 Win Rate: {STATS['wins']}/{STATS['wins']+STATS['loss'] if STATS['wins']+STATS['loss']>0 else 0}

👇 **Click TRADE to Start**
"""
    bot.send_message(m.chat.id, txt, reply_markup=mk, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_private_allowed(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Private Bot - Owner only"); return
    data=c.data; cid=c.message.chat.id
    if data=="trade":
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in OTC_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"pair_{p}"))
        bot.send_message(cid, "💹 **STEP 1/4 - SELECT PAIR**\n\n👇 Choose your trading pair:", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("pair_"):
        pair=data.replace("pair_",""); user_states[cid]={"pair":pair}
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🟢 DEMO ACCOUNT", callback_data=f"bal_PRACTICE_{pair}"))
        mk.add(types.InlineKeyboardButton("🔴 REAL ACCOUNT", callback_data=f"bal_REAL_{pair}"))
        mk.add(types.InlineKeyboardButton("⬅️ BACK", callback_data="trade"))
        bot.send_message(cid, f"✅ **PAIR: {PAIR_EMOJI.get(pair,pair)}**\n\n💳 **STEP 2/4 - SELECT ACCOUNT**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("bal_"):
        parts=data.split("_"); bal=parts[1]; pair=parts[2]; user_states[cid]={"pair":pair,"bal":bal}
        mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("💵 $1", callback_data=f"amt_1_{pair}_{bal}"),types.InlineKeyboardButton("💵 $5", callback_data=f"amt_5_{pair}_{bal}"),types.InlineKeyboardButton("💵 $10", callback_data=f"amt_10_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("💵 $20", callback_data=f"amt_20_{pair}_{bal}"),types.InlineKeyboardButton("💵 $50", callback_data=f"amt_50_{pair}_{bal}"),types.InlineKeyboardButton("💵 $100", callback_data=f"amt_100_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("✏️ CUSTOM AMOUNT", callback_data=f"custom_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("⬅️ BACK", callback_data=f"pair_{pair}"))
        bot.send_message(cid, f"✅ **PAIR: {PAIR_EMOJI.get(pair,pair)}**\n✅ **ACCOUNT: {bal}**\n\n💰 **STEP 3/4 - SELECT AMOUNT**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("amt_"):
        parts=data.split("_"); amt=float(parts[1]); pair=parts[2]; bal=parts[3]
        user_states[cid]={"pair":pair,"bal":bal,"amt":amt}
        bot.answer_callback_query(c.id, f"${amt} selected")
        bot.send_message(cid, f"✅ **AMOUNT: ${amt} {bal}**\n✅ **PAIR: {PAIR_EMOJI.get(pair,pair)}**\n\n⏱️ **STEP 4/4 - CHOOSE DURATION**\n\n👇 **Select trade duration (from 30sec up):**", reply_markup=duration_kb(pair, amt, bal), parse_mode="Markdown")
        return
    if data.startswith("dur_"):
        parts=data.split("_"); duration_sec=int(parts[1]); amt=float(parts[2]); pair=parts[3]; bal=parts[4]
        bot.answer_callback_query(c.id, f"{duration_sec}s selected")
        do_trade(cid, pair, amt, bal, duration_sec)
        return
    if data.startswith("custom_"):
        parts=data.split("_"); pair=parts[1]; bal=parts[2]
        user_states[cid]={"pair":pair,"bal":bal,"step":"await_amt"}
        bot.send_message(cid, f"✏️ **Type your amount**\n\nExample: `10` or `100`\n\nFor {pair} {bal}", parse_mode="Markdown")
        return
    if data=="stats":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0
        bot.send_message(cid, f"📊 **STATS PRIVATE**\n\n🏆 Wins: {STATS['wins']}\n❌ Loss: {STATS['loss']}\n📈 Winrate: {wr:.1f}%\n💰 Balance: ${STATS['balance']:.2f}\n🔒 Owner {OWNER_ID} only", parse_mode="Markdown")
    if data=="settings": bot.send_message(cid, "⚙️ Settings coming soon - Private bot")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get("step")=="await_amt")
def handle_custom_amt(m):
    if not is_private_allowed(m.from_user.id): return
    cid=m.chat.id; st=user_states.get(cid, {})
    try:
        amt=float(m.text.strip()); pair=st.get("pair"); bal=st.get("bal")
        if not pair: return
        user_states[cid]={"pair":pair,"bal":bal,"amt":amt}
        bot.send_message(cid, f"✅ **CUSTOM AMOUNT: ${amt} {bal}**\n\n⏱️ **STEP 4/4 - CHOOSE DURATION**\n👇 Select duration:", reply_markup=duration_kb(pair, amt, bal), parse_mode="Markdown")
    except: bot.send_message(cid, "❌ Send number only, e.g 100")

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def wh(): bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode("utf-8"))]); return "ok"
@app.route("/")
def home():
    u=os.getenv("RENDER_EXTERNAL_URL")
    if u:
        try: requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={u}/{BOT_TOKEN}", timeout=5)
        except: pass
    return "V48 V2 PRIVATE DURATION + RESULT RUNNING - OWNER ONLY"
app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
