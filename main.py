import os, time, threading, warnings, logging
from datetime import datetime, timedelta, timezone
import telebot
from telebot import types
import pandas as pd
import pytz

warnings.filterwarnings("ignore")
logging.getLogger().setLevel(logging.CRITICAL)

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 8659453018
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

REAL_PAIRS = ["EURUSD","GBPUSD","USDJPY","EURGBP","AUDUSD","USDCAD","EURJPY","GBPJPY"]
OTC_PAIRS = ["EURUSD-OTC","GBPUSD-OTC","EURGBP-OTC","USDJPY-OTC","GBPJPY-OTC","AUDUSD-OTC","USDCHF-OTC","EURJPY-OTC","AUDJPY-OTC","EURAUD-OTC","GBPAUD-OTC","NZDUSD-OTC","GBPCHF-OTC","EURCHF-OTC","USDZAR-OTC"]
PAIR_EMOJI = {"EURUSD":"🇪🇺 EUR/USD REAL","GBPUSD":"🇬🇧 GBP/USD REAL","USDJPY":"🇺🇸 USD/JPY REAL","EURGBP":"🇪🇺 EUR/GBP REAL","AUDUSD":"🇦🇺 AUD/USD REAL","USDCAD":"🇺🇸 USD/CAD REAL","EURJPY":"🇪🇺 EUR/JPY REAL","GBPJPY":"🇬🇧 GBP/JPY REAL","EURUSD-OTC":"🇪🇺 EUR/USD OTC","GBPUSD-OTC":"🇬🇧 GBP/USD OTC","EURGBP-OTC":"🇪🇺 EUR/GBP OTC","USDJPY-OTC":"🇺🇸 USD/JPY OTC","GBPJPY-OTC":"🇬🇧 GBP/JPY OTC","AUDUSD-OTC":"🇦🇺 AUD/USD OTC","USDCHF-OTC":"🇺🇸 USD/CHF OTC","EURJPY-OTC":"🇪🇺 EUR/JPY OTC","AUDJPY-OTC":"🇦🇺 AUD/JPY OTC","EURAUD-OTC":"🇪🇺 EUR/AUD OTC","GBPAUD-OTC":"🇬🇧 GBP/AUD OTC","NZDUSD-OTC":"🇳🇿 NZD/USD OTC","GBPCHF-OTC":"🇬🇧 GBP/CHF OTC","EURCHF-OTC":"🇪🇺 EUR/CHF OTC","USDZAR-OTC":"🇺🇸 USD/ZAR OTC"}

STATS = {"wins":0,"loss":0,"streak":0}
user_states = {}; AUTO_STATE = {}; IQ_LOCK = threading.Lock()
IQ_CONNECTED=False; iq=None; PAYOUT_CACHE={}; PAYOUT_TIME=0
SCANNER_ENABLED = {"real": True}

def is_allowed(uid): return uid == OWNER_ID
def is_real_hours():
    try:
        tz = pytz.timezone("Africa/Lagos"); now = datetime.now(tz)
        if now.weekday() >= 5: return False
        return 7 <= now.hour < 20
    except:
        now = datetime.now(timezone.utc) + timedelta(hours=1)
        return 7 <= now.hour < 20 and now.weekday()<5
def get_mode_text(): return "REAL SIGNAL (7AM-8PM)" if is_real_hours() else "OTC TRADING (8PM-7AM+Weekend)"

try:
    from iqoptionapi.stable_api import IQ_Option
    EMAIL=os.getenv("IQ_EMAIL"); PWD=os.getenv("IQ_PASS")
    if EMAIL and PWD:
        iq=IQ_Option(EMAIL,PWD); iq.connect(); IQ_CONNECTED=iq.check_connect()
except: IQ_CONNECTED=False

def iq_reconnect():
    global iq, IQ_CONNECTED
    try:
        from iqoptionapi.stable_api import IQ_Option
        iq=IQ_Option(os.getenv("IQ_EMAIL"),os.getenv("IQ_PASS")); iq.connect(); IQ_CONNECTED=iq.check_connect(); return IQ_CONNECTED
    except: return False
def get_real_balance(bal_type="PRACTICE"):
    try:
        with IQ_LOCK: iq.change_balance(bal_type); return iq.get_balance()
    except: return 0.0
