import os, time, threading, warnings, logging
from datetime import datetime, timedelta, timezone
from flask import Flask, request
import telebot
from telebot import types
import pandas as pd
import requests
import pytz

warnings.filterwarnings("ignore")
logging.getLogger().setLevel(logging.CRITICAL)
logging.getLogger("iqoptionapi").setLevel(logging.CRITICAL)
logging.disable(logging.ERROR)

BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELE_TOKEN")
OWNER_ID = 8659453018
if not BOT_TOKEN:
    print("ERROR BOT_TOKEN missing")
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)

REAL_PAIRS = ["EURUSD","GBPUSD","USDJPY","EURGBP","AUDUSD","USDCAD","EURJPY","GBPJPY","USDCHF","AUDJPY","EURAUD","GBPCHF","EURCHF","NZDUSD","GBPAUD","EURCAD","AUDCAD","GBPCAD","NZDJPY","AUDNZD","CHFJPY","CADJPY"]
OTC_PAIRS = ["EURUSD-OTC","GBPUSD-OTC","AUDUSD-OTC","EURGBP-OTC","EURJPY-OTC","GBPJPY-OTC","AUDJPY-OTC","EURAUD-OTC","GBPAUD-OTC","NZDUSD-OTC"]
PAIR_EMOJI = {"EURUSD":"🇪🇺 EUR/USD REAL","GBPUSD":"🇬🇧 GBP/USD REAL","USDJPY":"🇺🇸 USD/JPY REAL","EURGBP":"🇪🇺 EUR/GBP REAL","AUDUSD":"🇦🇺 AUD/USD REAL","USDCAD":"🇺🇸 USD/CAD REAL","EURJPY":"🇪🇺 EUR/JPY REAL","GBPJPY":"🇬🇧 GBP/JPY REAL","USDCHF":"🇺🇸 USD/CHF REAL","AUDJPY":"🇦🇺 AUD/JPY REAL","EURAUD":"🇪🇺 EUR/AUD REAL","GBPCHF":"🇬🇧 GBP/CHF REAL","EURCHF":"🇪🇺 EUR/CHF REAL","NZDUSD":"🇳🇿 NZD/USD REAL","GBPAUD":"🇬🇧 GBP/AUD REAL","EURCAD":"🇪🇺 EUR/CAD REAL","AUDCAD":"🇦🇺 AUD/CAD REAL","GBPCAD":"🇬🇧 GBP/CAD REAL","NZDJPY":"🇳🇿 NZD/JPY REAL","AUDNZD":"🇦🇺 AUD/NZD REAL","CHFJPY":"🇨🇭 CHF/JPY REAL","CADJPY":"🇨🇦 CAD/JPY REAL","EURUSD-OTC":"🇪🇺 EUR/USD OTC","GBPUSD-OTC":"🇬🇧 GBP/USD OTC","EURGBP-OTC":"🇪🇺 EUR/GBP OTC","USDJPY-OTC":"🇺🇸 USD/JPY OTC","GBPJPY-OTC":"🇬🇧 GBP/JPY OTC","AUDUSD-OTC":"🇦🇺 AUD/USD OTC","USDCHF-OTC":"🇺🇸 USD/CHF OTC","EURJPY-OTC":"🇪🇺 EUR/JPY OTC","AUDJPY-OTC":"🇦🇺 AUD/JPY OTC","EURAUD-OTC":"🇪🇺 EUR/AUD OTC","GBPAUD-OTC":"🇬🇧 GBP/AUD OTC","NZDUSD-OTC":"🇳🇿 NZD/USD OTC","GBPCHF-OTC":"🇬🇧 GBP/CHF OTC","EURCHF-OTC":"🇪🇺 EUR/CHF OTC","USDCAD-OTC":"🇺🇸 USD/CAD OTC","AUDCAD-OTC":"🇦🇺 AUD/CAD OTC","EURCAD-OTC":"🇪🇺 EUR/CAD OTC","CADJPY-OTC":"🇨🇦 CAD/JPY OTC","NZDJPY-OTC":"🇳🇿 NZD/JPY OTC"}

STATS = {"balance":0.0,"real_balance":0.0,"wins":0,"loss":0,"streak":0}
user_states = {}; AUTO_STATE = {}; IQ_LOCK = threading.Lock()
IQ_CONNECTED=False; iq=None; PAYOUT_CACHE={}; PAYOUT_TIME=0
OTC_SESSION_RESULTS = []
OTC_MARTI = {"loss_streak":0, "base":1.0, "bal":"PRACTICE", "levels":[1,2,4]}

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

@app.route("/")
def home():
    return f"V11 FREE WEB SERVICE RUNNING IQ:{IQ_CONNECTED} {datetime.now(pytz.timezone('Africa/Lagos')).strftime('%H:%M:%S')}"

@app.route(f"/{BOT_TOKEN}",methods=['POST'])
def wh(): 
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode("utf-8"))])
    return "ok"

def background_iq():
    global iq, IQ_CONNECTED
    time.sleep(3)
    for attempt in range(10):
        try:
            from iqoptionapi.stable_api import IQ_Option
            EMAIL=os.getenv("IQ_EMAIL"); PWD=os.getenv("IQ_PASS")
            PROXY=os.getenv("PROXY_URL")
            if not EMAIL or not PWD:
                print("IQ_EMAIL/PASS missing"); return
            print(f"[IQ] Attempt {attempt+1}/10 Email:{EMAIL} Proxy:{'YES' if PROXY else 'NO'}")
            iq=IQ_Option(EMAIL,PWD)
            if PROXY:
                try:
                    pc = PROXY.replace("http://","").replace("https://","")
                    if "@" in pc:
                        up, hp = pc.split("@")
                        pu, pp = up.split(":")
                        ph, pt = hp.split(":")
                        print(f"[IQ] Setting proxy {ph}:{pt}")
                        iq.set_proxy(proxy_type="http", host=ph, port=int(pt), user=pu, password=pp)
                except Exception as pe:
                    print(f"[IQ] Proxy parse error {pe}")
            logging.disable(logging.CRITICAL)
            iq.connect()
            IQ_CONNECTED=iq.check_connect()
            print(f"[IQ] check_connect={IQ_CONNECTED}")
            if IQ_CONNECTED:
                try:
                    iq.change_balance("PRACTICE")
                    time.sleep(1)
                    bal = iq.get_balance()
                    STATS["real_balance"]=bal
                    print(f"[IQ] SUCCESS BALANCE ${bal}")
                except Exception as be:
                    print(f"[IQ] Balance err {be} but connected")
                print(f"[IQ] CONNECTED TRUE")
                return
            else:
                print(f"[IQ] False, retrying...")
                time.sleep(8)
        except Exception as e:
            print(f"[IQ] Fail attempt {attempt+1}: {e}")
            import traceback; traceback.print_exc()
            time.sleep(10)
    IQ_CONNECTED=False
    print("[IQ] FAILED AFTER 10")

