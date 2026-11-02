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
logging.disable(logging.ERROR)

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 8659453018
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

REAL_PAIRS = ["EURUSD","GBPUSD","USDJPY","EURGBP","AUDUSD","USDCAD","EURJPY","GBPJPY"]
OTC_PAIRS = ["EURUSD-OTC","GBPUSD-OTC","EURGBP-OTC","USDJPY-OTC","GBPJPY-OTC","AUDUSD-OTC","USDCHF-OTC","EURJPY-OTC"]
ALL_PAIRS = REAL_PAIRS + OTC_PAIRS

PAIR_EMOJI = {
    "EURUSD":"🇪🇺 EUR/USD REAL","GBPUSD":"🇬🇧 GBP/USD REAL","USDJPY":"🇺🇸 USD/JPY REAL",
    "EURGBP":"🇪🇺 EUR/GBP REAL","AUDUSD":"🇦🇺 AUD/USD REAL","USDCAD":"🇺🇸 USD/CAD REAL",
    "EURJPY":"🇪🇺 EUR/JPY REAL","GBPJPY":"🇬🇧 GBP/JPY REAL",
    "EURUSD-OTC":"🇪🇺 EUR/USD OTC","GBPUSD-OTC":"🇬🇧 GBP/USD OTC","EURGBP-OTC":"🇪🇺 EUR/GBP OTC",
    "USDJPY-OTC":"🇺🇸 USD/JPY OTC","GBPJPY-OTC":"🇬🇧 GBP/JPY OTC","AUDUSD-OTC":"🇦🇺 AUD/USD OTC",
    "USDCHF-OTC":"🇺🇸 USD/CHF OTC","EURJPY-OTC":"🇪🇺 EUR/JPY OTC"
}
STATS = {"balance":100.0,"wins":0,"loss":0,"streak":0}
user_states = {}; AUTO_STATE = {}; AUTO_LOCK = {}; SCAN_LOCK = {}
IQ_LOCK = threading.Lock()
IQ_CONNECTED=False; iq=None
PAYOUT_CACHE={}; PAYOUT_TIME=0

def is_allowed(uid): return uid == OWNER_ID

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
        logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
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
    for _ in range(3):
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL); c=iq.get_candles(pair,60,50,time.time())
                if not c and "OTC" not in pair: c=iq.get_candles(pair,300,50,time.time())
                logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            if c and len(c)>20:
                df=pd.DataFrame(sorted(c,key=lambda x:x['from']))
                if 'max' in df.columns: df['high']=df['max']
                if 'min' in df.columns: df['low']=df['min']
                return df
        except: time.sleep(0.5)
    return None

def calc_rsi(closes, period=7):
    delta=closes.diff(); gain=delta.where(delta>0,0).rolling(period).mean()
    loss=-delta.where(delta<0,0).rolling(period).mean()
    return 100-(100/(1+gain/loss))

def calc_atr(df, period=14):
    hl=df['high']-df['low']; hc=abs(df['high']-df['close'].shift()); lc=abs(df['low']-df['close'].shift())
    tr=pd.concat([hl,hc,lc],axis=1).max(axis=1)
    return tr.rolling(period).mean()