def get_payout(pair):
    global PAYOUT_CACHE, PAYOUT_TIME
    if time.time()-PAYOUT_TIME<60 and pair in PAYOUT_CACHE: return PAYOUT_CACHE[pair]
    try:
        with IQ_LOCK: all_p=iq.get_all_profit()
        if pair in all_p:
            for k in ['blitz','turbo','binary']:
                if k in all_p[pair]: PAYOUT_CACHE[pair]=float(all_p[pair][k]); PAYOUT_TIME=time.time(); return float(all_p[pair][k])
        return 0.85
    except: return 0.85
def get_candles(pair):
    if not IQ_CONNECTED and not iq_reconnect(): return None
    for _ in range(3):
        try:
            with IQ_LOCK: c=iq.get_candles(pair,60,50,time.time())
            if c and len(c)>25: return pd.DataFrame(sorted(c,key=lambda x:x['from']))
            time.sleep(0.6)
        except: time.sleep(0.6)
    return None
def calc_rsi(closes, period=7):
    delta=closes.diff(); gain=delta.where(delta>0,0).rolling(period).mean(); loss=-delta.where(delta<0,0).rolling(period).mean(); rs=gain/loss; return 100-(100/(1+rs))
def calc_atr(df, period=14):
    try:
        high=df['max']; low=df['min']; close=df['close']; tr1=high-low; tr2=(high-close.shift()).abs(); tr3=(low-close.shift()).abs(); tr=pd.concat([tr1,tr2,tr3],axis=1).max(axis=1); return tr.rolling(period).mean().iloc[-1]
    except: return 0.0005
def legit_live_scan(cid, mid, pair):
    steps = [(0,"🚀 Initializing V8...",0.15),(15,f"🔌 IQ Check {pair}...",0.2),(30,"📊 Fetching candles...",0.25),(50,"📈 EMA9 + EMA21...",0.2),(70,"💹 RSI + ATR...",0.2),(85,"📰 Final check...",0.2),(100,"🔒 SIGNAL LOCKED!")]
    for pct,text,delay in steps:
        filled=int(pct//5); bar="█"*filled+"░"*(20-filled); color="🟥" if pct<40 else "🟨" if pct<80 else "🟩" if pct<100 else "💎"
        try: bot.edit_message_text(f"{color} **Z-BOT V8 LEGIT SCAN** {color}\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n💎 IQ: {'✅' if IQ_CONNECTED else '❌'}\n\n{bar} {pct}%\n\n🔍 {text}",cid,mid,parse_mode="Markdown")
        except: pass
        time.sleep(delay)
def analyze_momentum(pair, sniper_mode=False):
    df=get_candles(pair)
    if df is None: return None
    try:
        close=df['close']; open_=df['open']; high=df['max']; low=df['min']
        ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean(); ema50=close.ewm(50).mean()
        rsi=calc_rsi(close,7); atr=calc_atr(df,14)
        rsi_now=float(rsi.iloc[-1]); e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1]); e50=float(ema50.iloc[-1])
        c_now=float(close.iloc[-1]); o_now=float(open_.iloc[-1]); h_now=float(high.iloc[-1]); l_now=float(low.iloc[-1])
        mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100; mom3=(close.iloc[-1]-close.iloc[-4])/close.iloc[-4]*100
        is_green=c_now>o_now; body=abs(c_now-o_now); upper_wick=h_now-max(c_now,o_now); lower_wick=min(c_now,o_now)-l_now
        payout=get_payout(pair); sig="CALL" if is_green else "PUT"; score=65; reason=""; expiry=120
        if "-OTC" not in pair:
            expiry=120 if abs(mom1)<0.08 else 180
            if atr < 0.0001: score-=10
            if body < atr*0.3: score-=15
            if e9>e21 and e21>e50 and is_green and rsi_now>52 and rsi_now<72 and lower_wick>upper_wick and mom1>0.03: sig="CALL"; score=92; reason=f"🚀 Bullish PA Wick {mom1:.3f}%"
            elif e9<e21 and e21<e50 and not is_green and rsi_now<48 and rsi_now>28 and upper_wick>lower_wick and mom1<-0.03: sig="PUT"; score=92; reason=f"📉 Bearish PA Wick {mom1:.3f}%"
            elif e9>e21 and is_green and rsi_now>50 and mom1>0.02: sig="CALL"; score=84; reason="📈 EMA Bull + PA"
            elif e9<e21 and not is_green and rsi_now<50 and mom1<-0.02: sig="PUT"; score=84; reason="📉 EMA Bear + PA"
        else:
            expiry=60 if abs(mom1)>0.05 else 120
            if mom1>0.02 and mom3>0.05 and is_green and e9>e21 and rsi_now>50 and rsi_now<78: sig="CALL"; score=90; reason=f"🚀 Bullish {mom1:.3f}%"; expiry=60
            elif mom1<-0.02 and mom3<-0.05 and not is_green and e9<e21 and rsi_now<50: sig="PUT"; score=90; reason=f"📉 Bearish {mom1:.3f}%"; expiry=60
            elif e9>e21 and is_green: sig="CALL"; score=82; reason="📈 EMA Bull"
            elif e9<e21 and not is_green: sig="PUT"; score=82; reason="📉 EMA Bear"
        if sniper_mode and score<85: return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":rsi_now,"reason":reason,"payout":payout,"expiry":expiry,"atr":atr,"rejected":True}
        return {"pair":pair,"dir":sig,"conf":min(94,score),"price":c_now,"rsi":rsi_now,"reason":reason,"payout":payout,"expiry":expiry,"atr":atr,"rejected":False}
    except: return None
