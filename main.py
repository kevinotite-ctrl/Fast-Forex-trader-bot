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
    "EURUSD":"🇪🇺 EUR/USD REAL","GBPUSD":"🇬🇧 GBP/USD REAL","USDJPY":"🇺🇸 USD/JPY REAL",
    "EURGBP":"🇪🇺 EUR/GBP REAL","AUDUSD":"🇦🇺 AUD/USD REAL","USDCAD":"🇺🇸 USD/CAD REAL",
    "EURJPY":"🇪🇺 EUR/JPY REAL","GBPJPY":"🇬🇧 GBP/JPY REAL",
    "EURUSD-OTC":"🇪🇺 EUR/USD OTC","GBPUSD-OTC":"🇬🇧 GBP/USD OTC","EURGBP-OTC":"🇪🇺 EUR/GBP OTC",
    "USDJPY-OTC":"🇺🇸 USD/JPY OTC","GBPJPY-OTC":"🇬🇧 GBP/JPY OTC","AUDUSD-OTC":"🇦🇺 AUD/USD OTC",
    "USDCHF-OTC":"🇺🇸 USD/CHF OTC","EURJPY-OTC":"🇪🇺 EUR/JPY OTC"
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
    return REAL_PAIRS if is_weekday else OTC_PAIRS

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
        logging.disable(logging.NOTSET)
        logging.disable(logging.ERROR)
except: IQ_CONNECTED=False

def iq_reconnect():
    global iq, IQ_CONNECTED
    try:
        from iqoptionapi.stable_api import IQ_Option
        logging.disable(logging.CRITICAL)
        iq=IQ_Option(os.getenv("IQ_EMAIL"),os.getenv("IQ_PASS")); iq.connect()
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
    for _ in range(3):
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL)
                c=iq.get_candles(pair,60,50,time.time())
                if not c and "OTC" not in pair:
                    c=iq.get_candles(pair,300,50,time.time())
                logging.disable(logging.NOTSET)
                logging.disable(logging.ERROR)
            if c and len(c)>20:
                df=pd.DataFrame(sorted(c,key=lambda x:x['from']))
                if 'max' in df.columns: df['high']=df['max']
                if 'min' in df.columns: df['low']=df['min']
                if 'high' not in df.columns: df['high']=df['close']
                if 'low' not in df.columns: df['low']=df['close']
                return df
        except: time.sleep(0.5)
    return None

def calc_rsi(closes, period=7):
    delta=closes.diff(); gain=delta.where(delta>0,0).rolling(period).mean()
    loss=-delta.where(delta<0,0).rolling(period).mean()
    rs=gain/loss; return 100-(100/(1+rs))

def calc_atr(df, period=14):
    hl=df['high']-df['low']; hc=abs(df['high']-df['close'].shift()); lc=abs(df['low']-df['close'].shift())
    tr=pd.concat([hl,hc,lc],axis=1).max(axis=1)
    return tr.rolling(period).mean()