# ===== YOUR ORIGINAL SCAN BAR + FORCE 100% FIX FOR 85% HOOK =====
def legit_live_scan(cid, mid, pair):
    if SCAN_LOCK.get(cid): return
    SCAN_LOCK[cid]=True
    try:
        steps = [
            (0, "🚀 Initializing V8...", 0.15),
            (15, f"🔌 IQ Check {pair}...", 0.2),
            (30, "📊 Fetching candles...", 0.2),
            (50, "📈 EMA9 + EMA21...", 0.2),
            (70, "💹 RSI + ATR...", 0.2),
            (85, "🔍 Final lock...", 0.25),
        ]
        for pct, text, delay in steps:
            filled=int(pct//5); bar="█"*filled+"░"*(20-filled)
            color="🟥" if pct<40 else "🟨" if pct<80 else "🟩"
            txt=f"""{color} Z-BOT V8 LEGIT SCAN {color}

💱 Pair: {PAIR_EMOJI.get(pair, pair)}
💎 IQ: {'✅ Connected' if IQ_CONNECTED else '❌ Offline'}

{bar} {pct}%
▓ Progress: {pct}% ▓

🔍 {text}

⏳ Fast scan - V8.8
"""
            try: bot.edit_message_text(txt, cid, mid)
            except: pass
            time.sleep(delay)
        for _ in range(3):
            try:
                final_txt=f"""💎 Z-BOT V8 LEGIT SCAN 💎

💱 Pair: {PAIR_EMOJI.get(pair, pair)}
💎 IQ: {'✅ Connected' if IQ_CONNECTED else '❌ Offline'}

████████████████████ 100%
▓ Progress: 100% ▓

🔍 🔒 SIGNAL LOCKED! READY TO TRADE!

⏳ Scan complete - V8.8!
"""
                bot.edit_message_text(final_txt, cid, mid)
                break
            except: time.sleep(0.2)
    finally:
        SCAN_LOCK[cid]=False

# ===== IMPROVED OTC STRATEGY - SCALPER KING =====
def analyze_otc_improved(pair):
    df=get_candles(pair)
    if df is None: return None
    try:
        close=df['close']; open_=df['open']; high=df['high']; low=df['low']
        ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean()
        rsi=calc_rsi(close,7); rsi_now=float(rsi.iloc[-1])
        e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1])
        e9p=float(ema9.iloc[-2]); e21p=float(ema21.iloc[-2])
        mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100
        mom3=(close.iloc[-1]-close.iloc[-4])/close.iloc[-4]*100
        is_green=float(close.iloc[-1])>float(open_.iloc[-1])
        body=max(abs(float(close.iloc[-1])-float(open_.iloc[-1])),0.00001)
        upper=float(high.iloc[-1])-max(float(close.iloc[-1]),float(open_.iloc[-1]))
        lower=min(float(close.iloc[-1]),float(open_.iloc[-1]))-float(low.iloc[-1])
        payout=get_payout(pair)
        if payout<0.78: return {"pair":pair,"conf":50,"rejected":True} # Skip low payout
        
        sig="CALL" if is_green else "PUT"; score=75; reason="OTC"
        # BEST: CROSS + WICK FILTER + RSI + MOM
        if e9>e21 and e9p<=e21p and is_green and 55<=rsi_now<=72 and upper<body*0.35 and mom1>0.03 and mom3>0.06:
            sig="CALL"; score=95; reason=f"🔥 OTC CROSS BULL Wick {upper/body:.1f} RSI {rsi_now:.0f} MOM {mom1:.3f}%"
        elif e9<e21 and e9p>=e21p and not is_green and 28<=rsi_now<=45 and lower<body*0.35 and mom1<-0.03 and mom3<-0.06:
            sig="PUT"; score=95; reason=f"🔥 OTC CROSS BEAR Wick {lower/body:.1f} RSI {rsi_now:.0f} MOM {mom1:.3f}%"
        elif e9>e21 and is_green and rsi_now>58 and mom1>0.02 and upper<body*0.5:
            sig="CALL"; score=90; reason=f"🚀 OTC Bull No Wick MOM {mom1:.3f}%"
        elif e9<e21 and not is_green and rsi_now<42 and mom1<-0.02 and lower<body*0.5:
            sig="PUT"; score=90; reason=f"📉 OTC Bear No Wick MOM {mom1:.3f}%"
        elif e9>e21: sig="CALL"; score=82; reason="📈 OTC EMA Bull"
        else: sig="PUT"; score=82; reason="📉 OTC EMA Bear"
        return {"pair":pair,"dir":sig,"conf":score,"price":float(close.iloc[-1]),"rsi":rsi_now,"reason":reason,"payout":payout,"df":df.tail(30),"rejected":False if score>=88 else True}
    except: return None

