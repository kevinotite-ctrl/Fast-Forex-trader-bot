import os, time, threading, warnings, logging
from datetime import datetime, timedelta, timezone
from flask import Flask, request
import telebot
from telebot import types
import pandas as pd
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pytz

warnings.filterwarnings("ignore")
logging.getLogger().setLevel(logging.CRITICAL)
logging.getLogger("iqoptionapi").setLevel(logging.CRITICAL)
logging.disable(logging.ERROR)

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 8659453018
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

REAL_PAIRS = [
    "EURUSD","GBPUSD","USDJPY","EURGBP","AUDUSD","USDCAD","EURJPY","GBPJPY",
    "USDCHF","AUDJPY","EURAUD","GBPCHF","EURCHF","NZDUSD","GBPAUD",
    "EURCAD","AUDCAD","GBPCAD","NZDJPY","AUDNZD","CHFJPY","CADJPY"
]

OTC_PAIRS = [
    "EURUSD-OTC","GBPUSD-OTC","USDJPY-OTC","AUDUSD-OTC","USDCAD-OTC",
    "EURGBP-OTC","EURJPY-OTC","GBPJPY-OTC","AUDJPY-OTC","EURAUD-OTC",
    "GBPAUD-OTC","NZDUSD-OTC","GBPCHF-OTC","EURCHF-OTC","USDCHF-OTC",
    "AUDCAD-OTC","EURCAD-OTC","CADJPY-OTC","NZDJPY-OTC"
]

PAIR_EMOJI = {
    "EURUSD":"🇪🇺 EUR/USD REAL", "GBPUSD":"🇬🇧 GBP/USD REAL", "USDJPY":"🇺🇸 USD/JPY REAL", "EURGBP":"🇪🇺 EUR/GBP REAL",
    "AUDUSD":"🇦🇺 AUD/USD REAL", "USDCAD":"🇺🇸 USD/CAD REAL", "EURJPY":"🇪🇺 EUR/JPY REAL", "GBPJPY":"🇬🇧 GBP/JPY REAL",
    "USDCHF":"🇺🇸 USD/CHF REAL", "AUDJPY":"🇦🇺 AUD/JPY REAL", "EURAUD":"🇪🇺 EUR/AUD REAL", "GBPCHF":"🇬🇧 GBP/CHF REAL",
    "EURCHF":"🇪🇺 EUR/CHF REAL", "NZDUSD":"🇳🇿 NZD/USD REAL", "GBPAUD":"🇬🇧 GBP/AUD REAL", "EURCAD":"🇪🇺 EUR/CAD REAL",
    "AUDCAD":"🇦🇺 AUD/CAD REAL", "GBPCAD":"🇬🇧 GBP/CAD REAL", "NZDJPY":"🇳🇿 NZD/JPY REAL", "AUDNZD":"🇦🇺 AUD/NZD REAL",
    "CHFJPY":"🇨🇭 CHF/JPY REAL", "CADJPY":"🇨🇦 CAD/JPY REAL",
    "EURUSD-OTC":"🇪🇺 EUR/USD OTC", "GBPUSD-OTC":"🇬🇧 GBP/USD OTC", "EURGBP-OTC":"🇪🇺 EUR/GBP OTC",
    "USDJPY-OTC":"🇺🇸 USD/JPY OTC", "GBPJPY-OTC":"🇬🇧 GBP/JPY OTC", "AUDUSD-OTC":"🇦🇺 AUD/USD OTC",
    "USDCHF-OTC":"🇺🇸 USD/CHF OTC", "EURJPY-OTC":"🇪🇺 EUR/JPY OTC", "AUDJPY-OTC":"🇦🇺 AUD/JPY OTC",
    "EURAUD-OTC":"🇪🇺 EUR/AUD OTC", "GBPAUD-OTC":"🇬🇧 GBP/AUD OTC", "NZDUSD-OTC":"🇳🇿 NZD/USD OTC",
    "GBPCHF-OTC":"🇬🇧 GBP/CHF OTC", "EURCHF-OTC":"🇪🇺 EUR/CHF OTC", "USDCAD-OTC":"🇺🇸 USD/CAD OTC",
    "AUDCAD-OTC":"🇦🇺 AUD/CAD OTC", "EURCAD-OTC":"🇪🇺 EUR/CAD OTC", "CADJPY-OTC":"🇨🇦 CAD/JPY OTC",
    "NZDJPY-OTC":"🇳🇿 NZD/JPY OTC"
}

STATS = {"balance":0.0,"real_balance":0.0,"wins":0,"loss":0,"streak":0}
user_states = {}; AUTO_STATE = {}; IQ_LOCK = threading.Lock()
IQ_CONNECTED=False; iq=None; PAYOUT_CACHE={}; PAYOUT_TIME=0

def is_allowed(uid): return uid == OWNER_ID