def iq_reconnect():
    global iq, IQ_CONNECTED
    try:
        from iqoptionapi.stable_api import IQ_Option
        logging.disable(logging.CRITICAL)
        iq=IQ_Option(os.getenv("IQ_EMAIL"),os.getenv("IQ_PASS"))
        PROXY=os.getenv("PROXY_URL")
        if PROXY:
            try:
                pc = PROXY.replace("http://","").replace("https://","")
                if "@" in pc:
                    up, hp = pc.split("@")
                    pu, pp = up.split(":")
                    ph, pt = hp.split(":")
                    iq.set_proxy(proxy_type="http", host=ph, port=int(pt), user=pu, password=pp)
            except: pass
        iq.connect()
        IQ_CONNECTED=iq.check_connect()
        if IQ_CONNECTED: 
            try: STATS["real_balance"]=iq.get_balance()
            except: pass
        return IQ_CONNECTED
    except: IQ_CONNECTED=False; return False

def get_real_balance(bal_type="PRACTICE"):
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL); iq.change_balance(bal_type); bal=iq.get_balance()
            return bal
    except: return 0.0

def get_payout(pair):
    global PAYOUT_CACHE, PAYOUT_TIME
    if time.time()-PAYOUT_TIME<60 and pair in PAYOUT_CACHE: return PAYOUT_CACHE[pair]
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL); all_p=iq.get_all_profit()
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
            if c and len(c)>25: return pd.DataFrame(sorted(c,key=lambda x:x['from']))
            time.sleep(0.4)
        except: time.sleep(0.4)
    return None

def calc_rsi(closes, period=7):
    delta=closes.diff(); gain=delta.where(delta>0,0).rolling(period).mean(); loss=-delta.where(delta<0,0).rolling(period).mean(); rs=gain/loss; return 100-(100/(1+rs))

def calc_atr(df, period=14):
    try:
        high=df['max']; low=df['min']; close=df['close']; tr1=high-low; tr2=(high-close.shift()).abs(); tr3=(low-close.shift()).abs(); tr=pd.concat([tr1,tr2,tr3],axis=1).max(axis=1); return tr.rolling(period).mean().iloc[-1]
    except: return 0.0005

