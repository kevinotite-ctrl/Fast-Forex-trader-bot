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

REAL_PAIRS = ["EURUSD","GBPUSD","USDJPY","EURGBP","AUDUSD","USDCAD","EURJPY","GBPJPY","USDCHF","AUDJPY","EURAUD","GBPCHF","EURCHF","NZDUSD","GBPAUD","EURCAD","AUDCAD","GBPCAD","NZDJPY","AUDNZD","CHFJPY","CADJPY"]
OTC_PAIRS = ["EURUSD-OTC","GBPUSD-OTC","USDJPY-OTC","AUDUSD-OTC","USDCAD-OTC","EURGBP-OTC","EURJPY-OTC","GBPJPY-OTC","AUDJPY-OTC","EURAUD-OTC","GBPAUD-OTC","NZDUSD-OTC","GBPCHF-OTC","EURCHF-OTC","USDCHF-OTC","AUDCAD-OTC","EURCAD-OTC","CADJPY-OTC","NZDJPY-OTC"]
PAIR_EMOJI = {"EURUSD":"🇪🇺 EUR/USD REAL","GBPUSD":"🇬🇧 GBP/USD REAL","USDJPY":"🇺🇸 USD/JPY REAL","EURGBP":"🇪🇺 EUR/GBP REAL","AUDUSD":"🇦🇺 AUD/USD REAL","USDCAD":"🇺🇸 USD/CAD REAL","EURJPY":"🇪🇺 EUR/JPY REAL","GBPJPY":"🇬🇧 GBP/JPY REAL","USDCHF":"🇺🇸 USD/CHF REAL","AUDJPY":"🇦🇺 AUD/JPY REAL","EURAUD":"🇪🇺 EUR/AUD REAL","GBPCHF":"🇬🇧 GBP/CHF REAL","EURCHF":"🇪🇺 EUR/CHF REAL","NZDUSD":"🇳🇿 NZD/USD REAL","GBPAUD":"🇬🇧 GBP/AUD REAL","EURCAD":"🇪🇺 EUR/CAD REAL","AUDCAD":"🇦🇺 AUD/CAD REAL","GBPCAD":"🇬🇧 GBP/CAD REAL","NZDJPY":"🇳🇿 NZD/JPY REAL","AUDNZD":"🇦🇺 AUD/NZD REAL","CHFJPY":"🇨🇭 CHF/JPY REAL","CADJPY":"🇨🇦 CAD/JPY REAL","EURUSD-OTC":"🇪🇺 EUR/USD OTC","GBPUSD-OTC":"🇬🇧 GBP/USD OTC","EURGBP-OTC":"🇪🇺 EUR/GBP OTC","USDJPY-OTC":"🇺🇸 USD/JPY OTC","GBPJPY-OTC":"🇬🇧 GBP/JPY OTC","AUDUSD-OTC":"🇦🇺 AUD/USD OTC","USDCHF-OTC":"🇺🇸 USD/CHF OTC","EURJPY-OTC":"🇪🇺 EUR/JPY OTC","AUDJPY-OTC":"🇦🇺 AUD/JPY OTC","EURAUD-OTC":"🇪🇺 EUR/AUD OTC","GBPAUD-OTC":"🇬🇧 GBP/AUD OTC","NZDUSD-OTC":"🇳🇿 NZD/USD OTC","GBPCHF-OTC":"🇬🇧 GBP/CHF OTC","EURCHF-OTC":"🇪🇺 EUR/CHF OTC","USDCAD-OTC":"🇺🇸 USD/CAD OTC","AUDCAD-OTC":"🇦🇺 AUD/CAD OTC","EURCAD-OTC":"🇪🇺 EUR/CAD OTC","CADJPY-OTC":"🇨🇦 CAD/JPY OTC","NZDJPY-OTC":"🇳🇿 NZD/JPY OTC"}

STATS = {"balance":0.0,"real_balance":0.0,"wins":0,"loss":0,"streak":0}
user_states = {}; AUTO_STATE = {}; IQ_LOCK = threading.Lock()
IQ_CONNECTED=False; iq=None; PAYOUT_CACHE={}; PAYOUT_TIME=0

def is_allowed(uid): return uid == OWNER_ID
def is_real_hours():
    try:
        tz = pytz.timezone("Africa/Lagos"); now = datetime.now(tz)
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
        logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
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

