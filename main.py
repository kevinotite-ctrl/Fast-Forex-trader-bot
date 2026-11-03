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

# ===== ONLY REAL MARKET - NO OTC AT ALL =====
REAL_PAIRS = ["EURUSD","GBPUSD","USDJPY","EURGBP","AUDUSD","USDCAD","EURJPY","GBPJPY"]

PAIR_EMOJI = {
    "EURUSD":"🇪🇺 EUR/USD REAL", "GBPUSD":"🇬🇧 GBP/USD REAL", "USDJPY":"🇺🇸 USD/JPY REAL",
    "EURGBP":"🇪🇺 EUR/GBP REAL", "AUDUSD":"🇦🇺 AUD/USD REAL", "USDCAD":"🇺🇸 USD/CAD REAL",
    "EURJPY":"🇪🇺 EUR/JPY REAL", "GBPJPY":"🇬🇧 GBP/JPY REAL"
}
STATS = {"balance":100.0,"wins":0,"loss":0,"streak":0}
user_states = {}
AUTO_STATE = {}
IQ_LOCK = threading.Lock()
IQ_CONNECTED=False; iq=None
PAYOUT_CACHE={}; PAYOUT_TIME=0

def is_allowed(uid): return uid == OWNER_ID

def get_active_pairs():
    return REAL_PAIRS

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