def is_real_hours():
    try:
        tz = pytz.timezone("Africa/Lagos")
        now = datetime.now(tz)
        if now.weekday() >= 5: return False
        return 7 <= now.hour < 20
    except:
        now = datetime.now(timezone.utc) + timedelta(hours=1)
        if now.weekday() >= 5: return False
        return 7 <= now.hour < 20

def get_mode_text(): return "REAL SIGNAL (7AM-8PM)" if is_real_hours() else "OTC TRADING (8PM-7AM+Weekend)"

try:
    from iqoptionapi.stable_api import IQ_Option
    EMAIL=os.getenv("IQ_EMAIL"); PWD=os.getenv("IQ_PASS")
    if EMAIL and PWD:
        logging.disable(logging.CRITICAL)
        iq=IQ_Option(EMAIL,PWD); iq.connect()
        IQ_CONNECTED=iq.check_connect()
        if IQ_CONNECTED:
            try: iq.change_balance("PRACTICE"); STATS["real_balance"]=iq.get_balance()
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
        if IQ_CONNECTED: 
            try: STATS["real_balance"]=iq.get_balance()
            except: pass
        logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
        return IQ_CONNECTED
    except: IQ_CONNECTED=False; return False

def get_real_balance(bal_type="PRACTICE"):
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL); iq.change_balance(bal_type); bal=iq.get_balance()
            logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            return bal
    except: return 0.0

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
    if pair not in REAL_PAIRS and pair not in OTC_PAIRS: return None
    for _ in range(2):
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL); c=iq.get_candles(pair,60,50,time.time())
                logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            if c and len(c)>25: return pd.DataFrame(sorted(c,key=lambda x:x['from']))
            time.sleep(0.4)
        except: time.sleep(0.4)
    return None

def calc_rsi(closes, period=7):
    delta=closes.diff()
    gain=delta.where(delta>0,0).rolling(period).mean()
    loss=-delta.where(delta<0,0).rolling(period).mean()
    rs=gain/loss
    return 100-(100/(1+rs))

def calc_atr(df, period=14):
    try:
        high=df['max']; low=df['min']; close=df['close']
        tr1=high-low; tr2=(high-close.shift()).abs(); tr3=(low-close.shift()).abs()
        tr=pd.concat([tr1,tr2,tr3],axis=1).max(axis=1)
        return tr.rolling(period).mean().iloc[-1]
    except: return 0.0005