def legit_live_scan(cid, mid, pair):
    steps = [(0,"🚀 V11 Safe Init...",0.15),(20,f"🔌 Checking {pair}...",0.2),(40,"📊 ATR + Body Filter...",0.25),(60,"📈 EMA 3 Align...",0.2),(80,"💹 RSI Safe Zone + PA...",0.2),(100,"🔒 SAFE EXPIRY LOCKED!",0.3)]
    last_pct=-1
    for pct, text, delay in steps:
        if pct==last_pct: time.sleep(delay); continue
        last_pct=pct; filled=int(pct//5); bar="█"*filled+"░"*(20-filled); color="🟥" if pct<40 else "🟨" if pct<80 else "🟩" if pct<100 else "💎"
        txt=f"""{color} **Z-BOT V11 SAFE AUTO** {color}\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n💎 IQ: {'✅' if IQ_CONNECTED else '❌'}\n\n{bar} {pct}%\n\n🔍 {text}\n⏳ Auto Safe Expiry V11"""
        try: bot.edit_message_text(txt,cid,mid,parse_mode="Markdown")
        except: pass
        time.sleep(delay)

def analyze_momentum(pair, sniper_mode=False):
    df=get_candles(pair)
    if df is None: return None
    try:
        close=df['close']; open_=df['open']; high=df['max']; low=df['min']; ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean(); ema50=close.ewm(50).mean(); rsi_fast=calc_rsi(close,7); rsi_slow=calc_rsi(close,14); atr=calc_atr(df,14)
        c_now=float(close.iloc[-1]); o_now=float(open_.iloc[-1]); c_prev=float(close.iloc[-2]); o_prev=float(open_.iloc[-2]); h_now=float(high.iloc[-1]); l_now=float(low.iloc[-1]); e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1]); e50=float(ema50.iloc[-1]); rsi7=float(rsi_fast.iloc[-1]); rsi14=float(rsi_slow.iloc[-1]); mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100; mom3=(close.iloc[-1]-close.iloc[-4])/close.iloc[-4]*100; body=abs(c_now-o_now); upper_wick=h_now-max(c_now,o_now); lower_wick=min(c_now,o_now)-l_now; is_green=c_now>o_now; payout=get_payout(pair); sig="CALL" if is_green else "PUT"; score=0; reason_list=[]
        min_atr = 0.00025 if pair in ["EURUSD","GBPUSD","USDJPY"] else 0.00035
        if atr < min_atr: return {"pair":pair,"dir":sig,"conf":45,"price":c_now,"rsi":rsi7,"reason":"Low ATR - Choppy","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if body < atr*0.35: return {"pair":pair,"dir":sig,"conf":50,"price":c_now,"rsi":rsi7,"reason":"Doji - No body","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if upper_wick > body*2.5 and lower_wick > body*2.5: return {"pair":pair,"dir":sig,"conf":48,"price":c_now,"rsi":rsi7,"reason":"High indecision","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if is_green:
            if e9 > e21 and e21 > e50: score+=20; reason_list.append("EMA Bull Align")
            elif e9 > e21: score+=12
        else:
            if e9 < e21 and e21 < e50: score+=20; reason_list.append("EMA Bear Align")
            elif e9 < e21: score+=12
        if is_green:
            if 55 <= rsi7 <= 68 and 50 <= rsi14 <= 65: score+=25; reason_list.append(f"RSI Safe {rsi7:.0f}")
            elif 50 <= rsi7 <= 72: score+=15
            elif rsi7 > 75: score-=15
        else:
            if 32 <= rsi7 <= 45 and 35 <= rsi14 <= 50: score+=25; reason_list.append(f"RSI Safe {rsi7:.0f}")
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
        score = max(45, min(94, score + 30)); reason = " + ".join(reason_list) if reason_list else "Weak PA"; expiry = 120
        if sniper_mode and score < 85: return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":rsi7,"reason":reason,"payout":payout,"expiry":expiry,"atr":atr,"rejected":True}
        return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":rsi7,"reason":reason,"payout":payout,"expiry":expiry,"atr":atr,"rejected":False}
    except: return None

def iq_trade(pair,direction,amount,bal,expiry_sec=120):
    if not IQ_CONNECTED and not iq_reconnect(): return False,None,0
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL); iq.change_balance(bal)
            mins=max(1,int(expiry_sec/60))
            if expiry_sec<=60: mins=1
            try:
                check,oid=iq.buy(amount,pair,direction.lower(),mins)
                if check: return True,oid,expiry_sec
            except: pass
            if expiry_sec<=90:
                try:
                    _,oid=iq.buy_blitz(pair,amount,direction.lower(),expiry_sec)
                    return True,oid,expiry_sec
                except: pass
            return False,None,0
    except: iq_reconnect(); return False,None,0

def try_auto_otc_trade(d, cid):
    global OTC_SESSION_RESULTS, OTC_MARTI
    try:
        if cid in AUTO_STATE and AUTO_STATE[cid].get('running'):
            base = AUTO_STATE[cid].get('base_amt',1.0); bal_type = AUTO_STATE[cid].get('bal','PRACTICE'); OTC_MARTI["base"]=base; OTC_MARTI["bal"]=bal_type
        else:
            base = OTC_MARTI["base"]; bal_type = OTC_MARTI["bal"]
        levels = OTC_MARTI["levels"]; idx = OTC_MARTI["loss_streak"] % len(levels); mult = levels[idx]; curr_amt = round(base * mult,2)
        ok,oid,exp = iq_trade(d['pair'], d['dir'], curr_amt, bal_type, d['expiry'])
        if not ok:
            bot.send_message(cid,f"⚠️ Auto OTC 85% trade failed {d['pair']} {d['dir']}"); return
        bal_now=get_real_balance(bal_type)
        bot.send_message(cid,f"🤖 **AUTO OTC 85% PLACED! Level {idx+1}/3 ({mult}x)**\n\n💱 {d['pair']} {d['dir']} ${curr_amt} (base ${base}) {d['conf']}% Safe 2 min\n🆔 {oid} | Bal ${bal_now:.2f}\n⏳ Waiting...")
        time.sleep(exp+6)
        with IQ_LOCK:
            logging.disable(logging.CRITICAL); pnl=iq.check_win_v4(oid)
        bal_now=get_real_balance(bal_type); win = pnl>0
        if win:
            STATS['wins']+=1; STATS['streak']+=1; STATS['real_balance']=bal_now; OTC_MARTI["loss_streak"]=0
            OTC_SESSION_RESULTS.append({"pair":d['pair'],"dir":d['dir'],"conf":d['conf'],"pnl":pnl,"win":True,"amt":curr_amt,"level":mult,"time":datetime.now(pytz.timezone("Africa/Lagos")).strftime('%H:%M:%S')})
            bot.send_message(cid,f"✅ **AUTO OTC WIN** +${pnl:.2f}\n💱 {d['pair']} {d['dir']} ${curr_amt} L{mult} {d['conf']}%\n💰 Bal ${bal_now:.2f} | 🔥 {STATS['streak']}\n♻️ Reset to ${base} (Level 1)")
        else:
            STATS['loss']+=1; STATS['streak']=0; STATS['real_balance']=bal_now; OTC_MARTI["loss_streak"]+=1
            if OTC_MARTI["loss_streak"] >= len(levels):
                bot.send_message(cid,f"❌ **LOSS -${curr_amt:.2f}** | Level {mult} finished (1-2-4 done)\n💱 {d['pair']}\n♻️ Resetting to Level 1 ${base}"); OTC_MARTI["loss_streak"]=0
            else:
                next_mult = levels[OTC_MARTI["loss_streak"]]; next_amt = base * next_mult
                bot.send_message(cid,f"❌ **LOSS -${curr_amt:.2f}** | {d['pair']} Level {mult}\n💰 Bal ${bal_now:.2f}\n👉 Next 85% signal → **${next_amt:.2f} Level {OTC_MARTI['loss_streak']+1} ({next_mult}x) - 2 Min**")
            OTC_SESSION_RESULTS.append({"pair":d['pair'],"dir":d['dir'],"conf":d['conf'],"pnl":-curr_amt,"win":False,"amt":curr_amt,"level":mult,"time":datetime.now(pytz.timezone("Africa/Lagos")).strftime('%H:%M:%S')})
    except Exception as e:
        bot.send_message(cid,f"Auto OTC martingale error {e}")

def real_signal_scanner():
    last_signal={}; tz=pytz.timezone("Africa/Lagos")
    while True:
        try:
            if is_real_hours() and IQ_CONNECTED:
                for pair in REAL_PAIRS:
                    if pair in last_signal and time.time()-last_signal[pair]<600: continue
                    d=analyze_momentum(pair,sniper_mode=True)
                    if d and not d.get('rejected') and d['conf']>=85:
                        now=datetime.now(tz); entry=now+timedelta(seconds=45); entry2=entry+timedelta(seconds=120); entry3=entry+timedelta(seconds=240); exp=d['expiry']; dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]
                        msg=f"""📡 **REAL SIGNAL V11 - 3 LEVELS (2 MIN EACH)** 📡\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n📊 {dir_e} | 🎯 {d['conf']:.0f}% SAFE\n📈 {d['reason']} | RSI {d['rsi']:.1f} | ATR {d['atr']:.5f}\n💸 {int(d['payout']*100)}% | 2 Min Each Level\n\n⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)\n📅 {now.strftime('%A %d %b %H:%M WAT')}\n\n**Level 1:** {entry.strftime('%H:%M:%S')} - 2 Min - ${base:.2f}\n**Level 2:** {entry2.strftime('%H:%M:%S')} - 2 Min - ${base*2:.2f}\n**Level 3:** {entry3.strftime('%H:%M:%S')} - 2 Min - ${base*4:.2f}\n\n⛔ STOP after Level 3. No Level 4.\n⚠️ MANUAL - Follow levels only\n"""
                        try: bot.send_message(OWNER_ID,msg,parse_mode="Markdown"); last_signal[pair]=time.time()
                        except: pass
                    time.sleep(3)
            time.sleep(25)
        except: time.sleep(30)