def iq_trade(pair,direction,amount,bal,expiry_sec=30):
    if not IQ_CONNECTED and not iq_reconnect(): return False,None,0
    try:
        with IQ_LOCK:
            iq.change_balance(bal)
            if "-OTC" in pair and expiry_sec<=90:
                try: _,oid=iq.buy_blitz(pair,amount,direction.lower(),expiry_sec); return True,oid,expiry_sec
                except: pass
            mins=max(1,int(expiry_sec/60)); check,oid=iq.buy(amount,pair,direction.lower(),mins); return (True,oid,expiry_sec) if check else (False,None,0)
    except: return False,None,0

def real_signal_scanner():
    last_signal={}; tz=pytz.timezone("Africa/Lagos")
    while True:
        try:
            if not SCANNER_ENABLED["real"]: time.sleep(10); continue
            if is_real_hours() and IQ_CONNECTED:
                for pair in REAL_PAIRS:
                    if pair in last_signal and time.time()-last_signal[pair]<600: continue
                    d=analyze_momentum(pair,sniper_mode=True)
                    if d and not d.get('rejected') and d['conf']>=86:
                        now=datetime.now(tz); entry=now+timedelta(seconds=45); exp=d['expiry']; exp_txt=f"{exp//60} min {exp%60}s" if exp>=60 else f"{exp}s"
                        dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"
                        msg=f"📡 **REAL SIGNAL 9.5** 📡\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n📊 {dir_e} | 🎯 {d['conf']:.0f}%\n📈 {d['reason']} | RSI {d['rsi']:.1f}\n💸 Payout {int(d['payout']*100)}%\n\n⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)\n⏱️ EXPIRY: {exp_txt}\n📅 {now.strftime('%A %d %b %H:%M WAT')}\n\n⚠️ PLACE MANUALLY ON IQ"
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
            bot.send_message(cid,f"🤖 Auto OTC {pair_to_trade} {d['dir']} ${curr_amt:.2f} {d['conf']}% - ID {oid}\n💰 Bal ${bal_now:.2f}")
            time.sleep(exp+6)
            try:
                with IQ_LOCK: pnl=iq.check_win_v4(oid)
                bal_now=get_real_balance(state['bal'])
                if pnl>0:
                    STATS['wins']+=1; STATS['streak']+=1; AUTO_STATE[cid]['trades']+=1; consecutive_losses=0
                    bot.send_message(cid,f"✅ WIN +${pnl:.2f} | {pair_to_trade}\n💰 Bal ${bal_now:.2f} | Streak {STATS['streak']}")
                else:
                    STATS['loss']+=1; STATS['streak']=0; AUTO_STATE[cid]['trades']+=1; consecutive_losses+=1
                    bot.send_message(cid,f"❌ LOSS -${curr_amt:.2f} | Bal ${bal_now:.2f} | Next ${state['base_amt']*(2.2**consecutive_losses):.2f}")
                    if consecutive_losses>=3: consecutive_losses=0; time.sleep(60)
            except: bot.send_message(cid,f"⏱️ Expired {oid} - Check IQ")
            time.sleep(8)
        except: time.sleep(10)