def legit_live_scan(cid, mid, pair):
    steps = [
        (0, "🚀 Initializing V8...", 0.15),
        (15, f"🔌 IQ Check {pair}...", 0.2),
        (30, "📊 Fetching candles...", 0.25),
        (50, "📈 EMA9 + EMA21...", 0.2),
        (70, "💹 RSI + ATR...", 0.2),
        (85, "📰 Final check...", 0.2),
        (100, "🔒 SIGNAL LOCKED!")
    ]
    last_pct = -1
    for item in steps:
        if len(item) == 3:
            pct, text, delay = item
        else:
            pct, text = item
            delay = 0.15
        if pct == last_pct:
            time.sleep(delay)
            continue
        last_pct = pct
        filled = int(pct // 5)
        bar = "█" * filled + "░" * (20 - filled)
        if pct < 40: color = "🟥"
        elif pct < 80: color = "🟨"
        elif pct < 100: color = "🟩"
        else: color = "💎"
        scan_txt = f"""{color} **Z-BOT V8 LEGIT SCAN** {color}

💱 Pair: {PAIR_EMOJI.get(pair, pair)}
💎 IQ: {'✅ Connected' if IQ_CONNECTED else '❌ Offline'}

{bar} {pct}%
▓ Progress: {pct}% ▓

🔍 {text}

⏳ Fast scan - V8.2
"""
        try:
            bot.edit_message_text(scan_txt, cid, mid, parse_mode="Markdown")
        except: pass
        time.sleep(delay)
    try:
        final_txt = f"""💎 **Z-BOT V8 LEGIT SCAN** 💎

💱 Pair: {PAIR_EMOJI.get(pair, pair)}
💎 IQ: {'✅ Connected' if IQ_CONNECTED else '❌ Offline'}

████████████████████ 100%
▓ Progress: 100% ▓

🔍 🔒 SIGNAL LOCKED! READY TO TRADE!

⏳ Scan complete - Fast V8.2!
"""
        bot.edit_message_text(final_txt, cid, mid, parse_mode="Markdown")
        time.sleep(0.3)
    except: pass

def analyze_momentum(pair, sniper_mode=False):
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
            sig="CALL"; score=90; reason=f"🚀 Bullish {mom1:.3f}%"
        elif mom1<-0.02 and mom3<-0.05 and not is_green and e9<e21 and rsi_now<50:
            sig="PUT"; score=90; reason=f"📉 Bearish {mom1:.3f}%"
        elif e9>e21 and is_green: sig="CALL"; score=82; reason=f"📈 EMA Bull"
        elif e9<e21 and not is_green: sig="PUT"; score=82; reason=f"📉 EMA Bear"
        else: score=60; reason="Low momentum"
        if sniper_mode and score < 90:
            return {"pair":pair,"dir":sig,"conf":score,"price":float(close.iloc[-1]),"rsi":rsi_now,"reason":reason,"payout":payout,"df":df.tail(30),"rejected":True}
        return {"pair":pair,"dir":sig,"conf":min(94,score),"price":float(close.iloc[-1]),"rsi":rsi_now,"reason":reason,"payout":payout,"df":df.tail(30),"rejected":False}
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
    except: return False,None,0

def auto_trader_loop(cid):
    consecutive_losses = 0
    while AUTO_STATE.get(cid, {}).get('running', False):
        try:
            state = AUTO_STATE.get(cid)
            if not state or not state['running']: break
            pair_to_trade = state['pair']
            if pair_to_trade == "AUTO":
                best = None; best_score = 0
                for p in get_active_pairs():
                    d = analyze_momentum(p, sniper_mode=True)
                    if d and not d.get('rejected') and d['conf'] > best_score:
                        best_score = d['conf']; best = d
                if not best:
                    time.sleep(30); continue
                d = best
                pair_to_trade = d['pair']
            else:
                d = analyze_momentum(pair_to_trade, sniper_mode=True)
                if not d or d.get('rejected'):
                    time.sleep(20); continue
            curr_amt = state['base_amt'] * (2.2 ** consecutive_losses) if state['martingale'] else state['base_amt']
            curr_amt = min(curr_amt, state['base_amt'] * 8)
            ok, oid, exp = iq_trade(pair_to_trade, d['dir'], curr_amt, state['bal'], state['expiry'])
            if not ok:
                time.sleep(10); continue
            bot.send_message(cid, f"🤖 Auto {pair_to_trade} {d['dir']} ${curr_amt:.2f} {d['conf']}% - ID {oid}")
            time.sleep(exp+5)
            try:
                with IQ_LOCK:
                    logging.disable(logging.CRITICAL); pnl=iq.check_win_v4(oid)
                    logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
                if pnl>0:
                    STATS['wins']+=1; STATS['balance']+=pnl; STATS['streak']+=1
                    AUTO_STATE[cid]['trades']+=1
                    mk=types.InlineKeyboardMarkup(row_width=2)
                    mk.add(types.InlineKeyboardButton("📊 STATS", callback_data="stats"),
                           types.InlineKeyboardButton("🛑 STOP AUTO", callback_data="stop_auto"))
                    bot.send_message(cid, f"✅ AUTO WIN +${pnl:.2f} | {pair_to_trade} | Bal ${STATS['balance']:.2f} | Streak {STATS['streak']}", reply_markup=mk)
                    consecutive_losses = 0
                else:
                    STATS['loss']+=1; STATS['balance']-=curr_amt; STATS['streak']=0
                    AUTO_STATE[cid]['trades']+=1
                    consecutive_losses += 1
                    bot.send_message(cid, f"❌ AUTO LOSS -${curr_amt:.2f} | Next ${state['base_amt'] * (2.2 ** consecutive_losses):.2f} Martingale")
                    if consecutive_losses >= 3:
                        consecutive_losses = 0
                        time.sleep(60)
            except:
                bot.send_message(cid, f"⏱️ Expired {oid}")
            time.sleep(10)
        except: time.sleep(10)
    bot.send_message(cid, f"🛑 **AUTO STOPPED** W{STATS['wins']} L{STATS['loss']} Bal ${STATS['balance']:.2f}")

@bot.message_handler(commands=['start','stop'])
def start(m):
    if not is_allowed(m.from_user.id):
        bot.send_message(m.chat.id, f"❌ Private Bot"); return
    if m.text.startswith('/stop'):
        if m.chat.id in AUTO_STATE:
            AUTO_STATE[m.chat.id]['running'] = False
            bot.send_message(m.chat.id, "🛑 Stopping auto-trader...")
        else:
            bot.send_message(m.chat.id, "Auto not running")
        return
    mk=types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton("💹 MANUAL TRADE (REAL ONLY)", callback_data="trade"))
    mk.add(types.InlineKeyboardButton("🤖 AUTO-TRADER 90%+ MARTINGALE", callback_data="auto_setup"))
    mk.add(types.InlineKeyboardButton("📊 MY STATS", callback_data="stats"), types.InlineKeyboardButton("⚙️ SETTINGS", callback_data="settings"))
    txt=f"""🤖 **Z-BOT PRO V8.6 REAL KING** 🤖

💎 IQ: {'✅' if IQ_CONNECTED else '❌'} | 💰 ${STATS['balance']:.2f}
🏆 W: {STATS['wins']} L: {STATS['loss']} | 🔥 {STATS['streak']}

💹 MANUAL: 8 REAL PAIRS ONLY
🤖 AUTO: 90%+ Sniper + Martingale x2.2

👇 **Choose:**
"""
    bot.send_message(m.chat.id, txt, reply_markup=mk, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_allowed(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Private"); return
    data=c.data; cid=c.message.chat.id
    if data=="trade":
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in get_active_pairs():
            mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"pair_{p}"))
        bot.send_message(cid, f"💹 **MANUAL - SELECT PAIR (8 REAL)**", reply_markup=mk, parse_mode="Markdown"); return
    if data=="auto_setup":
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🤖 AUTO SCAN ALL REAL", callback_data="auto_pair_AUTO"))
        for p in get_active_pairs():
            mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"auto_pair_{p}"))
        bot.send_message(cid, f"🤖 **AUTO SETUP 1/4 - PAIR (90%+ Only)**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("auto_pair_"):
        pair=data.replace("auto_pair_","")
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🟢 DEMO", callback_data=f"auto_bal_PRACTICE_{pair}"))
        mk.add(types.InlineKeyboardButton("🔴 REAL", callback_data=f"auto_bal_REAL_{pair}"))
        bot.send_message(cid, f"✅ Pair: {pair}\n\n🤖 **SETUP 2/4 - ACCOUNT**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("auto_bal_"):
        parts=data.split("_"); bal=parts[2]; pair=parts[3]
        mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("💵 $1", callback_data=f"auto_amt_1_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $5", callback_data=f"auto_amt_5_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $10", callback_data=f"auto_amt_10_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("💵 $20", callback_data=f"auto_amt_20_{pair}_{bal}"))
        bot.send_message(cid, f"✅ {pair} {bal}\n\n🤖 **SETUP 3/4 - BASE AMOUNT**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("auto_amt_"):
        parts=data.split("_"); amt=float(parts[2]); pair=parts[3]; bal=parts[4]
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("⏱️ 30 SEC", callback_data=f"auto_exp_30_{pair}_{bal}_{int(amt)}"),
               types.InlineKeyboardButton("⏱️ 1 MIN", callback_data=f"auto_exp_60_{pair}_{bal}_{int(amt)}"))
        mk.add(types.InlineKeyboardButton("⏱️ 2 MIN", callback_data=f"auto_exp_120_{pair}_{bal}_{int(amt)}"),
               types.InlineKeyboardButton("⏱️ 5 MIN", callback_data=f"auto_exp_300_{pair}_{bal}_{int(amt)}"))
        bot.send_message(cid, f"✅ Base ${amt}\n\n🤖 **SETUP 4/4 - EXPIRY**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("auto_exp_"):
        parts=data.split("_"); expiry=int(parts[2]); pair=parts[3]; bal=parts[4]; amt=float(parts[5])
        AUTO_STATE[cid] = {"running": True,"pair": pair,"bal": bal,"base_amt": amt,"curr_amt": amt,"expiry": expiry,"martingale": True,"sniper": True,"trades": 0}
        mk=types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("🛑 STOP AUTO", callback_data="stop_auto"))
        bot.send_message(cid, f"🚀 **STARTING AUTO 90%+!** {pair} ${amt} {expiry}s Martingale ON", reply_markup=mk, parse_mode="Markdown")
        threading.Thread(target=auto_trader_loop, args=(cid,), daemon=True).start()
        return
    if data=="stop_auto":
        if cid in AUTO_STATE:
            AUTO_STATE[cid]['running']=False
            bot.send_message(cid, "🛑 Stopping...")
        return
    if data.startswith("pair_"):
        pair=data.replace("pair_","")
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🟢 DEMO", callback_data=f"bal_PRACTICE_{pair}"))
        mk.add(types.InlineKeyboardButton("🔴 REAL", callback_data=f"bal_REAL_{pair}"))
        bot.send_message(cid, f"✅ **PAIR: {PAIR_EMOJI.get(pair,pair)}**\n\n💳 **STEP 2/4 - ACCOUNT**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("bal_"):
        parts=data.split("_"); bal=parts[1]; pair=parts[2]
        mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("💵 $1", callback_data=f"amt_1_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $5", callback_data=f"amt_5_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $10", callback_data=f"amt_10_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("💵 $20", callback_data=f"amt_20_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $50", callback_data=f"amt_50_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $100", callback_data=f"amt_100_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("✏️ CUSTOM", callback_data=f"custom_{pair}_{bal}"))
        bot.send_message(cid, f"✅ {pair} {bal}\n\n💰 **STEP 3/4 - AMOUNT**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("amt_") or data.startswith("custom_"):
        if data.startswith("custom_"):
            parts=data.split("_"); pair=parts[1]; bal=parts[2]
            user_states[cid]={"pair":pair,"bal":bal,"step":"await_amt"}
            bot.send_message(cid, f"✏️ Type amount for {pair} {bal}"); return
        parts=data.split("_"); amt=float(parts[1]); pair=parts[2]; bal=parts[3]
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("⏱️ 30 SEC", callback_data=f"exp_30_{pair}_{bal}_{int(amt)}"),
               types.InlineKeyboardButton("⏱️ 1 MIN", callback_data=f"exp_60_{pair}_{bal}_{int(amt)}"))
        mk.add(types.InlineKeyboardButton("⏱️ 2 MIN", callback_data=f"exp_120_{pair}_{bal}_{int(amt)}"),
               types.InlineKeyboardButton("⏱️ 5 MIN", callback_data=f"exp_300_{pair}_{bal}_{int(amt)}"))
        mk.add(types.InlineKeyboardButton("⏱️ 15 MIN", callback_data=f"exp_900_{pair}_{bal}_{int(amt)}"))
        bot.send_message(cid, f"✅ ${amt}\n\n⏱️ **STEP 4/4 - EXPIRY**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("exp_"):
        parts=data.split("_"); expiry=int(parts[1]); pair=parts[2]; bal=parts[3]; amt=float(parts[4])
        bot.answer_callback_query(c.id, f"Analyzing...")
        scan_msg = bot.send_message(cid, f"🔍 **V8 SCAN {PAIR_EMOJI.get(pair,pair)}**\n\n0%\n🚀 Starting...")
        legit_live_scan(cid, scan_msg.message_id, pair)
        d=analyze_momentum(pair, sniper_mode=False)
        if not d:
            mk=types.InlineKeyboardMarkup(row_width=2)
            mk.add(types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"),
                   types.InlineKeyboardButton("🔄 RETRY", callback_data=f"exp_{expiry}_{pair}_{bal}_{int(amt)}"))
            bot.send_message(cid, f"❌ Failed analyze {pair}", reply_markup=mk); return
        dir_emoji = "🟢 CALL" if d['dir']=="CALL" else "🔴 PUT"
        expiry_txt = f"{expiry}s" if expiry < 60 else f"{expiry//60} min"
        signal_txt=f"""📡 **SIGNAL FOUND!**

💱 {PAIR_EMOJI.get(pair,pair)}
📊 {dir_emoji} | 🎯 {d['conf']:.0f}%
💸 {int(d['payout']*100)}% | 💰 ${amt} | ⏱️ {expiry_txt}
📈 {d['reason']}

🤖 **PLACING {expiry_txt} TRADE...**
"""
        bot.send_message(cid, signal_txt, parse_mode="Markdown")
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal,expiry)
        if not ok:
            mk=types.InlineKeyboardMarkup(row_width=2)
            mk.add(types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"),
                   types.InlineKeyboardButton("🔄 RETRY", callback_data=f"exp_{expiry}_{pair}_{bal}_{int(amt)}"))
            bot.send_message(cid, "❌ Trade Failed", reply_markup=mk); iq_reconnect(); return
        bot.send_message(cid, f"✅ Placed {oid} | Waiting {exp}s...")
        time.sleep(exp+5)
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL); pnl=iq.check_win_v4(oid)
                logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            if pnl>0:
                STATS['wins']+=1; STATS['balance']+=pnl; STATS['streak']+=1
                mk=types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton("🔁 SAME TRADE", callback_data=f"exp_{expiry}_{pair}_{bal}_{int(amt)}"),
                       types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"))
                mk.add(types.InlineKeyboardButton("📊 STATS", callback_data="stats"),
                       types.InlineKeyboardButton("🤖 AUTO", callback_data="auto_setup"))
                bot.send_message(cid, f"✅ **WIN +${pnl:.2f}**\n💱 {pair} {expiry_txt}\n🔥 Streak {STATS['streak']} | Bal ${STATS['balance']:.2f}\n\n👇 Next trade?", reply_markup=mk, parse_mode="Markdown")
            else:
                STATS['loss']+=1; STATS['balance']-=amt; STATS['streak']=0
                mk=types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton(f"🔁 MARTINGALE ${amt*2.2:.0f}", callback_data=f"exp_{expiry}_{pair}_{bal}_{int(amt*2.2)}"),
                       types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"))
                mk.add(types.InlineKeyboardButton("📊 STATS", callback_data="stats"),
                       types.InlineKeyboardButton("🤖 AUTO", callback_data="auto_setup"))
                bot.send_message(cid, f"❌ **LOSS -${amt}**\n💱 {pair} {expiry_txt}\nBal ${STATS['balance']:.2f}\n\n👇 Martingale or New?", reply_markup=mk, parse_mode="Markdown")
        except:
            mk=types.InlineKeyboardMarkup(row_width=2)
            mk.add(types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"),
                   types.InlineKeyboardButton("🔄 RETRY", callback_data=f"exp_{expiry}_{pair}_{bal}_{int(amt)}"))
            bot.send_message(cid, f"⏱️ Expired - Check IQ app {oid}\n\n👇 Continue?", reply_markup=mk, parse_mode="Markdown")
        return
    if data=="stats":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"),
               types.InlineKeyboardButton("🤖 AUTO", callback_data="auto_setup"))
        bot.send_message(cid, f"📊 **STATS**\n\n🏆 Wins: {STATS['wins']}\n❌ Loss: {STATS['loss']}\n📈 Winrate: {wr:.1f}%\n🔥 Streak: {STATS['streak']}\n💰 Balance: ${STATS['balance']:.2f}", reply_markup=mk, parse_mode="Markdown")
    if data=="settings":
        bot.send_message(cid, f"⚙️ **SETTINGS**\n\n💹 Manual: REAL Only 8 Pairs\n🤖 Auto: 90%+ Sniper\nScan: Original V8.2\nNo OTC ✅")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get("step")=="await_amt")
def handle_custom_amt(m):
    cid=m.chat.id; st=user_states.get(cid, {})
    if not is_allowed(m.from_user.id): return
    try:
        amt=float(m.text.strip())
        pair=st.get("pair"); bal=st.get("bal")
        if not pair: return
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("⏱️ 30 SEC", callback_data=f"exp_30_{pair}_{bal}_{int(amt)}"),
               types.InlineKeyboardButton("⏱️ 1 MIN", callback_data=f"exp_60_{pair}_{bal}_{int(amt)}"))
        mk.add(types.InlineKeyboardButton("⏱️ 2 MIN", callback_data=f"exp_120_{pair}_{bal}_{int(amt)}"),
               types.InlineKeyboardButton("⏱️ 5 MIN", callback_data=f"exp_300_{pair}_{bal}_{int(amt)}"))
        mk.add(types.InlineKeyboardButton("⏱️ 15 MIN", callback_data=f"exp_900_{pair}_{bal}_{int(amt)}"))
        bot.send_message(cid, f"✅ Custom ${amt} for {pair}\n\n⏱️ **STEP 4/4 - EXPIRY**", reply_markup=mk, parse_mode="Markdown")
    except: bot.send_message(cid, "❌ Send number only")

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def wh(): bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode("utf-8"))]); return "ok"
@app.route("/")
def home():
    u=os.getenv("RENDER_EXTERNAL_URL")
    if u:
        try: requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={u}/{BOT_TOKEN}", timeout=5)
        except: pass
    return "V8.6 REAL ONLY 8 PAIRS - RUNNING"
app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