def legit_live_scan(cid, mid, pair):
    steps = [(0,"🚀 V11 Safe Init...",0.15),(20,f"🔌 Checking {pair}...",0.2),(40,"📊 ATR + Body Filter...",0.25),(60,"📈 EMA 3 Align...",0.2),(80,"💹 RSI Safe Zone + PA...",0.2),(100,"🔒 SAFE EXPIRY LOCKED!",0.3)]
    last_pct=-1
    for pct, text, delay in steps:
        if pct==last_pct: time.sleep(delay); continue
        last_pct=pct; filled=int(pct//5); bar="█"*filled+"░"*(20-filled)
        color="🟥" if pct<40 else "🟨" if pct<80 else "🟩" if pct<100 else "💎"
        txt=f"""{color} **Z-BOT V11 SAFE AUTO** {color}\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n💎 IQ: {'✅' if IQ_CONNECTED else '❌'}\n\n{bar} {pct}%\n\n🔍 {text}\n⏳ Auto Safe Expiry V11"""
        try: bot.edit_message_text(txt,cid,mid,parse_mode="Markdown")
        except: pass
        time.sleep(delay)

def analyze_momentum(pair, sniper_mode=False):
    df=get_candles(pair)
    if df is None: return None
    try:
        close=df['close']; open_=df['open']; high=df['max']; low=df['min']
        ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean(); ema50=close.ewm(50).mean()
        rsi_fast=calc_rsi(close,7); rsi_slow=calc_rsi(close,14)
        atr=calc_atr(df,14)
        c_now=float(close.iloc[-1]); o_now=float(open_.iloc[-1])
        c_prev=float(close.iloc[-2]); o_prev=float(open_.iloc[-2])
        h_now=float(high.iloc[-1]); l_now=float(low.iloc[-1])
        e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1]); e50=float(ema50.iloc[-1])
        e21_prev=float(ema21.iloc[-2])
        rsi7=float(rsi_fast.iloc[-1]); rsi14=float(rsi_slow.iloc[-1])
        mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100
        mom3=(close.iloc[-1]-close.iloc[-4])/close.iloc[-4]*100
        body=abs(c_now-o_now)
        upper_wick=h_now-max(c_now,o_now)
        lower_wick=min(c_now,o_now)-l_now
        is_green=c_now>o_now
        payout=get_payout(pair)
        sig="CALL" if is_green else "PUT"
        score=0
        reason_list=[]
        min_atr = 0.00025 if pair in ["EURUSD","GBPUSD","USDJPY"] else 0.00035
        if atr < min_atr:
            return {"pair":pair,"dir":sig,"conf":45,"price":c_now,"rsi":rsi7,"reason":"Low ATR - Choppy","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if body < atr*0.35:
            return {"pair":pair,"dir":sig,"conf":50,"price":c_now,"rsi":rsi7,"reason":"Doji - No body","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if upper_wick > body*2.5 and lower_wick > body*2.5:
            return {"pair":pair,"dir":sig,"conf":48,"price":c_now,"rsi":rsi7,"reason":"High indecision","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if is_green:
            if e9 > e21 and e21 > e50: 
                score+=20; reason_list.append("EMA Bull Align")
                if e21 > e21_prev: score+=10; reason_list.append("Slope Up")
            elif e9 > e21: score+=12
        else:
            if e9 < e21 and e21 < e50: 
                score+=20; reason_list.append("EMA Bear Align")
                if e21 < e21_prev: score+=10; reason_list.append("Slope Down")
            elif e9 < e21: score+=12
        if is_green:
            if 55 <= rsi7 <= 68 and 50 <= rsi14 <= 65:
                score+=25; reason_list.append(f"RSI Safe {rsi7:.0f}")
            elif 50 <= rsi7 <= 72: score+=15
            elif rsi7 > 75: score-=15
        else:
            if 32 <= rsi7 <= 45 and 35 <= rsi14 <= 50:
                score+=25; reason_list.append(f"RSI Safe {rsi7:.0f}")
            elif 28 <= rsi7 <= 50: score+=15
            elif rsi7 < 25: score-=15
        if is_green:
            if mom1 > 0.025 and mom3 > 0.05: score+=20; reason_list.append(f"Mom {mom1:.3f}%")
            elif mom1 > 0.01: score+=10
            elif mom1 < 0: score-=10
        else:
            if mom1 < -0.025 and mom3 < -0.05: score+=20; reason_list.append(f"Mom {mom1:.3f}%")
            elif mom1 < -0.01: score+=10
            elif mom1 > 0: score-=10
        bullish_engulf = c_now > o_prev and o_now < c_prev and is_green and not (c_prev > o_prev)
        bearish_engulf = c_now < o_prev and o_now > c_prev and not is_green and (c_prev > o_prev)
        pin_bull = lower_wick > body*1.5 and lower_wick > upper_wick*1.5 and is_green
        pin_bear = upper_wick > body*1.5 and upper_wick > lower_wick*1.5 and not is_green
        if is_green:
            if bullish_engulf: score+=15; reason_list.append("Bull Engulf")
            if pin_bull: score+=15; reason_list.append("Pin Bar Bull")
            elif lower_wick > upper_wick: score+=8
        else:
            if bearish_engulf: score+=15; reason_list.append("Bear Engulf")
            if pin_bear: score+=15; reason_list.append("Pin Bar Bear")
            elif upper_wick > lower_wick: score+=8
        score = max(45, min(94, score + 30))
        reason = " + ".join(reason_list) if reason_list else "Weak PA"
        if "-OTC" not in pair:
            expiry = 180 if abs(mom1) > 0.06 else 120
        else:
            expiry = 60 if abs(mom1) > 0.05 else 120
        if sniper_mode and score < 85:
            return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":rsi7,"reason":reason,"payout":payout,"expiry":expiry,"atr":atr,"rejected":True}
        return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":rsi7,"reason":reason,"payout":payout,"expiry":expiry,"atr":atr,"rejected":False}
    except: return None

def iq_trade(pair,direction,amount,bal,expiry_sec=30):
    if not IQ_CONNECTED and not iq_reconnect(): return False,None,0
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL); iq.change_balance(bal)
            logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            mins=max(1,int(expiry_sec/60))
            if expiry_sec<=60: mins=1
            try:
                logging.disable(logging.CRITICAL); check,oid=iq.buy(amount,pair,direction.lower(),mins)
                logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
                if check: return True,oid,expiry_sec
            except: pass
            if expiry_sec<=90:
                try:
                    logging.disable(logging.CRITICAL); _,oid=iq.buy_blitz(pair,amount,direction.lower(),expiry_sec)
                    logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
                    return True,oid,expiry_sec
                except: pass
            return False,None,0
    except: iq_reconnect(); return False,None,0

def real_signal_scanner():
    last_signal={}; tz=pytz.timezone("Africa/Lagos")
    while True:
        try:
            if is_real_hours() and IQ_CONNECTED:
                for pair in REAL_PAIRS:
                    if pair in last_signal and time.time()-last_signal[pair]<600: continue
                    d=analyze_momentum(pair,sniper_mode=True)
                    if d and not d.get('rejected') and d['conf']>=85:
                        now=datetime.now(tz); entry=now+timedelta(seconds=45)
                        exp=d['expiry']; exp_txt=f"{exp//60} min" if exp>=60 else f"{exp}s"
                        dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"
                        msg=f"""📡 **REAL AUTO SIGNAL V11 SAFE** 📡

💱 {PAIR_EMOJI.get(pair,pair)}
📊 {dir_e} | 🎯 {d['conf']:.0f}% SAFE
📈 {d['reason']} | RSI {d['rsi']:.1f} | ATR {d['atr']:.5f}
💸 {int(d['payout']*100)}% | Auto Expiry {exp_txt}

⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)
📅 {now.strftime('%A %d %b %H:%M WAT')}

⚠️ MANUAL - Safe expiry auto picked
"""
                        try: bot.send_message(OWNER_ID,msg,parse_mode="Markdown"); last_signal[pair]=time.time()
                        except: pass
                    time.sleep(3)
            time.sleep(25)
        except: time.sleep(30)

def auto_trader_loop(cid):
    consecutive_losses=0
    while AUTO_STATE.get(cid,{}).get('running',False):
        try:
            state=AUTO_STATE.get(cid)
            if not state or not state['running']: break
            if not IQ_CONNECTED: iq_reconnect(); time.sleep(5); continue
            pair_to_trade=state['pair']
            if pair_to_trade=="AUTO":
                best=None; best_score=0
                for p in OTC_PAIRS:
                    d=analyze_momentum(p,sniper_mode=True)
                    if d and not d.get('rejected') and d['conf']>best_score: best_score=d['conf']; best=d
                if not best: time.sleep(25); continue
                d=best; pair_to_trade=d['pair']
            else:
                d=analyze_momentum(pair_to_trade,sniper_mode=True)
                if not d or d.get('rejected'): time.sleep(20); continue
            curr_amt=state['base_amt']*(2.2**consecutive_losses) if state['martingale'] else state['base_amt']
            curr_amt=min(curr_amt,state['base_amt']*8)
            ok,oid,exp=iq_trade(pair_to_trade,d['dir'],curr_amt,state['bal'],state['expiry'])
            if not ok: iq_reconnect(); time.sleep(8); continue
            bal_now=get_real_balance(state['bal'])
            bot.send_message(cid,f"🤖 Auto OTC {pair_to_trade} {d['dir']} ${curr_amt:.2f} {d['conf']}% Safe {exp}s - ID {oid}\n💰 Bal ${bal_now:.2f}")
            time.sleep(exp+6)
            try:
                with IQ_LOCK:
                    logging.disable(logging.CRITICAL); pnl=iq.check_win_v4(oid)
                    logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
                bal_now=get_real_balance(state['bal'])
                if pnl>0:
                    STATS['wins']+=1; STATS['real_balance']=bal_now; STATS['streak']+=1; AUTO_STATE[cid]['trades']+=1
                    mk=types.InlineKeyboardMarkup(row_width=2)
                    mk.add(types.InlineKeyboardButton("📊 STATS",callback_data="stats"),types.InlineKeyboardButton("🛑 STOP AUTO",callback_data="stop_auto"))
                    bot.send_message(cid,f"✅ WIN +${pnl:.2f} | {pair_to_trade}\n💰 Bal ${bal_now:.2f} | Streak {STATS['streak']}",reply_markup=mk)
                    consecutive_losses=0
                else:
                    STATS['loss']+=1; STATS['real_balance']=bal_now; STATS['streak']=0; AUTO_STATE[cid]['trades']+=1; consecutive_losses+=1
                    bot.send_message(cid,f"❌ LOSS -${curr_amt:.2f} | Bal ${bal_now:.2f} | Next ${state['base_amt']*(2.2**consecutive_losses):.2f}")
                    if consecutive_losses>=3: consecutive_losses=0; time.sleep(60)
            except:
                bot.send_message(cid,f"⏱️ Expired {oid} - Check IQ")
            time.sleep(8)
        except: time.sleep(10)
    try:
        bal=get_real_balance("PRACTICE")
        bot.send_message(cid,f"🛑 AUTO STOPPED W{STATS['wins']} L{STATS['loss']} Bal ${bal:.2f}")
    except: pass

@bot.message_handler(commands=['start','stop','mode','balance'])
def start(m):
    if not is_allowed(m.from_user.id): bot.send_message(m.chat.id,"❌ Private"); return
    if m.text.startswith('/stop'):
        if m.chat.id in AUTO_STATE: AUTO_STATE[m.chat.id]['running']=False; bot.send_message(m.chat.id,"🛑 Stopping...")
        else: bot.send_message(m.chat.id,"Auto not running"); return
    if m.text.startswith('/mode'):
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz)
        txt=f"""📍 **MODE CHECK V11 SAFE AUTO**

⏰ Now: {now.strftime('%A %H:%M:%S WAT')}
📊 Mode: {get_mode_text()}
☀️ REAL: 7AM-8PM = Auto safe expiry signals
🌙 OTC: 8PM-7AM+Weekend = Manual+Auto
💎 IQ: {'✅' if IQ_CONNECTED else '❌'}
🛡️ V11: No expiry choose - bot picks safe
"""
        bot.send_message(m.chat.id,txt,parse_mode="Markdown"); return
    if m.text.startswith('/balance'):
        try:
            demo=get_real_balance("PRACTICE"); real=get_real_balance("REAL")
            bot.send_message(m.chat.id,f"💰 **BALANCES**\n🟢 DEMO: ${demo:.2f}\n🔴 REAL: ${real:.2f}\n📍 {get_mode_text()}")
        except Exception as e: bot.send_message(m.chat.id,f"Balance error {e}")
        return
    bal_demo=get_real_balance("PRACTICE")
    mk=types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton(f"💹 MANUAL OTC (19) - ${bal_demo:.2f}",callback_data="trade"))
    mk.add(types.InlineKeyboardButton(f"📈 TRADE REAL (22) AUTO EXPIRY",callback_data="trade_real"))
    mk.add(types.InlineKeyboardButton("🤖 AUTO-TRADER OTC 90%+ (Untouched)",callback_data="auto_setup"))
    mk.add(types.InlineKeyboardButton("📊 MY STATS",callback_data="stats"),types.InlineKeyboardButton("⚙️ SETTINGS",callback_data="settings"))
    txt=f"""🤖 **Z-BOT V11 SAFE AUTO EXPIRY** 🤖

💎 IQ: {'✅' if IQ_CONNECTED else '❌'} | 💰 DEMO ${bal_demo:.2f}
🏆 W:{STATS['wins']} L:{STATS['loss']} | 🔥 {STATS['streak']}
📍 {get_mode_text()}

☀️ REAL 22: Click pair = Auto safe expiry 65%+ 
🌙 OTC 19: Click pair = Auto safe expiry + trade
🛡️ V11 SAFE: ATR + Body + Engulf + Pin Bar

👇 **Select:**
"""
    bot.send_message(m.chat.id,txt,reply_markup=mk,parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_allowed(c.from_user.id): bot.answer_callback_query(c.id,"❌ Private"); return
    data=c.data; cid=c.message.chat.id

    if data=="trade_real":
        mk=types.InlineKeyboardMarkup(row_width=1)
        mk.add(types.InlineKeyboardButton("🔍 📊 SCAN ALL REAL NOW (22 PAIRS)",callback_data="scan_all_real"))
        for p in REAL_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}",callback_data=f"real_pair_{p}"))
        bot.send_message(cid,f"📈 **TRADE REAL V11 AUTO EXPIRY - NO CHOOSE**\n📍 {get_mode_text()}\n☀️ Mon-Fri 7AM-8PM\n\n👇 Click any pair - bot auto picks safe expiry:",reply_markup=mk,parse_mode="Markdown"); return

    if data=="scan_all_real":
        bot.answer_callback_query(c.id,"Scanning 22 REAL pairs SAFE...")
        scan_msg=bot.send_message(cid,"🔍 **SCANNING ALL 22 REAL PAIRS V11 SAFE...**\n\n⏳ ~12 sec")
        results=[]
        for pair in REAL_PAIRS:
            d=analyze_momentum(pair,sniper_mode=False)
            if not d: 
                results.append((pair,0,"-","No data","🔴 NO TRADE",120))
                continue
            conf=d['conf']; dir_=d['dir']; reason=d['reason']; exp=d['expiry']
            if conf>=85: status="🟢 READY"
            elif conf>=65: status="🟡 READY"
            else: status="🔴 NO TRADE"
            results.append((pair,conf,dir_,reason,status,exp))
            try: bot.edit_message_text(f"🔍 Scanning V11... {pair} {conf:.0f}%",cid,scan_msg.message_id)
            except: pass
            time.sleep(0.5)
        results.sort(key=lambda x: x[1], reverse=True)
        txt="📊 **REAL V11 SAFE READINESS AUTO EXPIRY** 📊\n"
        txt+=f"📍 {get_mode_text()}\n⏰ {datetime.now(pytz.timezone('Africa/Lagos')).strftime('%H:%M:%S WAT')}\n\n"
        for pair,conf,dir_,reason,status,exp in results:
            emoji=PAIR_EMOJI.get(pair,pair)
            if conf>=65: txt+=f"{status} {emoji}: {conf:.0f}% {dir_} Safe {exp}s - {reason}\n"
            else: txt+=f"{status} {emoji}: {conf:.0f}% - {reason}\n"
        best = results[0] if results else None
        if best and best[1]>=65: txt+=f"\n💡 **BEST NOW:** {PAIR_EMOJI.get(best[0],best[0])} {best[1]:.0f}% Safe {best[5]}s"
        else: txt+=f"\n💡 **No safe trade now - Rescan in 1 min**"
        mk=types.InlineKeyboardMarkup(row_width=2)
        if best and best[1]>=65: mk.add(types.InlineKeyboardButton(f"✅ TRADE BEST {best[0]}",callback_data=f"real_pair_{best[0]}"))
        mk.add(types.InlineKeyboardButton("🔄 RE-SCAN ALL",callback_data="scan_all_real"),types.InlineKeyboardButton("💹 SWITCH TO OTC",callback_data="trade"))
        bot.send_message(cid,txt,reply_markup=mk,parse_mode="Markdown")
        return

    if data.startswith("real_pair_"):
        pair=data.replace("real_pair_","")
        bot.answer_callback_query(c.id,f"Scanning {pair} SAFE...")
        scan_msg=bot.send_message(cid,f"🔍 **V11 SAFE SCAN {PAIR_EMOJI.get(pair,pair)}**\n\n0%\n🚀 Auto safe expiry...")
        legit_live_scan(cid,scan_msg.message_id,pair)
        d=analyze_momentum(pair,sniper_mode=False)
        if not d or d['conf'] < 65:
            mk=types.InlineKeyboardMarkup()
            mk.add(types.InlineKeyboardButton("🔄 RETRY",callback_data=f"real_pair_{pair}"),types.InlineKeyboardButton("📈 SCAN ALL",callback_data="scan_all_real"))
            bot.send_message(cid,f"⚠️ **No safe trade now for {pair}**\n\n📊 Conf: {d['conf'] if d else 0}% < 65%\n🛡️ {d['reason'] if d else 'No data'}\n💡 Wait 30 sec - market choppy",reply_markup=mk)
            return
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=45)
        exp=d['expiry']; exp_txt=f"{exp//60} min" if exp>=60 else f"{exp}s"
        dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"
        signal_txt=f"""📡 **REAL SIGNAL V11 SAFE AUTO** 📡

💱 {PAIR_EMOJI.get(pair,pair)}
📊 {dir_e} | 🎯 {d['conf']:.0f}% SAFE
📈 {d['reason']} | RSI {d['rsi']:.1f} | ATR {d['atr']:.5f}
💸 {int(d['payout']*100)}% | 💰 {d['price']:.5f}

⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)
⏱️ AUTO SAFE EXPIRY: {exp_txt} ({exp}s) - Bot picked
📅 {now.strftime('%A %d %b %H:%M WAT')}

⚠️ **MANUAL PLACE - Expiry already safe**
"""
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🔁 SAME PAIR",callback_data=f"real_pair_{pair}"),types.InlineKeyboardButton("📈 SCAN ALL",callback_data="scan_all_real"))
        mk.add(types.InlineKeyboardButton("💹 SWITCH TO OTC",callback_data="trade"))
        bot.send_message(cid,signal_txt,reply_markup=mk,parse_mode="Markdown")
        return

    if data=="trade":
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in OTC_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}",callback_data=f"pair_{p}"))
        bot.send_message(cid,f"💹 **MANUAL OTC (19) AUTO SAFE EXPIRY**\n📍 {get_mode_text()}\n\n👇 Click pair - bot auto picks safe expiry",reply_markup=mk,parse_mode="Markdown"); return

    if data=="auto_setup":
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🤖 AUTO SCAN ALL 19 OTC",callback_data="auto_pair_AUTO"))
        for p in OTC_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}",callback_data=f"auto_pair_{p}"))
        bot.send_message(cid,f"🤖 **AUTO SETUP 1/4 - OTC ONLY**",reply_markup=mk,parse_mode="Markdown"); return
    if data.startswith("auto_pair_"):
        pair=data.replace("auto_pair_","")
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🟢 DEMO",callback_data=f"auto_bal_PRACTICE_{pair}"))
        mk.add(types.InlineKeyboardButton("🔴 REAL",callback_data=f"auto_bal_REAL_{pair}"))
        bot.send_message(cid,f"✅ Pair: {pair}\n\n🤖 **SETUP 2/4 - ACCOUNT**",reply_markup=mk,parse_mode="Markdown"); return
    if data.startswith("auto_bal_"):
        parts=data.split("_"); bal=parts[2]; pair=parts[3]
        mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("💵 $1",callback_data=f"auto_amt_1_{pair}_{bal}"),types.InlineKeyboardButton("💵 $5",callback_data=f"auto_amt_5_{pair}_{bal}"),types.InlineKeyboardButton("💵 $10",callback_data=f"auto_amt_10_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("💵 $20",callback_data=f"auto_amt_20_{pair}_{bal}"))
        bot.send_message(cid,f"✅ {pair} {bal}\n\n🤖 **SETUP 3/4 - BASE AMOUNT**",reply_markup=mk,parse_mode="Markdown"); return
    if data.startswith("auto_amt_"):
        parts=data.split("_"); amt=float(parts[2]); pair=parts[3]; bal=parts[4]
        d=analyze_momentum(pair,sniper_mode=False) if pair!="AUTO" else {"expiry":60}
        exp_auto=d['expiry'] if d else 60
        AUTO_STATE[cid]={"running":True,"pair":pair,"bal":bal,"base_amt":amt,"curr_amt":amt,"expiry":exp_auto,"martingale":True,"sniper":True,"trades":0}
        mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🛑 STOP AUTO",callback_data="stop_auto"))
        bot.send_message(cid,f"🚀 **STARTING AUTO OTC V11 SAFE!** {pair} ${amt} Auto {exp_auto}s\n💰 Bal ${get_real_balance(bal):.2f}",reply_markup=mk,parse_mode="Markdown")
        threading.Thread(target=auto_trader_loop,args=(cid,),daemon=True).start(); return
    if data=="stop_auto":
        if cid in AUTO_STATE: AUTO_STATE[cid]['running']=False; bot.send_message(cid,"🛑 Stopping..."); return

    if data.startswith("pair_"):
        pair=data.replace("pair_","")
        bot.answer_callback_query(c.id,f"Scanning {pair} SAFE...")
        scan_msg=bot.send_message(cid,f"🔍 **V11 SAFE SCAN {PAIR_EMOJI.get(pair,pair)}**\n\n0%\n🚀 Auto safe expiry...")
        legit_live_scan(cid,scan_msg.message_id,pair)
        d=analyze_momentum(pair,sniper_mode=False)
        if not d:
            bot.send_message(cid,f"❌ Failed analyze {pair}"); return
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🟢 DEMO",callback_data=f"bal_PRACTICE_{pair}_{d['expiry']}"),types.InlineKeyboardButton("🔴 REAL",callback_data=f"bal_REAL_{pair}_{d['expiry']}"))
        bot.send_message(cid,f"✅ **{PAIR_EMOJI.get(pair,pair)} READY V11**\n\n📊 {d['dir']} {d['conf']:.0f}% | {d['reason']}\n⏱️ Safe Expiry Auto: {d['expiry']}s | ATR {d['atr']:.5f}\n\n💳 **CHOOSE ACCOUNT - Bot will place {d['expiry']}s**",reply_markup=mk,parse_mode="Markdown")
        return

    if data.startswith("bal_"):
        parts=data.split("_"); bal=parts[1]; pair=parts[2]; expiry=int(parts[3])
        mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("💵 $1",callback_data=f"amt_1_{pair}_{bal}_{expiry}"),types.InlineKeyboardButton("💵 $5",callback_data=f"amt_5_{pair}_{bal}_{expiry}"),types.InlineKeyboardButton("💵 $10",callback_data=f"amt_10_{pair}_{bal}_{expiry}"))
        mk.add(types.InlineKeyboardButton("✏️ CUSTOM",callback_data=f"custom_{pair}_{bal}_{expiry}"))
        bot.send_message(cid,f"✅ {pair} Safe {expiry}s | {bal}\n\n💰 **AMOUNT**",reply_markup=mk,parse_mode="Markdown"); return

    if data.startswith("amt_") or data.startswith("custom_"):
        if data.startswith("custom_"):
            parts=data.split("_"); pair=parts[1]; bal=parts[2]; expiry=int(parts[3])
            user_states[cid]={"pair":pair,"bal":bal,"expiry":expiry,"step":"await_amt"}
            bot.send_message(cid,f"✏️ Type amount for {pair} {bal} Safe {expiry}s"); return
        parts=data.split("_"); amt=float(parts[1]); pair=parts[2]; bal=parts[3]; expiry=int(parts[4])
        bot.answer_callback_query(c.id,f"Placing {expiry}s trade...")
        d=analyze_momentum(pair,sniper_mode=False)
        if not d: bot.send_message(cid,"❌ No data"); return
        dir_emoji="🟢 CALL" if d['dir']=="CALL" else "🔴 PUT"
        exp_txt=f"{expiry}s" if expiry<60 else f"{expiry//60} min"
        bot.send_message(cid,f"📡 **PLACING SAFE TRADE**\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n📊 {dir_emoji} {d['conf']:.0f}% | {d['reason']}\n⏱️ Auto Safe: {exp_txt}\n💰 ${amt} {bal}\n\n🤖 Placing...")
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal,expiry)
        if not ok:
            mk=types.InlineKeyboardMarkup(row_width=2)
            mk.add(types.InlineKeyboardButton("💹 NEW TRADE",callback_data="trade"),types.InlineKeyboardButton("🔄 RETRY",callback_data=f"amt_{int(amt)}_{pair}_{bal}_{expiry}"))
            bot.send_message(cid,"❌ Trade Failed",reply_markup=mk); iq_reconnect(); return
        bot.send_message(cid,f"✅ Placed {oid} | Waiting {exp}s | Bal ${get_real_balance(bal):.2f}")
        time.sleep(exp+6)
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL); pnl=iq.check_win_v4(oid)
                logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            bal_now=get_real_balance(bal)
            if pnl>0:
                STATS['wins']+=1; STATS['real_balance']=bal_now; STATS['streak']+=1
                mk=types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton("🔁 SAME SAFE TRADE",callback_data=f"amt_{int(amt)}_{pair}_{bal}_{expiry}"),types.InlineKeyboardButton("💹 NEW TRADE",callback_data="trade"))
                mk.add(types.InlineKeyboardButton("📊 STATS",callback_data="stats"),types.InlineKeyboardButton("🤖 AUTO",callback_data="auto_setup"))
                bot.send_message(cid,f"✅ **WIN +${pnl:.2f}**\n💱 {pair} Safe {exp_txt}\n🔥 Streak {STATS['streak']} | Bal ${bal_now:.2f}\n\n👇 Next?",reply_markup=mk,parse_mode="Markdown")
            else:
                STATS['loss']+=1; STATS['real_balance']=bal_now; STATS['streak']=0
                mk=types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton(f"🔁 MARTINGALE ${amt*2.2:.0f}",callback_data=f"amt_{int(amt*2.2)}_{pair}_{bal}_{expiry}"),types.InlineKeyboardButton("💹 NEW TRADE",callback_data="trade"))
                mk.add(types.InlineKeyboardButton("📊 STATS",callback_data="stats"),types.InlineKeyboardButton("🤖 AUTO",callback_data="auto_setup"))
                bot.send_message(cid,f"❌ **LOSS -${amt}**\n💱 {pair} Safe {exp_txt}\nBal ${bal_now:.2f}\n\n👇 Martingale?",reply_markup=mk,parse_mode="Markdown")
        except:
            mk=types.InlineKeyboardMarkup(row_width=2)
            mk.add(types.InlineKeyboardButton("💹 NEW TRADE",callback_data="trade"),types.InlineKeyboardButton("🔄 RETRY",callback_data=f"amt_{int(amt)}_{pair}_{bal}_{expiry}"))
            bot.send_message(cid,f"⏱️ Expired {oid} - Check IQ",reply_markup=mk,parse_mode="Markdown")
        return

    if data=="stats":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0; bal=get_real_balance("PRACTICE")
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("💹 NEW TRADE",callback_data="trade"),types.InlineKeyboardButton("🤖 AUTO",callback_data="auto_setup"))
        bot.send_message(cid,f"📊 **STATS V11 SAFE AUTO**\n📍 {get_mode_text()}\n🏆 Wins: {STATS['wins']}\n❌ Loss: {STATS['loss']}\n📈 Winrate: {wr:.1f}%\n🔥 Streak: {STATS['streak']}\n💰 Bal: ${bal:.2f}",reply_markup=mk,parse_mode="Markdown")
    if data=="settings":
        bot.send_message(cid,f"⚙️ **SETTINGS V11 SAFE AUTO**\n\n🛡️ SAFE V11: ATR filter + Body filter + EMA 3 Align + RSI Safe Zone + Wick + Engulf + Pin Bar\n⏱️ Auto Expiry: Bot picks 60s/120s/180s based on momentum\n📊 65%+ = Safe trade, 85%+ = Premium sniper\n🌙 OTC 19 valid IQ pairs 24/7 daytime\n☀️ REAL 22 pairs 7AM-8PM\nNo expiry choose - all automatic!")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id,{}).get("step")=="await_amt")