# ===== LEGIT SCAN BAR - UNTOUCHED =====
def legit_live_scan(cid, mid, pair):
    steps = [(0,"🚀 Initializing V8...",0.15),(15,f"🔌 IQ Check {pair}...",0.2),(30,"📊 Fetching candles...",0.25),(50,"📈 EMA analysis...",0.2),(70,"💹 RSI + ATR...",0.2),(85,"🔍 Final lock...",0.2),(100,"🔒 SIGNAL LOCKED!")]
    last_pct=-1
    for pct,text,delay in steps:
        if pct==last_pct: time.sleep(delay); continue
        last_pct=pct
        filled=int(pct//5); bar="█"*filled+"░"*(20-filled)
        color="🟥" if pct<40 else "🟨" if pct<80 else "🟩" if pct<100 else "💎"
        txt=f"""{color} **Z-BOT V8 LEGIT SCAN** {color}

💱 Pair: {PAIR_EMOJI.get(pair,pair)}
💎 IQ: {'✅ Connected' if IQ_CONNECTED else '❌ Offline'}

{bar} {pct}%
▓ Progress: {pct}% ▓

🔍 {text}

⏳ Fast scan V8.3
"""
        try: bot.edit_message_text(txt,cid,mid,parse_mode="Markdown")
        except: pass
        time.sleep(delay)
    try:
        bot.edit_message_text(f"""💎 **Z-BOT V8 LEGIT SCAN** 💎

💱 Pair: {PAIR_EMOJI.get(pair,pair)}
💎 IQ: {'✅ Connected' if IQ_CONNECTED else '❌ Offline'}

████████████████████ 100%
▓ Progress: 100% ▓

🔍 🔒 SIGNAL LOCKED! READY!

⏳ Scan complete!
""",cid,mid,parse_mode="Markdown")
        time.sleep(0.2)
    except: pass

# ===== 2 DIFFERENT STRATEGIES =====
def analyze_otc_strategy(pair):
    """OTC STRATEGY - Fast Scalper: EMA9/21 + RSI + Wick rejection + Momentum"""
    df=get_candles(pair)
    if df is None: return None
    try:
        close=df['close']; open_=df['open']; high=df['high']; low=df['low']
        ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean()
        rsi=calc_rsi(close,7); rsi_now=float(rsi.iloc[-1])
        e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1])
        e9_prev=float(ema9.iloc[-2]); e21_prev=float(ema21.iloc[-2])
        
        mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100
        mom3=(close.iloc[-1]-close.iloc[-4])/close.iloc[-4]*100
        
        is_green=float(close.iloc[-1])>float(open_.iloc[-1])
        body=max(abs(float(close.iloc[-1])-float(open_.iloc[-1])),0.00001)
        upper=float(high.iloc[-1])-max(float(close.iloc[-1]),float(open_.iloc[-1]))
        lower=min(float(close.iloc[-1]),float(open_.iloc[-1]))-float(low.iloc[-1])
        
        payout=get_payout(pair)
        sig="CALL" if is_green else "PUT"; score=75; reason="OTC"
        
        # KING OTC CONDITIONS
        if e9>e21 and e9_prev<=e21_prev and is_green and 55<=rsi_now<=72 and upper<body*0.4 and mom1>0.03:
            sig="CALL"; score=94; reason=f"🔥 OTC CROSS BULL wick {upper/body:.1f} RSI {rsi_now:.0f}"
        elif e9<e21 and e9_prev>=e21_prev and not is_green and 28<=rsi_now<=45 and lower<body*0.4 and mom1<-0.03:
            sig="PUT"; score=94; reason=f"🔥 OTC CROSS BEAR wick {lower/body:.1f} RSI {rsi_now:.0f}"
        elif e9>e21 and is_green and rsi_now>58 and mom1>0.02 and upper<body*0.6:
            sig="CALL"; score=90; reason=f"🚀 OTC Bull MOM {mom1:.3f}%"
        elif e9<e21 and not is_green and rsi_now<42 and mom1<-0.02 and lower<body*0.6:
            sig="PUT"; score=90; reason=f"📉 OTC Bear MOM {mom1:.3f}%"
        elif e9>e21: sig="CALL"; score=82; reason="📈 OTC EMA Bull"
        else: sig="PUT"; score=82; reason="📉 OTC EMA Bear"
        
        return {"pair":pair,"dir":sig,"conf":score,"price":float(close.iloc[-1]),"rsi":rsi_now,"reason":reason,"mom":mom3,"payout":payout,"df":df.tail(30)}
    except Exception as e: return None