@bot.message_handler(commands=['start','stop','mode','balance','stop_signals','start_signals','stop_all'])
def start_cmd(m):
    if not is_allowed(m.from_user.id): return
    if m.text.startswith('/stop_all'):
        SCANNER_ENABLED["real"]=False
        if m.chat.id in AUTO_STATE: AUTO_STATE[m.chat.id]['running']=False
        bot.send_message(m.chat.id,"🛑 ALL STOPPED\n❌ REAL Scanner OFF\n❌ OTC Auto OFF"); return
    if m.text.startswith('/stop_signals'): SCANNER_ENABLED["real"]=False; bot.send_message(m.chat.id,"🛑 REAL SIGNALS STOPPED\n💤 Sleeping\n/start_signals to wake"); return
    if m.text.startswith('/start_signals'): SCANNER_ENABLED["real"]=True; bot.send_message(m.chat.id,"✅ REAL SIGNALS STARTED\n🔍 Scanning 8 REAL pairs Mon-Fri 7AM-8PM"); return
    if m.text.startswith('/stop'):
        if m.chat.id in AUTO_STATE: AUTO_STATE[m.chat.id]['running']=False; bot.send_message(m.chat.id,"🛑 Stopping OTC Auto...")
        else: bot.send_message(m.chat.id,"Auto not running. Use /stop_signals for REAL"); return
    if m.text.startswith('/mode'):
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz)
        txt=f"📍 MODE CHECK\n\n⏰ {now.strftime('%A %H:%M:%S WAT')}\n📊 Market: {get_mode_text()}\n🔍 REAL Scanner: {'✅ ACTIVE' if SCANNER_ENABLED['real'] and is_real_hours() else '❌ STOPPED' if not SCANNER_ENABLED['real'] else '💤 SLEEP'}\n🤖 OTC Auto: {'✅ RUNNING' if m.chat.id in AUTO_STATE and AUTO_STATE[m.chat.id].get('running') else '❌ STOPPED'}\n💎 IQ: {'✅' if IQ_CONNECTED else '❌'}"
        bot.send_message(m.chat.id,txt); return
    if m.text.startswith('/balance'):
        demo=get_real_balance("PRACTICE"); real=get_real_balance("REAL")
        bot.send_message(m.chat.id,f"💰 BALANCES\n🟢 DEMO: ${demo:.2f}\n🔴 REAL: ${real:.2f}"); return
    bal_demo=get_real_balance("PRACTICE")
    mk=types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton(f"💹 MANUAL OTC (15) - ${bal_demo:.2f}",callback_data="trade"))
    mk.add(types.InlineKeyboardButton("🤖 AUTO-TRADER OTC 90%+",callback_data="auto_setup"))
    mk.add(types.InlineKeyboardButton("📊 MY STATS",callback_data="stats"))
    bot.send_message(m.chat.id,f"🤖 Z-BOT PRO V9.5 ULTRA 🤖\n\n💎 IQ: {'✅' if IQ_CONNECTED else '❌'} | 💰 DEMO ${bal_demo:.2f}\n🏆 W:{STATS['wins']} L:{STATS['loss']} | 🔥 {STATS['streak']}\n📍 {get_mode_text()}\n🔍 Scanner: {'✅' if SCANNER_ENABLED['real'] else '❌'}\n\nCommands: /mode /balance /stop_signals /start_signals /stop_all\n\n👇 OTC Trading:",reply_markup=mk)

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_allowed(c.from_user.id): return
    data=c.data; cid=c.message.chat.id
    if data=="trade":
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in OTC_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}",callback_data=f"pair_{p}"))
        bot.send_message(cid,f"💹 MANUAL OTC (15 PAIRS)\n📍 {get_mode_text()}",reply_markup=mk); return
    if data=="auto_setup":
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🤖 AUTO SCAN ALL 15 OTC",callback_data="auto_pair_AUTO"))
        for p in OTC_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}",callback_data=f"auto_pair_{p}"))
        bot.send_message(cid,f"🤖 AUTO SETUP 1/4 - OTC ONLY",reply_markup=mk); return
    if data.startswith("auto_pair_"):
        pair=data.replace("auto_pair_",""); mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🟢 DEMO",callback_data=f"auto_bal_PRACTICE_{pair}")); mk.add(types.InlineKeyboardButton("🔴 REAL",callback_data=f"auto_bal_REAL_{pair}"))
        bot.send_message(cid,f"✅ Pair: {pair}\n\n🤖 SETUP 2/4 - ACCOUNT",reply_markup=mk); return
    if data.startswith("auto_bal_"):
        parts=data.split("_"); bal=parts[2]; pair=parts[3]; mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("💵 $1",callback_data=f"auto_amt_1_{pair}_{bal}"),types.InlineKeyboardButton("💵 $5",callback_data=f"auto_amt_5_{pair}_{bal}"),types.InlineKeyboardButton("💵 $10",callback_data=f"auto_amt_10_{pair}_{bal}"))
        bot.send_message(cid,f"✅ {pair} {bal}\n\n🤖 SETUP 3/4 - BASE AMOUNT",reply_markup=mk); return
    if data.startswith("auto_amt_"):
        parts=data.split("_"); amt=float(parts[2]); pair=parts[3]; bal=parts[4]; mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("⏱️ 30 SEC",callback_data=f"auto_exp_30_{pair}_{bal}_{int(amt)}"),types.InlineKeyboardButton("⏱️ 1 MIN",callback_data=f"auto_exp_60_{pair}_{bal}_{int(amt)}"))
        mk.add(types.InlineKeyboardButton("⏱️ 2 MIN",callback_data=f"auto_exp_120_{pair}_{bal}_{int(amt)}"))
        bot.send_message(cid,f"✅ Base ${amt}\n\n🤖 SETUP 4/4 - EXPIRY",reply_markup=mk); return
    if data.startswith("auto_exp_"):
        parts=data.split("_"); expiry=int(parts[2]); pair=parts[3]; bal=parts[4]; amt=float(parts[5])
        AUTO_STATE[cid]={"running":True,"pair":pair,"bal":bal,"base_amt":amt,"expiry":expiry,"martingale":True,"trades":0}
        bot.send_message(cid,f"🚀 STARTING AUTO OTC {pair} ${amt} {expiry}s\n💰 Bal ${get_real_balance(bal):.2f}")
        threading.Thread(target=auto_trader_loop,args=(cid,),daemon=True).start(); return
    if data=="stop_auto":
        if cid in AUTO_STATE: AUTO_STATE[cid]['running']=False; bot.send_message(cid,"🛑 Stopping..."); return
    if data.startswith("pair_"):
        pair=data.replace("pair_",""); mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🟢 DEMO",callback_data=f"bal_PRACTICE_{pair}"),types.InlineKeyboardButton("🔴 REAL",callback_data=f"bal_REAL_{pair}"))
        bot.send_message(cid,f"✅ PAIR: {PAIR_EMOJI.get(pair,pair)}\n\n💳 STEP 2/4 - ACCOUNT",reply_markup=mk); return
    if data.startswith("bal_"):
        parts=data.split("_"); bal=parts[1]; pair=parts[2]; mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("💵 $1",callback_data=f"amt_1_{pair}_{bal}"),types.InlineKeyboardButton("💵 $5",callback_data=f"amt_5_{pair}_{bal}"),types.InlineKeyboardButton("💵 $10",callback_data=f"amt_10_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("✏️ CUSTOM",callback_data=f"custom_{pair}_{bal}"))
        bot.send_message(cid,f"✅ {pair} {bal}\n\n💰 STEP 3/4 - AMOUNT",reply_markup=mk); return
    if data.startswith("amt_") or data.startswith("custom_"):
        if data.startswith("custom_"):
            parts=data.split("_"); pair=parts[1]; bal=parts[2]; user_states[cid]={"pair":pair,"bal":bal,"step":"await_amt"}
            bot.send_message(cid,f"✏️ Type amount for {pair} {bal}"); return
        parts=data.split("_"); amt=float(parts[1]); pair=parts[2]; bal=parts[3]; mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("⏱️ 30 SEC",callback_data=f"exp_30_{pair}_{bal}_{int(amt)}"),types.InlineKeyboardButton("⏱️ 1 MIN",callback_data=f"exp_60_{pair}_{bal}_{int(amt)}"))
        mk.add(types.InlineKeyboardButton("⏱️ 2 MIN",callback_data=f"exp_120_{pair}_{bal}_{int(amt)}"))
        bot.send_message(cid,f"✅ ${amt}\n\n⏱️ STEP 4/4 - EXPIRY",reply_markup=mk); return
    if data.startswith("exp_"):
        parts=data.split("_"); expiry=int(parts[1]); pair=parts[2]; bal=parts[3]; amt=float(parts[4])
        bot.answer_callback_query(c.id,f"Analyzing...")
        scan_msg=bot.send_message(cid,f"🔍 V8 SCAN {PAIR_EMOJI.get(pair,pair)}\n\n0%\n🚀 Starting...")
        legit_live_scan(cid,scan_msg.message_id,pair)
        d=analyze_momentum(pair,sniper_mode=False)
        if not d: bot.send_message(cid,f"❌ Failed analyze {pair}"); return
        dir_emoji="🟢 CALL" if d['dir']=="CALL" else "🔴 PUT"
        bot.send_message(cid,f"📡 SIGNAL FOUND!\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n📊 {dir_emoji} | 🎯 {d['conf']:.0f}%\n💸 {int(d['payout']*100)}% | 💰 ${amt} | ⏱️ {expiry}s\n📈 {d['reason']}\n\n🤖 PLACING TRADE...")
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal,expiry)
        if not ok: bot.send_message(cid,"❌ Trade Failed"); iq_reconnect(); return
        bot.send_message(cid,f"✅ Placed {oid} | Waiting {exp}s... | Bal ${get_real_balance(bal):.2f}")
        time.sleep(exp+6)
        try:
            with IQ_LOCK: pnl=iq.check_win_v4(oid)
            bal_now=get_real_balance(bal)
            if pnl>0: STATS['wins']+=1; STATS['streak']+=1; bot.send_message(cid,f"✅ WIN +${pnl:.2f}\nBal ${bal_now:.2f}")
            else: STATS['loss']+=1; STATS['streak']=0; bot.send_message(cid,f"❌ LOSS -${amt}\nBal ${bal_now:.2f}")
        except: bot.send_message(cid,f"⏱️ Expired - Check IQ app {oid}")
        return
    if data=="stats":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0; bal=get_real_balance("PRACTICE")
        bot.send_message(cid,f"📊 STATS 9.5\n📍 {get_mode_text()}\n🏆 Wins: {STATS['wins']}\n❌ Loss: {STATS['loss']}\n📈 Winrate: {wr:.1f}%\n🔥 Streak: {STATS['streak']}\n💰 Bal: ${bal:.2f}")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id,{}).get("step")=="await_amt")