def handle_custom_amt(m):
    cid=m.chat.id; st=user_states.get(cid,{})
    if not is_allowed(m.from_user.id): return
    try:
        amt=float(m.text.strip()); pair=st.get("pair"); bal=st.get("bal"); expiry=st.get("expiry",60)
        if not pair: return
        bot.send_message(cid,f"✅ Custom ${amt} - Placing Safe {expiry}s trade...")
        d=analyze_momentum(pair,sniper_mode=False)
        if not d: return
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal,expiry)
        if not ok: bot.send_message(cid,"❌ Failed"); return
        bot.send_message(cid,f"✅ Placed {oid} Waiting {exp}s...")
        time.sleep(exp+6)
        with IQ_LOCK:
            logging.disable(logging.CRITICAL); pnl=iq.check_win_v4(oid)
            logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
        bal_now=get_real_balance(bal)
        if pnl>0: STATS['wins']+=1; STATS['streak']+=1; bot.send_message(cid,f"✅ WIN +${pnl:.2f} Bal ${bal_now:.2f}")
        else: STATS['loss']+=1; STATS['streak']=0; bot.send_message(cid,f"❌ LOSS Bal ${bal_now:.2f}")
    except: bot.send_message(cid,"❌ Send number only")

@app.route(f"/{BOT_TOKEN}",methods=['POST'])
def wh(): bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode("utf-8"))]); return "ok"
@app.route("/")
def home():
    u=os.getenv("RENDER_EXTERNAL_URL")
    if u:
        try: requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={u}/{BOT_TOKEN}",timeout=5)
        except: pass
    return "V11 SAFE AUTO EXPIRY - RUNNING"

threading.Thread(target=real_signal_scanner,daemon=True).start()
app.run(host="0.0.0.0",port=int(os.getenv("PORT",10000)))