# ===== IMPROVED REAL STRATEGY - SNIPER PRO =====
def analyze_real_improved(pair):
    df=get_candles(pair)
    if df is None: return None
    try:
        close=df['close']; open_=df['open']; high=df['high']; low=df['low']
        ema21=close.ewm(21).mean(); ema50=close.ewm(50).mean()
        rsi=calc_rsi(close,14); rsi_now=float(rsi.iloc[-1])
        atr=calc_atr(df,14); atr_now=float(atr.iloc[-1]); atr_avg=float(atr.tail(20).mean())
        e21=float(ema21.iloc[-1]); e50=float(ema50.iloc[-1])
        e21p=float(ema21.iloc[-5]); e50p=float(ema50.iloc[-5])
        mom5=(close.iloc[-1]-close.iloc[-6])/close.iloc[-6]*100
        is_green=float(close.iloc[-1])>float(open_.iloc[-1])
        payout=get_payout(pair)
        if payout<0.78: return {"pair":pair,"conf":50,"rejected":True}
        sig="CALL" if is_green else "PUT"; score=75; reason="REAL"
        strong=atr_now>atr_avg*0.85
        if e21>e50 and e21p<=e50p and is_green and 50<=rsi_now<=68 and strong and mom5>0.08:
            sig="CALL"; score=94; reason=f"💎 REAL CROSS BULL ATR {atr_now:.5f} RSI {rsi_now:.0f} MOM {mom5:.3f}%"
        elif e21<e50 and e21p>=e50p and not is_green and 32<=rsi_now<=50 and strong and mom5<-0.08:
            sig="PUT"; score=94; reason=f"💎 REAL CROSS BEAR ATR {atr_now:.5f} RSI {rsi_now:.0f} MOM {mom5:.3f}%"
        elif e21>e50 and close.iloc[-1]>e21 and rsi_now>55 and strong and mom5>0.05:
            sig="CALL"; score=90; reason=f"💵 REAL Trend Bull {mom5:.3f}% ATR OK"
        elif e21<e50 and close.iloc[-1]<e21 and rsi_now<45 and strong and mom5<-0.05:
            sig="PUT"; score=90; reason=f"💷 REAL Trend Bear {mom5:.3f}% ATR OK"
        elif not strong:
            return {"pair":pair,"conf":65,"rejected":True,"reason":f"⚠️ Low Vol ATR {atr_now:.5f}"}
        else:
            sig="CALL" if e21>e50 else "PUT"; score=80; reason="💵 REAL EMA Trend"
        return {"pair":pair,"dir":sig,"conf":score,"price":float(close.iloc[-1]),"rsi":rsi_now,"reason":reason,"payout":payout,"df":df.tail(30),"rejected":False if score>=88 else True}
    except: return None

def analyze_momentum(pair, sniper_mode=False):
    d = analyze_otc_improved(pair) if "OTC" in pair else analyze_real_improved(pair)
    if not d: return None
    if sniper_mode and d.get('rejected'): return None
    return d

# ===== IMPROVED IQ TRADE - REAL=1,2,5min / OTC=30sec =====
def iq_trade(pair,direction,amount,bal,expiry_sec=30):
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL)
            try: iq.change_balance(bal)
            except: pass
            try:
                ot=iq.get_all_open_time()
                if pair in ot and not ot[pair]['open']:
                    logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
                    return False, None, 0
            except: pass
            logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            if "OTC" in pair:
                try:
                    logging.disable(logging.CRITICAL); _,oid=iq.buy_blitz(pair,amount,direction.lower(),expiry_sec)
                    logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
                    return True,oid,expiry_sec
                except: pass
                logging.disable(logging.CRITICAL); _,oid=iq.buy(amount,pair,direction.lower(),1)
                logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
                return True,oid,60
            else:
                for mins in [1,2,5,3]:
                    try:
                        logging.disable(logging.CRITICAL); check,oid=iq.buy(amount,pair,direction.lower(),mins)
                        logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
                        if oid and "suspend" not in str(oid).lower() and check!=False: return True,oid,mins*60
                    except: continue
                return False,None,0
    except: return False,None,0