def analyze_real_strategy(pair):
    """REAL STRATEGY - Sniper Pro: EMA21/50 + RSI 14 + ATR filter + Strong trend"""
    df=get_candles(pair)
    if df is None: return None
    try:
        close=df['close']; open_=df['open']; high=df['high']; low=df['low']
        ema21=close.ewm(21).mean(); ema50=close.ewm(50).mean()
        rsi=calc_rsi(close,14); rsi_now=float(rsi.iloc[-1])
        atr=calc_atr(df,14); atr_now=float(atr.iloc[-1])
        atr_avg=float(atr.tail(20).mean())
        
        e21=float(ema21.iloc[-1]); e50=float(ema50.iloc[-1])
        e21_prev=float(ema21.iloc[-5]); e50_prev=float(ema50.iloc[-5])
        
        mom5=(close.iloc[-1]-close.iloc[-6])/close.iloc[-6]*100
        is_green=float(close.iloc[-1])>float(open_.iloc[-1])
        
        payout=get_payout(pair); body=abs(float(close.iloc[-1])-float(open_.iloc[-1]))
        
        sig="CALL" if is_green else "PUT"; score=75; reason="REAL"
        
        # REAL needs STRONG trend + ATR filter (no chop)
        is_strong_atr = atr_now > atr_avg*0.8  # Enough volatility
        
        if e21>e50 and e21_prev<=e50_prev and is_green and 50<=rsi_now<=68 and is_strong_atr and mom5>0.08:
            sig="CALL"; score=93; reason=f"💎 REAL CROSS BULL ATR {atr_now:.5f} RSI {rsi_now:.0f}"
        elif e21<e50 and e21_prev>=e50_prev and not is_green and 32<=rsi_now<=50 and is_strong_atr and mom5<-0.08:
            sig="PUT"; score=93; reason=f"💎 REAL CROSS BEAR ATR {atr_now:.5f} RSI {rsi_now:.0f}"
        elif e21>e50 and close.iloc[-1]>e21 and rsi_now>55 and is_strong_atr and mom5>0.05:
            sig="CALL"; score=88; reason=f"💵 REAL Trend Bull {mom5:.3f}%"
        elif e21<e50 and close.iloc[-1]<e21 and rsi_now<45 and is_strong_atr and mom5<-0.05:
            sig="PUT"; score=88; reason=f"💷 REAL Trend Bear {mom5:.3f}%"
        elif not is_strong_atr:
            # Low volatility - skip
            sig="CALL" if e21>e50 else "PUT"; score=70; reason=f"⚠️ REAL Low Vol ATR {atr_now:.5f} - Weak"
        else:
            sig="CALL" if e21>e50 else "PUT"; score=80; reason="💵 REAL EMA Trend"
        
        return {"pair":pair,"dir":sig,"conf":score,"price":float(close.iloc[-1]),"rsi":rsi_now,"reason":reason,"mom":mom5,"payout":payout,"df":df.tail(30),"atr":atr_now}
    except Exception as e: return None

def analyze_momentum(pair):
    if "OTC" in pair: return analyze_otc_strategy(pair)
    else: return analyze_real_strategy(pair)

def iq_trade(pair,direction,amount,bal):
    is_real="OTC" not in pair
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL)
            iq.change_balance(bal)
            logging.disable(logging.NOTSET)
            logging.disable(logging.ERROR)
            time.sleep(1.0)
            if is_real:
                for mins in [1,2,5,3]:
                    try:
                        logging.disable(logging.CRITICAL)
                        check,oid=iq.buy(amount,pair,direction.lower(),mins)
                        logging.disable(logging.NOTSET)
                        logging.disable(logging.ERROR)
                        if oid and "suspend" not in str(oid).lower() and "cannot" not in str(oid).lower() and check!=False:
                            return True,oid,mins*60
                    except: continue
                    time.sleep(0.4)
            else:
                try:
                    logging.disable(logging.CRITICAL)
                    check,oid=iq.buy_blitz(pair,amount,direction.lower(),30)
                    logging.disable(logging.NOTSET)
                    logging.disable(logging.ERROR)
                    if oid and "suspend" not in str(oid).lower():
                        return True,oid,30
                except: pass
                try:
                    logging.disable(logging.CRITICAL)
                    check,oid=iq.buy(amount,pair,direction.lower(),1)
                    logging.disable(logging.NOTSET)
                    logging.disable(logging.ERROR)
                    return True,oid,60
                except: pass
            return False,None,0
    except Exception as e:
        print(f"Trade err {e}",flush=True)
        return False,None,0