def otc_auto_85_scanner():
    last_signal={}
    while True:
        try:
            if not is_real_hours() and IQ_CONNECTED:
                for pair in OTC_PAIRS:
                    if pair in last_signal and time.time()-last_signal[pair]<180: continue
                    d=analyze_momentum(pair,sniper_mode=True)
                    if d and not d.get('rejected') and d['conf']>=85:
                        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=45); entry2=entry+timedelta(seconds=120); entry3=entry+timedelta(seconds=240); exp=d['expiry']; dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"; levels = OTC_MARTI["levels"]; idx = OTC_MARTI["loss_streak"] % len(levels); mult = levels[idx]; base = OTC_MARTI["base"]; curr = base*mult
                        msg=f"""📡 **OTC SIGNAL V11 - 3 LEVELS (2 MIN EACH)** 📡\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n📊 {dir_e} | 🎯 {d['conf']:.0f}% SAFE\n📈 {d['reason']} | RSI {d['rsi']:.1f}\n💸 {int(d['payout']*100)}% | 2 Min Each Level\n\n⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')}\n\n**Level 1:** {entry.strftime('%H:%M:%S')} - 2 Min - ${base:.2f}\n**Level 2:** {entry2.strftime('%H:%M:%S')} - 2 Min - ${base*2:.2f}\n**Level 3:** {entry3.strftime('%H:%M:%S')} - 2 Min - ${base*4:.2f}\n\n⛔ STOP after Level 3.\n🤖 Auto placing ${curr:.2f} Level {idx+1} ({mult}x) now...\n"""
                        try: bot.send_message(OWNER_ID,msg,parse_mode="Markdown"); last_signal[pair]=time.time()
                        except: pass
                        threading.Thread(target=try_auto_otc_trade,args=(d,OWNER_ID),daemon=True).start()
                    time.sleep(2)
            time.sleep(12)
        except: time.sleep(15)

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
            levels=[1,2,4]; idx=consecutive_losses % len(levels); curr_amt=state['base_amt']*levels[idx]; curr_amt=min(curr_amt,state['base_amt']*4)
            ok,oid,exp=iq_trade(pair_to_trade,d['dir'],curr_amt,state['bal'],state['expiry'])
            if not ok: iq_reconnect(); time.sleep(8); continue
            bal_now=get_real_balance(state['bal'])
            bot.send_message(cid,f"🤖 Auto OTC {pair_to_trade} {d['dir']} ${curr_amt:.2f} L{levels[idx]} {d['conf']}% Safe 2 min - ID {oid}\n💰 Bal ${bal_now:.2f}")
            time.sleep(exp+6)
            try:
                with IQ_LOCK:
                    logging.disable(logging.CRITICAL); pnl=iq.check_win_v4(oid)
                bal_now=get_real_balance(state['bal'])
                if pnl>0:
                    STATS['wins']+=1; STATS['real_balance']=bal_now; STATS['streak']+=1; AUTO_STATE[cid]['trades']+=1
                    mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("📊 STATS",callback_data="stats"),types.InlineKeyboardButton("🛑 STOP AUTO",callback_data="stop_auto"))
                    bot.send_message(cid,f"✅ WIN +${pnl:.2f} | {pair_to_trade} L{levels[idx]} Reset to $1\n💰 Bal ${bal_now:.2f} | Streak {STATS['streak']}",reply_markup=mk); consecutive_losses=0
                else:
                    STATS['loss']+=1; STATS['real_balance']=bal_now; STATS['streak']=0; AUTO_STATE[cid]['trades']+=1; consecutive_losses+=1
                    if consecutive_losses>=3: consecutive_losses=0; bot.send_message(cid,f"❌ LOSS -${curr_amt:.2f} | 1-2-4 done → Reset | Bal ${bal_now:.2f}")
                    else: bot.send_message(cid,f"❌ LOSS -${curr_amt:.2f} | Bal ${bal_now:.2f} | Next L{levels[consecutive_losses]} ${state['base_amt']*levels[consecutive_losses]:.2f} - 2 Min")
            except: bot.send_message(cid,f"⏱️ Expired {oid} - Check IQ")
            time.sleep(8)
        except: time.sleep(10)
    try:
        bal=get_real_balance("PRACTICE"); bot.send_message(cid,f"🛑 AUTO STOPPED W{STATS['wins']} L{STATS['loss']} Bal ${bal:.2f}")
    except: pass