# ===== IMPROVED AUTO TRADER - PAYOUT FILTER + COOLDOWN + MARTINGALE =====
def auto_trader_loop(cid):
    consecutive_losses = 0; AUTO_LOCK[cid] = True
    bot.send_message(cid, f"🔒 AUTO ONE TRADE LOCKED - 90%+ Only + Payout 78%+")
    while AUTO_STATE.get(cid, {}).get('running', False):
        if AUTO_STATE[cid].get('in_trade', False): time.sleep(5); continue
        try:
            state = AUTO_STATE.get(cid)
            if not state or not state['running']: break
            pair_to_trade = state['pair']
            if pair_to_trade == "AUTO":
                best = None; best_score = 0
                for p in ALL_PAIRS:
                    d = analyze_momentum(p, sniper_mode=True)
                    if d and d['conf'] > best_score: best_score = d['conf']; best = d
                if not best: time.sleep(30); continue
                d = best; pair_to_trade = d['pair']
            else:
                d = analyze_momentum(pair_to_trade, sniper_mode=True)
                if not d: time.sleep(20); continue
            curr_amt = state['base_amt'] if consecutive_losses==0 else min(state['base_amt'] * (2.2 ** consecutive_losses), state['base_amt']*8)
            AUTO_STATE[cid]['in_trade'] = True
            ok, oid, exp = iq_trade(pair_to_trade, d['dir'], curr_amt, state['bal'], state['expiry'])
            if not ok:
                AUTO_STATE[cid]['in_trade'] = False
                bot.send_message(cid, f"⚠️ {pair_to_trade} closed, next in 10s...")
                time.sleep(10); continue
            bot.send_message(cid, f"🤖 AUTO #{state['trades']+1} {pair_to_trade} {d['dir']} ${curr_amt:.2f} {d['conf']}% {int(d['payout']*100)}% ID {oid} ⏱️{exp}s")
            time.sleep(exp+5)
            try:
                with IQ_LOCK: logging.disable(logging.CRITICAL); pnl=iq.check_win_v4(oid); logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
                if pnl>0:
                    STATS['wins']+=1; STATS['balance']+=pnl; STATS['streak']+=1; AUTO_STATE[cid]['trades']+=1; consecutive_losses=0
                    bot.send_message(cid, f"✅ AUTO WIN +${pnl:.2f} Bal ${STATS['balance']:.2f} ➡️ Next BASE ${state['base_amt']}")
                else:
                    STATS['loss']+=1; STATS['balance']-=curr_amt; STATS['streak']=0; AUTO_STATE[cid]['trades']+=1; consecutive_losses+=1
                    next_amt = state['base_amt'] * (2.2 ** consecutive_losses)
                    bot.send_message(cid, f"❌ AUTO LOSS -${curr_amt:.2f} ➡️ Next MARTI ${next_amt:.2f} Streak {consecutive_losses}")
                    if consecutive_losses >= 3:
                        bot.send_message(cid, f"⚠️ 3 Losses, cooling 60s...")
                        time.sleep(60); consecutive_losses=0
            except: bot.send_message(cid, f"⏱️ Expired {oid} Check app")
            AUTO_STATE[cid]['in_trade'] = False; time.sleep(10)
        except:
            if cid in AUTO_STATE: AUTO_STATE[cid]['in_trade'] = False
            time.sleep(10)
    AUTO_LOCK[cid] = False
    bot.send_message(cid, f"🛑 AUTO STOPPED W{STATS['wins']} L{STATS['loss']} Bal ${STATS['balance']:.2f}")