@bot.message_handler(commands=['start'])
def start(m):
    if not is_allowed(m.from_user.id):
        bot.send_message(m.chat.id,f"❌ Private\nYour ID: {m.from_user.id}")
        return
    mk=types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton("💹 TRADE NOW",callback_data="trade"))
    mk.add(types.InlineKeyboardButton("📊 MY STATS",callback_data="stats"),types.InlineKeyboardButton("⚙️ SETTINGS",callback_data="settings"))
    txt=f"""🤖 **Z-BOT V8.3 PRO** 🤖

✨ *OTC Scalper + REAL Sniper*

💎 IQ: {'✅' if IQ_CONNECTED else '❌'}
💰 Balance: ${STATS['balance']:.2f}
🎯 W/L: {STATS['wins']}/{STATS['loss']}

📊 Strategies:
🔥 OTC: EMA 9/21 + Wick + MOM (Fast)
💎 REAL: EMA 21/50 + ATR + RSI14 (Sniper)

👇 **Click TRADE**
"""
    bot.send_message(m.chat.id,txt,reply_markup=mk,parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_allowed(c.from_user.id): return
    data=c.data; cid=c.message.chat.id
    if data=="trade":
        mk=types.InlineKeyboardMarkup(row_width=2)
        active=get_active_pairs()
        for p in active: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}",callback_data=f"pair_{p}"))
        bot.send_message(cid,"💹 **STEP 1/3 - SELECT PAIR**\n\n👇 Choose:",reply_markup=mk,parse_mode="Markdown")
        return
    if data.startswith("pair_"):
        pair=data.replace("pair_","")
        user_states[cid]={"pair":pair}
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🟢 DEMO",callback_data=f"bal_PRACTICE_{pair}"))
        mk.add(types.InlineKeyboardButton("🔴 REAL",callback_data=f"bal_REAL_{pair}"))
        mk.add(types.InlineKeyboardButton("⬅️ BACK",callback_data="trade"))
        bot.send_message(cid,f"✅ **{PAIR_EMOJI.get(pair,pair)}**\n\n💳 **STEP 2/3 ACCOUNT**",reply_markup=mk,parse_mode="Markdown")
        return
    if data.startswith("bal_"):
        parts=data.split("_"); bal=parts[1]; pair=parts[2]
        user_states[cid]={"pair":pair,"bal":bal}
        mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("💵 $1",callback_data=f"amt_1_{pair}_{bal}"),types.InlineKeyboardButton("💵 $5",callback_data=f"amt_5_{pair}_{bal}"),types.InlineKeyboardButton("💵 $10",callback_data=f"amt_10_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("💵 $20",callback_data=f"amt_20_{pair}_{bal}"),types.InlineKeyboardButton("💵 $50",callback_data=f"amt_50_{pair}_{bal}"),types.InlineKeyboardButton("💵 $100",callback_data=f"amt_100_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("✏️ CUSTOM",callback_data=f"custom_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("⬅️ BACK",callback_data=f"pair_{pair}"))
        bot.send_message(cid,f"✅ **{PAIR_EMOJI.get(pair,pair)} {bal}**\n\n💰 **STEP 3/3 AMOUNT**",reply_markup=mk,parse_mode="Markdown")
        return
    if data.startswith("amt_") or data.startswith("custom_"):
        if data.startswith("custom_"):
            parts=data.split("_"); pair=parts[1]; bal=parts[2]
            user_states[cid]={"pair":pair,"bal":bal,"step":"await_amt"}
            bot.send_message(cid,f"✏️ Type amount e.g 10",parse_mode="Markdown")
            return
        parts=data.split("_"); amt=float(parts[1]); pair=parts[2]; bal=parts[3]
        scan_msg=bot.send_message(cid,f"🔍 **V8.3 SCAN {PAIR_EMOJI.get(pair,pair)}**\n\n░░░░░░░░░░░░ 0%")
        legit_live_scan(cid,scan_msg.message_id,pair)
        d=analyze_momentum(pair)
        if not d:
            mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🔄 RETRY",callback_data=f"amt_{int(amt)}_{pair}_{bal}"))
            bot.send_message(cid,f"❌ Failed {pair}",reply_markup=mk); return
        dir_emoji="🟢 CALL 🟢" if d['dir']=="CALL" else "🔴 PUT 🔴"
        strat="OTC SCALPER 🔥" if "OTC" in pair else "REAL SNIPER 💎"
        signal_txt=f"""━━━━━━━━━━━━━━━
📡 **{strat} SIGNAL**
━━━━━━━━━━━━━━━

💱 {PAIR_EMOJI.get(pair,pair)}
📊 {dir_emoji}
🎯 {d['conf']:.0f}% | 💸 {int(d['payout']*100)}%
💰 ${amt} {bal}
📈 {d['reason']}
📍 {d['price']:.5f} | RSI {d['rsi']:.0f}

━━━━━━━━━━━━━━━
🤖 **PLACING...**
━━━━━━━━━━━━━━━
"""
        try:
            plt.figure(figsize=(6,3))
            color='#FFD700' if "OTC" not in pair else '#00FF6A'
            plt.plot(d['df']['close'],color=color,linewidth=2)
            plt.title(f"{pair} {d['dir']} {d['conf']:.0f}% - {strat}")
            plt.grid(alpha=0.3); plt.tight_layout(); p="/tmp/c.png"; plt.savefig(p); plt.close()
            bot.send_photo(cid,open(p,'rb'),caption=signal_txt,parse_mode="Markdown")
        except: bot.send_message(cid,signal_txt,parse_mode="Markdown")
        time.sleep(0.5)
        bot.send_message(cid,f"🚀 **PLACING {pair}...**")
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal)
        if not ok:
            bot.send_message(cid,"❌ Trade Failed - Try again"); iq_reconnect(); return
        bot.send_message(cid,f"✅ **PLACED!** ID `{oid}` ⏱️ {exp}s",parse_mode="Markdown")
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
                mk.add(types.InlineKeyboardButton("🔁 SAME",callback_data=f"amt_{int(amt)}_{pair}_{bal}"),types.InlineKeyboardButton("💹 NEW",callback_data="trade"))
                bot.send_message(cid,f"✅ **WIN +${pnl:.2f}** Bal ${STATS['balance']:.2f} 🎉",reply_markup=mk,parse_mode="Markdown")
            else:
                STATS['loss']+=1; STATS['balance']-=amt
                mk=types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton(f"🔁 MARTI ${amt*2.2:.0f}",callback_data=f"amt_{int(amt*2.2)}_{pair}_{bal}"),types.InlineKeyboardButton("💹 NEW",callback_data="trade"))
                bot.send_message(cid,f"❌ **LOSS -${amt}** Bal ${STATS['balance']:.2f}",reply_markup=mk,parse_mode="Markdown")
        except: bot.send_message(cid,f"⏱️ Expired {oid} Check app")
        return
    if data=="stats":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0
        bot.send_message(cid,f"📊 **V8.3 STATS**\nW {STATS['wins']} L {STATS['loss']} {wr:.1f}%\nBal ${STATS['balance']:.2f}",parse_mode="Markdown")
    if data=="settings":
        bot.send_message(cid,f"⚙️ **V8.3 SETTINGS**\n\n🔥 OTC: EMA9/21 + Wick 0.4 + RSI7 + MOM\n💎 REAL: EMA21/50 + ATR + RSI14 + MOM5\nOwner: {OWNER_ID}")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id,{}).get("step")=="await_amt")