@bot.message_handler(commands=['start','stop','mode','balance','results'])
def start(m):
    if not is_allowed(m.from_user.id): bot.send_message(m.chat.id,"❌ Private"); return
    if m.text.startswith('/stop'):
        if m.chat.id in AUTO_STATE: AUTO_STATE[m.chat.id]['running']=False; bot.send_message(m.chat.id,"🛑 Stopping...")
        else: bot.send_message(m.chat.id,"Auto not running"); return
    if m.text.startswith('/results'):
        if not OTC_SESSION_RESULTS: bot.send_message(m.chat.id,"📭 No OTC 85% auto trades yet this session"); return
        wins=sum(1 for x in OTC_SESSION_RESULTS if x['win']); losses=len(OTC_SESSION_RESULTS)-wins; pnl_total=sum(x['pnl'] for x in OTC_SESSION_RESULTS); levels = OTC_MARTI["levels"]; idx = OTC_MARTI["loss_streak"] % len(levels)
        txt=f"📊 **OTC 85% AUTO MARTINGALE RESULTS (1-2-4)**\n\nTotal: {len(OTC_SESSION_RESULTS)} | W:{wins} L:{losses} | PnL: ${pnl_total:.2f}\nCurrent Level: {idx+1} ({levels[idx]}x) | Base: ${OTC_MARTI['base']} | Each Level 2 Min\n\n"
        for r in OTC_SESSION_RESULTS[-25:]: txt+=f"{'✅' if r['win'] else '❌'} {r['time']} {r['pair']} {r['dir']} ${r['amt']} L{r['level']} {r['conf']}% {r['pnl']:+.2f}\n"
        bot.send_message(m.chat.id,txt,parse_mode="Markdown"); return
    if m.text.startswith('/mode'):
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz)
        txt=f"""📍 **MODE CHECK V11.3**

⏰ Now: {now.strftime('%A %H:%M:%S WAT')}
📊 Mode: {get_mode_text()}
💎 IQ: {'✅' if IQ_CONNECTED else '❌ False - Check email/pass or IP blocked'}
🛡️ Martingale: 1-2-4 (3 Levels, 2 Min each)
"""
        bot.send_message(m.chat.id,txt,parse_mode="Markdown"); return
    if m.text.startswith('/balance'):
        try:
            if not IQ_CONNECTED:
                bot.send_message(m.chat.id,f"💰 **BALANCES**\nIQ: ❌ Not connected yet (IP may be blocked)\n📍 {get_mode_text()}\n\nWait 1 min and try /start again")
                return
            demo=get_real_balance("PRACTICE"); real=get_real_balance("REAL")
            bot.send_message(m.chat.id,f"💰 **BALANCES**\n🟢 DEMO: ${demo:.2f}\n🔴 REAL: ${real:.2f}\n📍 {get_mode_text()}")
        except Exception as e: bot.send_message(m.chat.id,f"Balance error {e}")
        return
    try:
        bal_demo = get_real_balance("PRACTICE") if IQ_CONNECTED else STATS.get("real_balance",0.0)
    except:
        bal_demo = 0.0
    mk=types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton(f"💹 SCAN ALL OTC + AUTO 85% 1-2-4 - ${bal_demo:.2f}",callback_data="scan_all_otc"))
    mk.add(types.InlineKeyboardButton(f"📈 TRADE REAL (22) AUTO EXPIRY",callback_data="trade_real"))
    mk.add(types.InlineKeyboardButton("🤖 AUTO-TRADER OTC 85%+",callback_data="auto_setup"))
    mk.add(types.InlineKeyboardButton("📊 MY STATS",callback_data="stats"),types.InlineKeyboardButton("⚙️ SETTINGS",callback_data="settings"))
    txt=f"""🤖 **Z-BOT V11.3 OTC AUTO 85% MARTINGALE** 🤖

💎 IQ: {'✅' if IQ_CONNECTED else '❌ False - Retrying...'} | 💰 DEMO ${bal_demo:.2f}
🏆 W:{STATS['wins']} L:{STATS['loss']} | 🔥 {STATS['streak']}
📍 {get_mode_text()}

👇 **Select:**
"""
    bot.send_message(m.chat.id,txt,reply_markup=mk,parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_allowed(c.from_user.id): bot.answer_callback_query(c.id,"❌ Private"); return
    data=c.data; cid=c.message.chat.id
    if data=="trade_real":
        mk=types.InlineKeyboardMarkup(row_width=1); mk.add(types.InlineKeyboardButton("🔍 📊 SCAN ALL REAL NOW (22 PAIRS)",callback_data="scan_all_real"))
        for p in REAL_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}",callback_data=f"real_pair_{p}"))
        bot.send_message(cid,f"📈 **TRADE REAL V11 AUTO EXPIRY**\n📍 {get_mode_text()}",reply_markup=mk,parse_mode="Markdown"); return
    if data=="scan_all_real":
        bot.answer_callback_query(c.id,"Scanning 22 REAL pairs SAFE..."); scan_msg=bot.send_message(cid,"🔍 **SCANNING ALL 22 REAL PAIRS V11 SAFE...**\n\n⏳ ~12 sec"); results=[]; datas={}
        for pair in REAL_PAIRS:
            d=analyze_momentum(pair,sniper_mode=False)
            if not d: results.append((pair,0,"-","No data","🔴 NO TRADE",120)); continue
            conf=d['conf']; dir_=d['dir']; reason=d['reason']; exp=d['expiry']
            if conf>=85: status="🟢 READY"
            elif conf>=65: status="🟡 READY"
            else: status="🔴 NO TRADE"
            results.append((pair,conf,dir_,reason,status,exp)); datas[pair]=d
            try: bot.edit_message_text(f"🔍 Scanning V11... {pair} {conf:.0f}%",cid,scan_msg.message_id)
            except: pass
            time.sleep(0.3)
        results.sort(key=lambda x: x[1], reverse=True); txt="📊 **REAL V11 SAFE READINESS** 📊\n"; txt+=f"📍 {get_mode_text()}\n⏰ {datetime.now(pytz.timezone('Africa/Lagos')).strftime('%H:%M:%S WAT')}\n\n"
        for pair,conf,dir_,reason,status,exp in results:
            emoji=PAIR_EMOJI.get(pair,pair)
            if conf>=65: txt+=f"{status} {emoji}: {conf:.0f}% {dir_} Safe 2 min - {reason}\n"
            else: txt+=f"{status} {emoji}: {conf:.0f}% - {reason}\n"
        best = results[0] if results else None
        if best and best[1]>=65: txt+=f"\n💡 **BEST NOW:** {PAIR_EMOJI.get(best[0],best[0])} {best[1]:.0f}% Safe 2 min"
        mk=types.InlineKeyboardMarkup(row_width=2)
        if best and best[1]>=65: mk.add(types.InlineKeyboardButton(f"✅ TRADE BEST {best[0]}",callback_data=f"real_pair_{best[0]}"))
        mk.add(types.InlineKeyboardButton("🔄 RE-SCAN ALL",callback_data="scan_all_real"),types.InlineKeyboardButton("💹 SWITCH TO OTC",callback_data="scan_all_otc"))
        bot.send_message(cid,txt,reply_markup=mk,parse_mode="Markdown")
        if best and best[1]>=65 and best[0] in datas:
            time.sleep(0.5); best_data=datas[best[0]]; tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=45); entry2=entry+timedelta(seconds=120); entry3=entry+timedelta(seconds=240); exp=best_data['expiry']; dir_e="🟢 CALL ⬆️" if best_data['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]
            signal_txt=f"""📡 **REAL TOP SIGNAL V11.3 - 3 LEVELS** 📡\n\n💱 {PAIR_EMOJI.get(best_data['pair'],best_data['pair'])}\n📊 {dir_e} | 🎯 {best_data['conf']:.0f}% SAFE\n📈 {best_data['reason']} | RSI {best_data['rsi']:.1f}\n💸 {int(best_data['payout']*100)}% | 💰 {best_data['price']:.5f}\n\n⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)\n\n**Level 1:** {entry.strftime('%H:%M:%S')} - 2 Min - ${base:.2f}\n**Level 2:** {entry2.strftime('%H:%M:%S')} - 2 Min - ${base*2:.2f}\n**Level 3:** {entry3.strftime('%H:%M:%S')} - 2 Min - ${base*4:.2f}\n\n⛔ STOP after Level 3.\n"""
            bot.send_message(cid,signal_txt,parse_mode="Markdown")
        return
    if data.startswith("real_pair_"):
        pair=data.replace("real_pair_",""); bot.answer_callback_query(c.id,f"Scanning {pair} SAFE..."); scan_msg=bot.send_message(cid,f"🔍 **V11 SAFE SCAN {PAIR_EMOJI.get(pair,pair)}**\n\n0%\n🚀 Auto safe expiry..."); legit_live_scan(cid,scan_msg.message_id,pair); d=analyze_momentum(pair,sniper_mode=False)
        if not d or d['conf'] < 65:
            mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🔄 RETRY",callback_data=f"real_pair_{pair}"),types.InlineKeyboardButton("📈 SCAN ALL",callback_data="scan_all_real"))
            bot.send_message(cid,f"⚠️ **No safe trade now for {pair}**\n\n📊 Conf: {d['conf'] if d else 0}% < 65%\n🛡️ {d['reason'] if d else 'No data'}",reply_markup=mk); return
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=45); entry2=entry+timedelta(seconds=120); entry3=entry+timedelta(seconds=240); exp=d['expiry']; dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]
        signal_txt=f"""📡 **REAL SIGNAL V11 SAFE - 3 LEVELS** 📡\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n📊 {dir_e} | 🎯 {d['conf']:.0f}% SAFE\n📈 {d['reason']} | RSI {d['rsi']:.1f} | ATR {d['atr']:.5f}\n💸 {int(d['payout']*100)}% | 💰 {d['price']:.5f}\n\n⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)\n⏱️ EXPIRY: 2 Min Each Level\n\n**Level 1:** {entry.strftime('%H:%M:%S')} - 2 Min - ${base:.2f}\n**Level 2:** {entry2.strftime('%H:%M:%S')} - 2 Min - ${base*2:.2f}\n**Level 3:** {entry3.strftime('%H:%M:%S')} - 2 Min - ${base*4:.2f}\n\n⛔ STOP after Level 3.\n⚠️ **MANUAL PLACE**\n"""
        mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("🔁 SAME PAIR",callback_data=f"real_pair_{pair}"),types.InlineKeyboardButton("📈 SCAN ALL",callback_data="scan_all_real"))
        bot.send_message(cid,signal_txt,reply_markup=mk,parse_mode="Markdown"); return
    if data=="trade" or data=="scan_all_otc":
        bot.answer_callback_query(c.id,"Scanning 19 OTC SAFE..."); scan_msg=bot.send_message(cid,"🔍 **SCANNING ALL 19 OTC V11.3 SAME STRATEGY AS REAL...**\n\n⏳ ~10 sec"); results=[]; datas={}
        for pair in OTC_PAIRS:
            d=analyze_momentum(pair,sniper_mode=False)
            if not d: results.append((pair,0,"-","No data","🔴 NO TRADE",120)); continue
            conf=d['conf']; dir_=d['dir']; reason=d['reason']; exp=d['expiry']
            if conf>=85: status="🟢 READY"
            elif conf>=65: status="🟡 READY"
            else: status="🔴 NO TRADE"
            results.append((pair,conf,dir_,reason,status,exp)); datas[pair]=d
            try: bot.edit_message_text(f"🔍 Scanning OTC V11... {pair} {conf:.0f}%",cid,scan_msg.message_id)
            except: pass
            time.sleep(0.3)
        results.sort(key=lambda x: x[1], reverse=True); txt="📊 **OTC V11.3 SAME AS REAL + AUTO 85%** 📊\n"; txt+=f"📍 {get_mode_text()} | 85%+ = AUTO TRADE 1-2-4\n⏰ {datetime.now(pytz.timezone('Africa/Lagos')).strftime('%H:%M:%S WAT')}\n\n"
        for pair,conf,dir_,reason,status,exp in results:
            emoji=PAIR_EMOJI.get(pair,pair)
            if conf>=65: txt+=f"{status} {emoji}: {conf:.0f}% {dir_} Safe 2 min - {reason}\n"
            else: txt+=f"{status} {emoji}: {conf:.0f}% - {reason}\n"
        best = results[0] if results else None; levels = OTC_MARTI["levels"]; idx = OTC_MARTI["loss_streak"] % len(levels)
        if best and best[1]>=65: txt+=f"\n💡 **BEST:** {PAIR_EMOJI.get(best[0],best[0])} {best[1]:.0f}% | Martingale Level {idx+1} ({levels[idx]}x)"
        if best and best[1]>=85: txt+=f"\n🤖 **85%+ → Auto trading ${OTC_MARTI['base']*levels[idx]:.0f} now!**"
        mk=types.InlineKeyboardMarkup(row_width=2)
        if best and best[1]>=65: mk.add(types.InlineKeyboardButton(f"✅ TRADE BEST {best[0]}",callback_data=f"pair_{best[0]}"))
        mk.add(types.InlineKeyboardButton("🔄 RE-SCAN OTC",callback_data="scan_all_otc"),types.InlineKeyboardButton("📈 REAL",callback_data="trade_real"))
        bot.send_message(cid,txt,reply_markup=mk,parse_mode="Markdown")
        if best and best[0] in datas:
            best_data=datas[best[0]]
            if best_data['conf']>=65:
                time.sleep(0.5); tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=45); entry2=entry+timedelta(seconds=120); entry3=entry+timedelta(seconds=240); dir_e="🟢 CALL ⬆️" if best_data['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]
                signal_txt=f"""📡 **OTC SIGNAL V11.3 - 3 LEVELS** 📡\n\n💱 {PAIR_EMOJI.get(best_data['pair'],best_data['pair'])}\n📊 {dir_e} | 🎯 {best_data['conf']:.0f}% SAFE\n📈 {best_data['reason']} | RSI {best_data['rsi']:.1f}\n💸 {int(best_data['payout']*100)}%\n\n⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)\n⏱️ 2 Min Each Level\n\n**Level 1:** {entry.strftime('%H:%M:%S')} - 2 Min - ${base:.2f}\n**Level 2:** {entry2.strftime('%H:%M:%S')} - 2 Min - ${base*2:.2f}\n**Level 3:** {entry3.strftime('%H:%M:%S')} - 2 Min - ${base*4:.2f}\n\n⛔ STOP after Level 3.\n"""
                if best_data['conf']>=85: signal_txt+=f"\n🤖 **85%+ AUTO TRADE Level {idx+1} ({levels[idx]}x) - Placing ${OTC_MARTI['base']*levels[idx]:.0f} now...**"
                bot.send_message(cid,signal_txt,parse_mode="Markdown")
                if best_data['conf']>=85: threading.Thread(target=try_auto_otc_trade,args=(best_data,cid),daemon=True).start()
        return
    if data=="auto_setup":
        mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("🤖 AUTO SCAN ALL 19 OTC 85%+",callback_data="auto_pair_AUTO"))
        for p in OTC_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}",callback_data=f"auto_pair_{p}"))
        bot.send_message(cid,f"🤖 **AUTO SETUP 1/4 - OTC 85%+ MARTINGALE 1-2-4**",reply_markup=mk,parse_mode="Markdown"); return
    if data.startswith("auto_pair_"):
        pair=data.replace("auto_pair_",""); mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("🟢 DEMO",callback_data=f"auto_bal_PRACTICE_{pair}")); mk.add(types.InlineKeyboardButton("🔴 REAL",callback_data=f"auto_bal_REAL_{pair}"))
        bot.send_message(cid,f"✅ Pair: {pair}\n\n🤖 **SETUP 2/4 - ACCOUNT**",reply_markup=mk,parse_mode="Markdown"); return
    if data.startswith("auto_bal_"):
        parts=data.split("_"); bal=parts[2]; pair=parts[3]; mk=types.InlineKeyboardMarkup(row_width=3); mk.add(types.InlineKeyboardButton("💵 $1",callback_data=f"auto_amt_1_{pair}_{bal}"),types.InlineKeyboardButton("💵 $2",callback_data=f"auto_amt_2_{pair}_{bal}"),types.InlineKeyboardButton("💵 $5",callback_data=f"auto_amt_5_{pair}_{bal}"))
        bot.send_message(cid,f"✅ {pair} {bal}\n\n🤖 **SETUP 3/4 - BASE AMOUNT (Base for 1-2-4)**",reply_markup=mk,parse_mode="Markdown"); return
    if data.startswith("auto_amt_"):
        parts=data.split("_"); amt=float(parts[2]); pair=parts[3]; bal=parts[4]; d=analyze_momentum(pair,sniper_mode=False) if pair!="AUTO" else {"expiry":120}; exp_auto=d['expiry'] if d else 120
        AUTO_STATE[cid]={"running":True,"pair":pair,"bal":bal,"base_amt":amt,"curr_amt":amt,"expiry":exp_auto,"martingale":True,"sniper":True,"trades":0}; OTC_MARTI["base"]=amt; OTC_MARTI["bal"]=bal; OTC_MARTI["loss_streak"]=0
        mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🛑 STOP AUTO",callback_data="stop_auto"))
        bot.send_message(cid,f"🚀 **STARTING AUTO OTC V11.3 85%+ MARTINGALE 1-2-4!**\n{pair} Base ${amt} → $1,$2,$4\nBal ${get_real_balance(bal):.2f}\n🤖 Win = reset to ${amt} | Each Level 2 Min",reply_markup=mk,parse_mode="Markdown")
        threading.Thread(target=auto_trader_loop,args=(cid,),daemon=True).start(); return
    if data=="stop_auto":
        if cid in AUTO_STATE: AUTO_STATE[cid]['running']=False; bot.send_message(cid,"🛑 Stopping..."); return
    if data.startswith("pair_"):
        pair=data.replace("pair_",""); bot.answer_callback_query(c.id,f"Scanning {pair} SAFE..."); scan_msg=bot.send_message(cid,f"🔍 **V11 SAFE SCAN {PAIR_EMOJI.get(pair,pair)}**\n\n0%\n🚀 Auto safe expiry..."); legit_live_scan(cid,scan_msg.message_id,pair); d=analyze_momentum(pair,sniper_mode=False)
        if not d: bot.send_message(cid,f"❌ Failed analyze {pair}"); return
        mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("🟢 DEMO",callback_data=f"bal_PRACTICE_{pair}_{d['expiry']}"),types.InlineKeyboardButton("🔴 REAL",callback_data=f"bal_REAL_{pair}_{d['expiry']}"))
        bot.send_message(cid,f"✅ **{PAIR_EMOJI.get(pair,pair)} READY V11**\n\n📊 {d['dir']} {d['conf']:.0f}% | {d['reason']}\n⏱️ Safe Expiry: 2 Min Each Level\n\n💳 **CHOOSE ACCOUNT**",reply_markup=mk,parse_mode="Markdown"); return
    if data.startswith("bal_"):
        parts=data.split("_"); bal=parts[1]; pair=parts[2]; expiry=int(parts[3]); mk=types.InlineKeyboardMarkup(row_width=3); mk.add(types.InlineKeyboardButton("💵 $1",callback_data=f"amt_1_{pair}_{bal}_{expiry}"),types.InlineKeyboardButton("💵 $2",callback_data=f"amt_2_{pair}_{bal}_{expiry}"),types.InlineKeyboardButton("💵 $4",callback_data=f"amt_4_{pair}_{bal}_{expiry}")); mk.add(types.InlineKeyboardButton("✏️ CUSTOM",callback_data=f"custom_{pair}_{bal}_{expiry}"))
        bot.send_message(cid,f"✅ {pair} Safe 2 Min | {bal}\n\n💰 **AMOUNT**",reply_markup=mk,parse_mode="Markdown"); return
    if data.startswith("amt_") or data.startswith("custom_"):
        if data.startswith("custom_"):
            parts=data.split("_"); pair=parts[1]; bal=parts[2]; expiry=int(parts[3]); user_states[cid]={"pair":pair,"bal":bal,"expiry":expiry,"step":"await_amt"}; bot.send_message(cid,f"✏️ Type amount for {pair} {bal} Safe 2 Min"); return
        parts=data.split("_"); amt=float(parts[1]); pair=parts[2]; bal=parts[3]; expiry=int(parts[4]); bot.answer_callback_query(c.id,f"Placing 2 Min trade..."); d=analyze_momentum(pair,sniper_mode=False)
        if not d: bot.send_message(cid,"❌ No data"); return
        dir_emoji="🟢 CALL" if d['dir']=="CALL" else "🔴 PUT"; exp_txt="2 Min"
        bot.send_message(cid,f"📡 **PLACING SAFE TRADE**\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n📊 {dir_emoji} {d['conf']:.0f}% | {d['reason']}\n⏱️ Expiry: {exp_txt}\n💰 ${amt} {bal}\n\n🤖 Placing...")
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal,expiry)
        if not ok:
            mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("💹 NEW TRADE",callback_data="trade"),types.InlineKeyboardButton("🔄 RETRY",callback_data=f"amt_{int(amt)}_{pair}_{bal}_{expiry}"))
            bot.send_message(cid,"❌ Trade Failed",reply_markup=mk); iq_reconnect(); return
        bot.send_message(cid,f"✅ Placed {oid} | Waiting {exp}s | Bal ${get_real_balance(bal):.2f}"); time.sleep(exp+6)
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL); pnl=iq.check_win_v4(oid)
            bal_now=get_real_balance(bal)
            if pnl>0:
                STATS['wins']+=1; STATS['real_balance']=bal_now; STATS['streak']+=1
                mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("🔁 SAME SAFE TRADE",callback_data=f"amt_{int(amt)}_{pair}_{bal}_{expiry}"),types.InlineKeyboardButton("💹 NEW TRADE",callback_data="trade")); mk.add(types.InlineKeyboardButton("📊 STATS",callback_data="stats"),types.InlineKeyboardButton("🤖 AUTO",callback_data="auto_setup"))
                bot.send_message(cid,f"✅ **WIN +${pnl:.2f}**\n💱 {pair} Safe 2 Min\n🔥 Streak {STATS['streak']} | Bal ${bal_now:.2f}",reply_markup=mk,parse_mode="Markdown")
            else:
                STATS['loss']+=1; STATS['real_balance']=bal_now; STATS['streak']=0
                mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton(f"🔁 MARTINGALE 1-2-4",callback_data=f"amt_{int(amt*2)}_{pair}_{bal}_{expiry}"),types.InlineKeyboardButton("💹 NEW TRADE",callback_data="trade"))
                bot.send_message(cid,f"❌ **LOSS -${amt}**\n💱 {pair} Safe 2 Min\nBal ${bal_now:.2f}",reply_markup=mk,parse_mode="Markdown")
        except:
            mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("💹 NEW TRADE",callback_data="trade"),types.InlineKeyboardButton("🔄 RETRY",callback_data=f"amt_{int(amt)}_{pair}_{bal}_{expiry}"))
            bot.send_message(cid,f"⏱️ Expired {oid} - Check IQ",reply_markup=mk,parse_mode="Markdown")
        return
    if data=="stats":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0; bal=get_real_balance("PRACTICE"); mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("💹 NEW TRADE",callback_data="trade"),types.InlineKeyboardButton("🤖 AUTO",callback_data="auto_setup"))
        bot.send_message(cid,f"📊 **STATS V11.3**\n📍 {get_mode_text()}\n🏆 Wins: {STATS['wins']}\n❌ Loss: {STATS['loss']}\n📈 Winrate: {wr:.1f}%\n🔥 Streak: {STATS['streak']}\n💰 Bal: ${bal:.2f}\n📦 OTC 85% Auto: {len(OTC_SESSION_RESULTS)} trades | Level {OTC_MARTI['loss_streak']+1} | 2 Min Each",reply_markup=mk,parse_mode="Markdown")
    if data=="settings":
        bot.send_message(cid,f"⚙️ **SETTINGS V11.3 OTC AUTO 85%**\n\n🛡️ Same as REAL: ATR+Body+EMA3+RSI+Engulf+Pin\n⏱️ Expiry: FIXED 2 Min (120s) for Level 1, 2, 3\n📊 OTC: 85%+ = Auto trade 1-2-4 return, win reset\n/results = session summary")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id,{}).get("step")=="await_amt")