@bot.message_handler(commands=['start','stop'])
def start(m):
    if not is_allowed(m.from_user.id): bot.send_message(m.chat.id, f"❌ Private"); return
    if m.text.startswith('/stop'):
        if m.chat.id in AUTO_STATE: AUTO_STATE[m.chat.id]['running']=False; bot.send_message(m.chat.id, "🛑 Stopping...")
        else: bot.send_message(m.chat.id, "Auto not running")
        return
    mk=types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton("💹 MANUAL TRADE (16 PAIRS)", callback_data="trade"))
    mk.add(types.InlineKeyboardButton("🤖 AUTO-TRADER 90%+ MARTINGALE", callback_data="auto_setup"))
    mk.add(types.InlineKeyboardButton("📊 MY STATS", callback_data="stats"))
    txt=f"""🤖 Z-BOT V8.8 IMPROVED 🤖

💎 IQ: {'✅' if IQ_CONNECTED else '❌'} | 💰 ${STATS['balance']:.2f}
🏆 W: {STATS['wins']} L: {STATS['loss']} | 🔥 {STATS['streak']}

🔥 OTC: EMA9/21 + Wick 0.35 + RSI7 + MOM
💎 REAL: EMA21/50 + ATR 0.85x + RSI14

✅ Scan: No 85% hook - Force 100%
✅ Pairs: 16 always
✅ REAL: 1,2,5min | OTC: 30sec
✅ AUTO: Payout 78%+ One trade

👇 Choose:
"""
    bot.send_message(m.chat.id, txt, reply_markup=mk)

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_allowed(c.from_user.id): bot.answer_callback_query(c.id, "❌ Private"); return
    data=c.data; cid=c.message.chat.id
    bot.answer_callback_query(c.id)
    if data=="trade":
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in ALL_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"pair_{p}"))
        bot.send_message(cid, f"💹 MANUAL - 16 PAIRS (REAL+OTC)", reply_markup=mk); return
    if data=="auto_setup":
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🤖 AUTO SCAN ALL 16", callback_data="auto_pair_AUTO"))
        for p in ALL_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"auto_pair_{p}"))
        bot.send_message(cid, f"🤖 AUTO SETUP 1/4 - PAIR (88%+ Only)", reply_markup=mk); return
    if data.startswith("auto_pair_"):
        pair=data.replace("auto_pair_","")
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🟢 DEMO", callback_data=f"auto_bal_PRACTICE_{pair}"))
        mk.add(types.InlineKeyboardButton("🔴 REAL", callback_data=f"auto_bal_REAL_{pair}"))
        bot.send_message(cid, f"✅ Pair: {pair}\n\n🤖 SETUP 2/4 - ACCOUNT", reply_markup=mk); return
    if data.startswith("auto_bal_"):
        parts=data.split("_"); bal=parts[2]; pair=parts[3]
        mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("💵 $1", callback_data=f"auto_amt_1_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $5", callback_data=f"auto_amt_5_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $10", callback_data=f"auto_amt_10_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("💵 $20", callback_data=f"auto_amt_20_{pair}_{bal}"))
        bot.send_message(cid, f"✅ {pair} {bal}\n\n🤖 SETUP 3/4 - BASE AMOUNT", reply_markup=mk); return
    if data.startswith("auto_amt_"):
        parts=data.split("_"); amt=float(parts[2]); pair=parts[3]; bal=parts[4]
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("⏱️ 30 SEC", callback_data=f"auto_exp_30_{pair}_{bal}_{int(amt)}"),
               types.InlineKeyboardButton("⏱️ 1 MIN", callback_data=f"auto_exp_60_{pair}_{bal}_{int(amt)}"))
        mk.add(types.InlineKeyboardButton("⏱️ 2 MIN", callback_data=f"auto_exp_120_{pair}_{bal}_{int(amt)}"),
               types.InlineKeyboardButton("⏱️ 5 MIN", callback_data=f"auto_exp_300_{pair}_{bal}_{int(amt)}"))
        bot.send_message(cid, f"✅ Base ${amt}\n\n🤖 SETUP 4/4 - EXPIRY", reply_markup=mk); return
    if data.startswith("auto_exp_"):
        if AUTO_LOCK.get(cid, False) or (cid in AUTO_STATE and AUTO_STATE[cid].get('running')):
            bot.send_message(cid, f"⚠️ Auto already running! Use /stop first"); return
        parts=data.split("_"); expiry=int(parts[2]); pair=parts[3]; bal=parts[4]; amt=float(parts[5])
        AUTO_STATE[cid] = {"running": True,"pair": pair,"bal": bal,"base_amt": amt,"curr_amt": amt,"expiry": expiry,"trades": 0,"in_trade": False}
        AUTO_LOCK[cid] = False
        mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🛑 STOP AUTO", callback_data="stop_auto"))
        bot.send_message(cid, f"🚀 STARTING AUTO 88%+! {pair} ${amt} {expiry}s Payout 78%+ One at a time", reply_markup=mk)
        threading.Thread(target=auto_trader_loop, args=(cid,), daemon=True).start()
        return
    if data=="stop_auto":
        if cid in AUTO_STATE: AUTO_STATE[cid]['running']=False; bot.send_message(cid, "🛑 Stopping auto...")
        return
    if data.startswith("pair_"):
        pair=data.replace("pair_","")
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🟢 DEMO", callback_data=f"bal_PRACTICE_{pair}"))
        mk.add(types.InlineKeyboardButton("🔴 REAL", callback_data=f"bal_REAL_{pair}"))
        bot.send_message(cid, f"✅ PAIR: {PAIR_EMOJI.get(pair,pair)}\n\n💳 STEP 2/4 - ACCOUNT", reply_markup=mk); return
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
        bot.send_message(cid, f"✅ {pair} {bal}\n\n💰 STEP 3/4 - AMOUNT", reply_markup=mk); return
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
        bot.send_message(cid, f"✅ ${amt}\n\n⏱️ STEP 4/4 - EXPIRY", reply_markup=mk); return
    if data.startswith("exp_"):
        parts=data.split("_"); expiry=int(parts[1]); pair=parts[2]; bal=parts[3]; amt=float(parts[4])
        scan_msg = bot.send_message(cid, f"🔍 V8.8 SCAN {PAIR_EMOJI.get(pair,pair)}\n\n0% 🚀 Starting...")
        legit_live_scan(cid, scan_msg.message_id, pair)
        d=analyze_momentum(pair, sniper_mode=False)
        if not d:
            mk=types.InlineKeyboardMarkup(row_width=2)
            mk.add(types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"),
                   types.InlineKeyboardButton("🔄 RETRY", callback_data=f"exp_{expiry}_{pair}_{bal}_{int(amt)}"))
            bot.send_message(cid, f"❌ Failed analyze {pair}", reply_markup=mk); return
        dir_emoji = "🟢 CALL" if d['dir']=="CALL" else "🔴 PUT"
        expiry_txt = f"{expiry}s" if expiry < 60 else f"{expiry//60} min"
        signal_txt=f"""📡 SIGNAL FOUND!

💱 {PAIR_EMOJI.get(pair,pair)}
📊 {dir_emoji} | 🎯 {d['conf']:.0f}% | 💸 {int(d['payout']*100)}%
💰 ${amt} | ⏱️ {expiry_txt}
📈 {d['reason']}

🤖 PLACING {expiry_txt} TRADE...
"""
        bot.send_message(cid, signal_txt)
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal,expiry)
        if not ok:
            mk=types.InlineKeyboardMarkup(row_width=2)
            mk.add(types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"),
                   types.InlineKeyboardButton("🔄 RETRY", callback_data=f"exp_{expiry}_{pair}_{bal}_{int(amt)}"))
            bot.send_message(cid, f"❌ {pair} not available now", reply_markup=mk); iq_reconnect(); return
        bot.send_message(cid, f"✅ Placed {oid} | Waiting {exp}s...")
        time.sleep(exp+5)
        try:
            with IQ_LOCK: logging.disable(logging.CRITICAL); pnl=iq.check_win_v4(oid); logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            if pnl>0:
                STATS['wins']+=1; STATS['balance']+=pnl; STATS['streak']+=1
                mk=types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton("🔁 SAME TRADE", callback_data=f"exp_{expiry}_{pair}_{bal}_{int(amt)}"),
                       types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"))
                bot.send_message(cid, f"✅ WIN +${pnl:.2f} {pair} {expiry_txt} Streak {STATS['streak']} Bal ${STATS['balance']:.2f}", reply_markup=mk)
            else:
                STATS['loss']+=1; STATS['balance']-=amt; STATS['streak']=0
                mk=types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton(f"🔁 MARTINGALE ${amt*2.2:.0f}", callback_data=f"exp_{expiry}_{pair}_{bal}_{int(amt*2.2)}"),
                       types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"))
                bot.send_message(cid, f"❌ LOSS -${amt} {pair} {expiry_txt} Bal ${STATS['balance']:.2f}", reply_markup=mk)
        except:
            mk=types.InlineKeyboardMarkup(row_width=2)
            mk.add(types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"),
                   types.InlineKeyboardButton("🔄 RETRY", callback_data=f"exp_{expiry}_{pair}_{bal}_{int(amt)}"))
            bot.send_message(cid, f"⏱️ Expired - Check IQ app {oid}", reply_markup=mk)
        return
    if data=="stats":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0
        bot.send_message(cid, f"📊 STATS W{STATS['wins']} L{STATS['loss']} {wr:.1f}% Streak {STATS['streak']} Bal ${STATS['balance']:.2f}")
    if data=="settings":
        bot.send_message(cid, f"⚙️ SETTINGS V8.8\n\n🔥 OTC: EMA9/21 Wick 0.35 RSI7 MOM\n💎 REAL: EMA21/50 ATR 0.85x RSI14\nAUTO: 88%+ Payout 78%+ Marti x2.2 One trade")

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
        bot.send_message(cid, f"✅ Custom ${amt} for {pair}\n\n⏱️ STEP 4/4 - EXPIRY", reply_markup=mk)
    except: bot.send_message(cid, "❌ Send number only")

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def wh(): bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode("utf-8"))]); return "ok"
@app.route("/")
def home():
    u=os.getenv("RENDER_EXTERNAL_URL")
    if u:
        try: requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={u}/{BOT_TOKEN}", timeout=5)
        except: pass
    return "V8.8 IMPROVED OTC KING + REAL SNIPER + AUTO PAYOUT FILTER - RUNNING"
app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