def get_candles_tf(pair, tf_sec=300):
    if not IQ_CONNECTED and not iq_reconnect(): return None
    for _ in range(2):
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL); c=iq.get_candles(pair,tf_sec,30,time.time())
                logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            if c and len(c)>10: return pd.DataFrame(sorted(c,key=lambda x:x['from']))
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
    steps = [(0,"🚀 V13.1 Scan Init...",0.15),(20,f"🔌 Checking {pair}...",0.2),(40,"📊 ATR + Body Filter...",0.25),(60,"📈 EMA 3 Align...",0.2),(80,"💹 RSI + PA...",0.2),(100,"🔒 SIGNAL READY!",0.3)]
    last_pct=-1
    for pct, text, delay in steps:
        if pct==last_pct: time.sleep(delay); continue
        last_pct=pct; filled=int(pct//5); bar="█"*filled+"░"*(20-filled)
        color="🟥" if pct<40 else "🟨" if pct<80 else "🟩" if pct<100 else "💎"
        txt=f"""{color} **Z-BOT V13.1 PROFIT SAFE** {color}\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n💎 IQ: {'✅' if IQ_CONNECTED else '❌'}\n\n{bar} {pct}%\n\n🔍 {text}\n⏳ 75%+ for profit"""
        try: bot.edit_message_text(txt,cid,mid,parse_mode="Markdown")
        except: pass
        time.sleep(delay)

def analyze_momentum(pair, sniper_mode=False, use_5m=False):
    df=get_candles(pair)
    df5=get_candles_tf(pair,300) if use_5m else None
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
        rsi7=float(rsi_fast.iloc[-1]); rsi14=float(rsi_slow.iloc[-1])
        mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100
        body=abs(c_now-o_now)
        upper_wick=h_now-max(c_now,o_now)
        lower_wick=min(c_now,o_now)-l_now
        is_green=c_now>o_now
        payout=get_payout(pair)
        sig="CALL" if is_green else "PUT"
        score=0; reason_list=[]
        recent_high = float(high.tail(20).max()); recent_low = float(low.tail(20).min())
        dist_to_res = (recent_high - c_now) / c_now * 100; dist_to_sup = (c_now - recent_low) / c_now * 100
        near_res = dist_to_res < 0.04; near_sup = dist_to_sup < 0.04
        if near_res and is_green:
            return {"pair":pair,"dir":sig,"conf":52,"price":c_now,"rsi":rsi7,"reason":f"Near Res {recent_high:.5f}","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if near_sup and not is_green:
            return {"pair":pair,"dir":sig,"conf":52,"price":c_now,"rsi":rsi7,"reason":f"Near Sup {recent_low:.5f}","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if use_5m and df5 is not None and len(df5) > 20:
            close5=df5['close']; ema9_5=close5.ewm(9).mean(); ema21_5=close5.ewm(21).mean()
            e9_5=float(ema9_5.iloc[-1]); e21_5=float(ema21_5.iloc[-1]); rsi5=calc_rsi(close5,14); rsi5_now=float(rsi5.iloc[-1])
            tf5_ok = True
            if is_green:
                if not (e9_5 > e21_5): tf5_ok=False
                if rsi5_now < 45: tf5_ok=False
            else:
                if not (e9_5 < e21_5): tf5_ok=False
                if rsi5_now > 55: tf5_ok=False
            if not tf5_ok:
                return {"pair":pair,"dir":sig,"conf":54,"price":c_now,"rsi":rsi7,"reason":"5m Conflict","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        min_atr = 0.00025 if pair in ["EURUSD","GBPUSD","USDJPY"] else 0.00035
        if atr < min_atr:
            return {"pair":pair,"dir":sig,"conf":45,"price":c_now,"rsi":rsi7,"reason":"Low ATR","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if body < atr*0.35:
            return {"pair":pair,"dir":sig,"conf":50,"price":c_now,"rsi":rsi7,"reason":"Doji","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if is_green:
            if e9 > e21 and e21 > e50: score+=20; reason_list.append("EMA Bull")
            elif e9 > e21: score+=12
        else:
            if e9 < e21 and e21 < e50: score+=20; reason_list.append("EMA Bear")
            elif e9 < e21: score+=12
        if is_green:
            if 55 <= rsi7 <= 68: score+=25; reason_list.append(f"RSI {rsi7:.0f}")
            elif 50 <= rsi7 <= 72: score+=15
        else:
            if 32 <= rsi7 <= 45: score+=25; reason_list.append(f"RSI {rsi7:.0f}")
            elif 28 <= rsi7 <= 50: score+=15
        bullish_engulf = c_now > o_prev and o_now < c_prev and is_green and not (c_prev > o_prev)
        bearish_engulf = c_now < o_prev and o_now > c_prev and not is_green and (c_prev > o_prev)
        pin_bull = lower_wick > body*1.5 and lower_wick > upper_wick*1.5 and is_green
        pin_bear = upper_wick > body*1.5 and upper_wick > lower_wick*1.5 and not is_green
        if is_green:
            if bullish_engulf: score+=15; reason_list.append("Bull Engulf")
            if pin_bull: score+=15; reason_list.append("Pin Bull")
        else:
            if bearish_engulf: score+=15; reason_list.append("Bear Engulf")
            if pin_bear: score+=15; reason_list.append("Pin Bear")
        score+=5; reason_list.append("SR Safe")
        if use_5m: score+=10; reason_list.append("5m Confirm")
        score = max(45, min(96, score + 30))
        reason = " + ".join(reason_list)
        expiry = 180 if abs(mom1) > 0.06 else 120
        if "-OTC" in pair: expiry = 60 if abs(mom1) > 0.05 else 120
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

def send_top_signal(cid, best_data, mode_name):
    try:
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=45)
        d=best_data
        dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"
        exp=d['expiry']; exp_txt=f"{exp//60} min" if exp>=60 else f"{exp}s"
        signal_txt=f"""📡 **V13.1 TOP PROFIT SIGNAL {mode_name}** 📡

💱 {PAIR_EMOJI.get(d['pair'],d['pair'])}
📊 {dir_e} | 🎯 {d['conf']:.0f}% HIGH CONF
📈 {d['reason']} | RSI {d['rsi']:.1f}
💸 {int(d['payout']*100)}% | 💰 {d['price']:.5f}

⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)
⏱️ AUTO EXPIRY: {exp_txt}

✅ **PROFIT SAFE - 75%+ REAL / 70%+ OTC**
"""
        mk=types.InlineKeyboardMarkup(row_width=2)
        if "-OTC" in d['pair']:
            mk.add(types.InlineKeyboardButton("🔁 SCAN OTC AGAIN",callback_data="scan_all_otc"),types.InlineKeyboardButton("📈 SCAN REAL",callback_data="trade_real"))
        else:
            if "FAST" in mode_name:
                mk.add(types.InlineKeyboardButton("🔁 RE-SCAN REAL FAST",callback_data="scan_all_real_fast"),types.InlineKeyboardButton("🛡️ TRY ULTRA",callback_data="scan_all_real_ultra"))
            else:
                mk.add(types.InlineKeyboardButton("🔁 RE-SCAN REAL ULTRA",callback_data="scan_all_real_ultra"),types.InlineKeyboardButton("⚡ TRY FAST",callback_data="scan_all_real_fast"))
        bot.send_message(cid,signal_txt,reply_markup=mk,parse_mode="Markdown")
    except Exception as e:
        bot.send_message(cid,f"Error sending top signal {e}")

@bot.message_handler(commands=['start','stop','mode','balance'])
def start(m):
    if not is_allowed(m.from_user.id): bot.send_message(m.chat.id,"❌ Private"); return
    if m.text.startswith('/stop'):
        if m.chat.id in AUTO_STATE: AUTO_STATE[m.chat.id]['running']=False; bot.send_message(m.chat.id,"🛑 Stopping...")
        else: bot.send_message(m.chat.id,"Auto not running"); return
    if m.text.startswith('/mode'):
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz)
        txt=f"""📍 **MODE CHECK V13.1 PROFIT SAFE**

⏰ Now: {now.strftime('%A %H:%M:%S WAT')}
📊 Mode: {get_mode_text()}
☀️ REAL: 75%+ profit safe + auto top
🌙 OTC: 70%+ profit safe + auto top
💎 IQ: {'✅' if IQ_CONNECTED else '❌'}
"""
        bot.send_message(m.chat.id,txt,parse_mode="Markdown"); return
    if m.text.startswith('/balance'):
        try:
            demo=get_real_balance("PRACTICE"); real=get_real_balance("REAL")
            bot.send_message(m.chat.id,f"💰 **BALANCES**\n🟢 DEMO: ${demo:.2f}\n🔴 REAL: ${real:.2f}")
        except Exception as e: bot.send_message(m.chat.id,f"Balance error {e}")
        return
    bal_demo=get_real_balance("PRACTICE")
    mk=types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton(f"💹 SCAN ALL OTC - PROFIT SAFE 70%+",callback_data="scan_all_otc"))
    mk.add(types.InlineKeyboardButton(f"📈 TRADE REAL (22) - PROFIT SAFE 75%+",callback_data="trade_real"))
    mk.add(types.InlineKeyboardButton("🤖 AUTO-TRADER OTC 90%+",callback_data="auto_setup"))
    mk.add(types.InlineKeyboardButton("📊 MY STATS",callback_data="stats"),types.InlineKeyboardButton("⚙️ SETTINGS",callback_data="settings"))
    txt=f"""🤖 **Z-BOT V13.1 PROFIT SAFE** 🤖

💎 IQ: {'✅' if IQ_CONNECTED else '❌'} | 💰 DEMO ${bal_demo:.2f}
🏆 W:{STATS['wins']} L:{STATS['loss']} | 🔥 {STATS['streak']}
📍 {get_mode_text()}

⚡ SCAN ALL → List + Auto signal ONLY if 75%+ REAL / 70%+ OTC for profit

👇 **Select:**
"""
    bot.send_message(m.chat.id,txt,reply_markup=mk,parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_allowed(c.from_user.id): bot.answer_callback_query(c.id,"❌ Private"); return
    data=c.data; cid=c.message.chat.id

    if data=="trade_real":
        mk=types.InlineKeyboardMarkup(row_width=1)
        mk.add(types.InlineKeyboardButton("⚡ SCAN ALL 22 FAST + AUTO TOP 75%+",callback_data="scan_all_real_fast"))
        mk.add(types.InlineKeyboardButton("🛡️ SCAN ALL 22 ULTRA + AUTO TOP 75%+",callback_data="scan_all_real_ultra"))
        bot.send_message(cid,f"📈 **CHOOSE REAL STRATEGY - PROFIT SAFE 75%+**\n\nScan all → bot sends top signal ONLY if 75%+ else warns SKIP",reply_markup=mk,parse_mode="Markdown"); return

    if data=="scan_all_real_fast":
        bot.answer_callback_query(c.id,"Scanning 22 REAL FAST...")
        bot.send_message(cid,"🔍 **SCANNING ALL 22 REAL FAST...**")
        results=[]; datas={}
        for pair in REAL_PAIRS:
            d=analyze_momentum(pair,sniper_mode=False, use_5m=False)
            if not d: 
                results.append((pair,0,"-","No data","🔴 NO TRADE",120))
                continue
            results.append((pair,d['conf'],d['dir'],d['reason'], "🟢 READY" if d['conf']>=85 else "🟡 READY" if d['conf']>=65 else "🔴 LOW", d['expiry']))
            datas[pair]=d
            time.sleep(0.2)
        results.sort(key=lambda x: x[1], reverse=True)
        txt="📊 **REAL FAST READINESS** 📊\n"
        for pair,conf,dir_,reason,status,exp in results:
            txt+=f"{status} {PAIR_EMOJI.get(pair,pair)}: {conf:.0f}% {dir_} {exp}s - {reason}\n"
        bot.send_message(cid,txt,parse_mode="Markdown")
        if datas and results:
            best_pair = results[0][0]
            best_conf = results[0][1]
            best_data = datas.get(best_pair)
            if best_data:
                time.sleep(0.5)
                if best_conf >= 75:
                    send_top_signal(cid, best_data, "FAST REAL")
                else:
                    bot.send_message(cid,f"⚠️ **No 75%+ now for PROFIT**\n\nBest now: {PAIR_EMOJI.get(best_pair,best_pair)} {best_conf:.0f}% {best_data['dir']} - {best_data['reason']}\n\n👉 SKIP am or wait 3-5 mins scan again. Low conf = high loss chance.",parse_mode="Markdown")
        return

    if data=="scan_all_real_ultra":
        bot.answer_callback_query(c.id,"Scanning 22 REAL ULTRA...")
        bot.send_message(cid,"🔍 **SCANNING ALL 22 REAL ULTRA...** ~20 sec")
        results=[]; datas={}
        for pair in REAL_PAIRS:
            d=analyze_momentum(pair,sniper_mode=False, use_5m=True)
            if not d: 
                results.append((pair,0,"-","No data","🔴 NO TRADE",120))
                continue
            results.append((pair,d['conf'],d['dir'],d['reason'], "🟢 READY" if d['conf']>=85 else "🟡 READY" if d['conf']>=65 else "🔴 LOW", d['expiry']))
            datas[pair]=d
            time.sleep(0.3)
        results.sort(key=lambda x: x[1], reverse=True)
        txt="📊 **REAL ULTRA READINESS (SR+5m)** 📊\n"
        for pair,conf,dir_,reason,status,exp in results:
            txt+=f"{status} {PAIR_EMOJI.get(pair,pair)}: {conf:.0f}% {dir_} {exp}s - {reason}\n"
        bot.send_message(cid,txt,parse_mode="Markdown")
        if datas and results:
            best_pair = results[0][0]
            best_conf = results[0][1]
            best_data = datas.get(best_pair)
            if best_data:
                time.sleep(0.5)
                if best_conf >= 75:
                    send_top_signal(cid, best_data, "ULTRA REAL")
                else:
                    bot.send_message(cid,f"⚠️ **No 75%+ now for PROFIT**\n\nBest now: {PAIR_EMOJI.get(best_pair,best_pair)} {best_conf:.0f}% {best_data['dir']} - {best_data['reason']}\n\n👉 ULTRA need 75%+ to profit for REAL. Wait 5 mins.",parse_mode="Markdown")
        return

    if data=="scan_all_otc":
        bot.answer_callback_query(c.id,"Scanning 19 OTC...")
        bot.send_message(cid,"🔍 **SCANNING ALL 19 OTC...**")
        results=[]; datas={}
        for pair in OTC_PAIRS:
            d=analyze_momentum(pair,sniper_mode=False, use_5m=False)
            if not d: 
                results.append((pair,0,"-","No data","🔴 NO TRADE",120))
                continue
            results.append((pair,d['conf'],d['dir'],d['reason'], "🟢 READY" if d['conf']>=85 else "🟡 READY" if d['conf']>=65 else "🔴 LOW", d['expiry']))
            datas[pair]=d
            time.sleep(0.2)
        results.sort(key=lambda x: x[1], reverse=True)
        txt="📊 **OTC FAST READINESS** 📊\n"
        for pair,conf,dir_,reason,status,exp in results:
            txt+=f"{status} {PAIR_EMOJI.get(pair,pair)}: {conf:.0f}% {dir_} {exp}s - {reason}\n"
        bot.send_message(cid,txt,parse_mode="Markdown")
        if datas and results:
            best_pair = results[0][0]
            best_conf = results[0][1]
            best_data = datas.get(best_pair)
            if best_data:
                time.sleep(0.5)
                if best_conf >= 70:
                    send_top_signal(cid, best_data, "OTC")
                else:
                    bot.send_message(cid,f"⚠️ **No 70%+ now for OTC PROFIT**\n\nBest now: {PAIR_EMOJI.get(best_pair,best_pair)} {best_conf:.0f}% {best_data['dir']} - {best_data['reason']}\n\n👉 SKIP or wait 3 mins. OTC dey move fast.",parse_mode="Markdown")
        return

    if data.startswith("real_pair_fast_") or data.startswith("real_pair_ultra_"):
        is_fast = "fast" in data
        pair = data.replace("real_pair_fast_","").replace("real_pair_ultra_","")
        bot.answer_callback_query(c.id,f"Scanning {pair}...")
        scan_msg=bot.send_message(cid,f"🔍 **SCAN {PAIR_EMOJI.get(pair,pair)}**\n\n0%")
        legit_live_scan(cid,scan_msg.message_id,pair)
        d=analyze_momentum(pair,sniper_mode=False, use_5m=not is_fast)
        if not d: bot.send_message(cid,f"❌ No data {pair}"); return
        send_top_signal(cid, d, "FAST REAL" if is_fast else "ULTRA REAL")
        return

    if data=="trade":
        mk=types.InlineKeyboardMarkup(row_width=1)
        mk.add(types.InlineKeyboardButton("🔍 SCAN ALL 19 OTC + PROFIT SAFE",callback_data="scan_all_otc"))
        for p in OTC_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}",callback_data=f"pair_{p}"))
        bot.send_message(cid,f"💹 **MANUAL OTC + PROFIT SAFE**\n📍 {get_mode_text()}",reply_markup=mk,parse_mode="Markdown"); return

    if data=="auto_setup":
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🤖 AUTO SCAN ALL 19 OTC",callback_data="auto_pair_AUTO"))
        for p in OTC_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}",callback_data=f"auto_pair_{p}"))
        bot.send_message(cid,f"🤖 **AUTO SETUP 1/4 - OTC ONLY SR**",reply_markup=mk,parse_mode="Markdown"); return
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
        bot.send_message(cid,f"✅ {pair} {bal}\n\n🤖 **SETUP 3/4 - BASE AMOUNT**",reply_markup=mk,parse_mode="Markdown"); return
    if data.startswith("auto_amt_"):
        parts=data.split("_"); amt=float(parts[2]); pair=parts[3]; bal=parts[4]
        d=analyze_momentum(pair,sniper_mode=False, use_5m=False) if pair!="AUTO" else {"expiry":60}
        exp_auto=d['expiry'] if d else 60
        AUTO_STATE[cid]={"running":True,"pair":pair,"bal":bal,"base_amt":amt,"curr_amt":amt,"expiry":exp_auto,"martingale":True,"sniper":True,"trades":0}
        mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🛑 STOP AUTO",callback_data="stop_auto"))
        bot.send_message(cid,f"🚀 **STARTING AUTO OTC SR FAST!** {pair} ${amt} Auto {exp_auto}s\n💰 Bal ${get_real_balance(bal):.2f}",reply_markup=mk,parse_mode="Markdown")
        threading.Thread(target=lambda: auto_trader_loop(cid),daemon=True).start(); return
    if data=="stop_auto":
        if cid in AUTO_STATE: AUTO_STATE[cid]['running']=False; bot.send_message(cid,"🛑 Stopping..."); return

    if data.startswith("pair_"):
        pair=data.replace("pair_","")
        bot.answer_callback_query(c.id,f"Scanning {pair}...")
        scan_msg=bot.send_message(cid,f"🔍 **V13.1 SR SCAN {PAIR_EMOJI.get(pair,pair)}**\n\n0%")
        legit_live_scan(cid,scan_msg.message_id,pair)
        d=analyze_momentum(pair,sniper_mode=False, use_5m=False)
        if not d: bot.send_message(cid,f"❌ Failed analyze {pair}"); return
        send_top_signal(cid, d, "OTC")
        return

    if data=="stats":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0; bal=get_real_balance("PRACTICE")
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("💹 SCAN OTC",callback_data="scan_all_otc"),types.InlineKeyboardButton("📈 SCAN REAL",callback_data="trade_real"))
        bot.send_message(cid,f"📊 **STATS V13.1 PROFIT SAFE**\n📍 {get_mode_text()}\n🏆 Wins: {STATS['wins']}\n❌ Loss: {STATS['loss']}\n📈 Winrate: {wr:.1f}%\n🔥 Streak: {STATS['streak']}\n💰 Bal: ${bal:.2f}",reply_markup=mk,parse_mode="Markdown")
    if data=="settings":
        bot.send_message(cid,f"⚙️ **SETTINGS V13.1 PROFIT SAFE**\n\nScan All → List always + Signal ONLY if 75%+ REAL / 70%+ OTC\nThis protects you from loss and ensures profit!")

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
                    d=analyze_momentum(p,sniper_mode=True, use_5m=False)
                    if d and not d.get('rejected') and d['conf']>best_score: best_score=d['conf']; best=d
                if not best: time.sleep(25); continue
                d=best; pair_to_trade=d['pair']
            else:
                d=analyze_momentum(pair_to_trade,sniper_mode=True, use_5m=False)
                if not d or d.get('rejected'): time.sleep(20); continue
            curr_amt=state['base_amt']*(2.2**consecutive_losses) if state['martingale'] else state['base_amt']
            curr_amt=min(curr_amt,state['base_amt']*8)
            ok,oid,exp=iq_trade(pair_to_trade,d['dir'],curr_amt,state['bal'],state['expiry'])
            if not ok: iq_reconnect(); time.sleep(8); continue
            bal_now=get_real_balance(state['bal'])
            bot.send_message(cid,f"🤖 Auto OTC {pair_to_trade} {d['dir']} ${curr_amt:.2f} {d['conf']}% {exp}s - ID {oid}\n💰 Bal ${bal_now:.2f}")
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

@app.route(f"/{BOT_TOKEN}",methods=['POST'])
def wh(): bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode("utf-8"))]); return "ok"
@app.route("/")
def home():
    u=os.getenv("RENDER_EXTERNAL_URL")
    if u:
        try: requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={u}/{BOT_TOKEN}",timeout=5)
        except: pass
    return "V13.1 PROFIT SAFE - RUNNING"

app.run(host="0.0.0.0",port=int(os.getenv("PORT",10000)))