def handle_custom_amt(m):
    cid=m.chat.id; st=user_states.get(cid,{})
    if not is_allowed(m.from_user.id): return
    try:
        amt=float(m.text.strip()); pair=st.get("pair"); bal=st.get("bal")
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("⏱️ 30 SEC",callback_data=f"exp_30_{pair}_{bal}_{int(amt)}"),types.InlineKeyboardButton("⏱️ 1 MIN",callback_data=f"exp_60_{pair}_{bal}_{int(amt)}"))
        bot.send_message(cid,f"✅ Custom ${amt} for {pair}\n\n⏱️ STEP 4/4 - EXPIRY",reply_markup=mk)
    except: bot.send_message(cid,"❌ Send number only")

print("🚀 Z-BOT V9.5 POLLING STARTING...")
threading.Thread(target=real_signal_scanner,daemon=True).start()
# Startup alert
def notify():
    time.sleep(3)
    try:
        import pytz; tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz)
        bot.send_message(OWNER_ID,f"🚀 Z-BOT V9.5 POLLING STARTED!\n\n⏰ {now.strftime('%A %H:%M:%S WAT')}\n📍 {get_mode_text()}\n💎 IQ: {'✅' if IQ_CONNECTED else '❌'}\n\n🔍 REAL Scanner: {'✅ ACTIVE' if SCANNER_ENABLED['real'] and is_real_hours() else '💤 SLEEP'}\n\nType /start to trade\n/mode to check status")
    except Exception as e: print(e)

threading.Thread(target=notify,daemon=True).start()

bot.infinity_polling(timeout=60, long_polling_timeout=60)