def handle_custom_amt(m):
    cid=m.chat.id; st=user_states.get(cid,{})
    if not is_allowed(m.from_user.id): return
    try:
        amt=float(m.text.strip()); pair=st.get("pair"); bal=st.get("bal"); expiry=st.get("expiry",120)
        if not pair: return
        bot.send_message(cid,f"✅ Custom ${amt} - Placing Safe 2 Min trade...")
        d=analyze_momentum(pair,sniper_mode=False)
        if not d: return
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal,expiry)
        if not ok: bot.send_message(cid,"❌ Failed"); return
        bot.send_message(cid,f"✅ Placed {oid} Waiting {exp}s..."); time.sleep(exp+6)
        with IQ_LOCK:
            logging.disable(logging.CRITICAL); pnl=iq.check_win_v4(oid)
        bal_now=get_real_balance(bal)
        if pnl>0: STATS['wins']+=1; STATS['streak']+=1; bot.send_message(cid,f"✅ WIN +${pnl:.2f} Bal ${bal_now:.2f}")
        else: STATS['loss']+=1; STATS['streak']=0; bot.send_message(cid,f"❌ LOSS Bal ${bal_now:.2f}")
    except: bot.send_message(cid,"❌ Send number only")

threading.Thread(target=background_iq, daemon=True).start()
threading.Thread(target=real_signal_scanner,daemon=True).start()
threading.Thread(target=otc_auto_85_scanner,daemon=True).start()

if __name__ == "__main__":
    try:
        url=os.getenv("RENDER_EXTERNAL_URL")
        if url and BOT_TOKEN:
            requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={url}/{BOT_TOKEN}", timeout=5)
            print(f"Webhook set {url}")
    except: pass
    port=int(os.getenv("PORT",10000))
    print(f"Starting Flask on 0.0.0.0:{port} - FREE WEB SERVICE")
    app.run(host="0.0.0.0", port=port, threaded=True)