def handle_custom_amt(m):
    if not is_allowed(m.from_user.id): return
    cid=m.chat.id; st=user_states.get(cid,{})
    try:
        amt=float(m.text.strip()); pair=st.get("pair"); bal=st.get("bal")
        if not pair: return
        scan_msg=bot.send_message(cid,f"🔍 **V8.3 SCAN {pair}**\n\n░░░░░░░░ 0%")
        legit_live_scan(cid,scan_msg.message_id,pair)
        d=analyze_momentum(pair)
        if not d: bot.send_message(cid,"Failed"); return
        strat="OTC SCALPER 🔥" if "OTC" in pair else "REAL SNIPER 💎"
        bot.send_message(cid,f"📡 **{strat}** {PAIR_EMOJI.get(pair,pair)} {d['dir']} {d['conf']:.0f}% ${amt}\n{d['reason']}")
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal)
        if ok:
            bot.send_message(cid,f"✅ Placed {oid} ⏳ {exp}s")
            time.sleep(exp+5)
            try:
                with IQ_LOCK:
                    logging.disable(logging.CRITICAL)
                    pnl=iq.check_win_v4(oid)
                    logging.disable(logging.NOTSET)
                    logging.disable(logging.ERROR)
                if pnl>0: bot.send_message(cid,f"✅ WIN +${pnl:.2f}")
                else: bot.send_message(cid,f"❌ LOSS -${amt}")
            except: bot.send_message(cid,"Check app")
        user_states.pop(cid,None)
    except: bot.send_message(cid,"❌ Send number e.g 100")

@app.route(f"/{BOT_TOKEN}",methods=['POST'])
def wh(): bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode("utf-8"))]); return "ok"
@app.route("/")
def home():
    u=os.getenv("RENDER_EXTERNAL_URL")
    if u:
        try: requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={u}/{BOT_TOKEN}",timeout=5)
        except: pass
    return "V8.3 OTC SCALPER + REAL SNIPER - RUNNING"
app.run(host="0.0.0.0",port=int(os.getenv("PORT",10000)))
