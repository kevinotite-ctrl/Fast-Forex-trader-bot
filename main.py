import os, time, threading, warnings, logging, json
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
if not BOT_TOKEN: print("ERROR BOT_TOKEN missing")
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)
ENABLE_OTC = False

REAL_PAIRS = ["EURUSD","GBPUSD","USDJPY","EURGBP","AUDUSD","USDCAD","EURJPY","GBPJPY","USDCHF","AUDJPY","EURAUD","GBPCHF","EURCHF","NZDUSD","GBPAUD","EURCAD","AUDCAD","GBPCAD","NZDJPY","AUDNZD","CHFJPY","CADJPY"]
OTC_PAIRS = ["EURUSD-OTC","GBPUSD-OTC","USDJPY-OTC","AUDUSD-OTC","USDCAD-OTC","EURGBP-OTC","EURJPY-OTC","GBPJPY-OTC","AUDJPY-OTC","EURAUD-OTC","GBPAUD-OTC","NZDUSD-OTC","GBPCHF-OTC","EURCHF-OTC","USDCHF-OTC","AUDCAD-OTC","EURCAD-OTC","CADJPY-OTC","NZDJPY-OTC"]
PAIR_EMOJI = {"EURUSD":"🇪🇺 EUR/USD REAL","GBPUSD":"🇬🇧 GBP/USD REAL","USDJPY":"🇺🇸 USD/JPY REAL","EURGBP":"🇪🇺 EUR/GBP REAL","AUDUSD":"🇦🇺 AUD/USD REAL","USDCAD":"🇺🇸 USD/CAD REAL","EURJPY":"🇪🇺 EUR/JPY REAL","GBPJPY":"🇬🇧 GBP/JPY REAL","USDCHF":"🇺🇸 USD/CHF REAL","AUDJPY":"🇦🇺 AUD/JPY REAL","EURAUD":"🇪🇺 EUR/AUD REAL","GBPCHF":"🇬🇧 GBP/CHF REAL","EURCHF":"🇪🇺 EUR/CHF REAL","NZDUSD":"🇳🇿 NZD/USD REAL","GBPAUD":"🇬🇧 GBP/AUD REAL","EURCAD":"🇪🇺 EUR/CAD REAL","AUDCAD":"🇦🇺 AUD/CAD REAL","GBPCAD":"🇬🇧 GBP/CAD REAL","NZDJPY":"🇳🇿 NZD/JPY REAL","AUDNZD":"🇦🇺 AUD/NZD REAL","CHFJPY":"🇨🇭 CHF/JPY REAL","CADJPY":"🇨🇦 CAD/JPY REAL","EURUSD-OTC":"🇪🇺 EUR/USD OTC","GBPUSD-OTC":"🇬🇧 GBP/USD OTC","EURGBP-OTC":"🇪🇺 EUR/GBP OTC","USDJPY-OTC":"🇺🇸 USD/JPY OTC","GBPJPY-OTC":"🇬🇧 GBP/JPY OTC","AUDUSD-OTC":"🇦🇺 AUD/USD OTC","USDCHF-OTC":"🇺🇸 USD/CHF OTC","EURJPY-OTC":"🇪🇺 EUR/JPY OTC","AUDJPY-OTC":"🇦🇺 AUD/JPY OTC","EURAUD-OTC":"🇪🇺 EUR/AUD OTC","GBPAUD-OTC":"🇬🇧 GBP/AUD OTC","NZDUSD-OTC":"🇳🇿 NZD/USD OTC","GBPCHF-OTC":"🇬🇧 GBP/CHF OTC","EURCHF-OTC":"🇪🇺 EUR/CHF OTC","USDCAD-OTC":"🇺🇸 USD/CAD OTC","AUDCAD-OTC":"🇦🇺 AUD/CAD OTC","EURCAD-OTC":"🇪🇺 EUR/CAD OTC","CADJPY-OTC":"🇨🇦 CAD/JPY OTC","NZDJPY-OTC":"🇳🇿 NZD/JPY OTC"}

STATS = {"balance":0.0,"real_balance":0.0,"wins":0,"loss":0,"streak":0,"daily_trades":0,"daily_date":""}
user_states = {}; AUTO_STATE = {}; IQ_LOCK = threading.Lock()
IQ_CONNECTED=False; iq=None; PAYOUT_CACHE={}; PAYOUT_TIME=0
OTC_SESSION_RESULTS = []
OTC_MARTI = {"loss_streak":0, "base":1.0, "bal":"PRACTICE", "levels":[1,2,4,8]}
PULLBACK_STATE = {}
ACTIVE_SIGNAL = {"active": False, "pair": None, "dir": None, "conf":0, "rsi":0, "adx":0, "started": 0}
DAILY_SUMMARY_SENT = ""

# ===== AI BRAIN =====
PAIR_BRAIN = {}
def load_brain():
    global PAIR_BRAIN
    try:
        with open("brain.json","r") as f: PAIR_BRAIN = json.load(f)
    except: PAIR_BRAIN = {}
def save_brain():
    try:
        with open("brain.json","w") as f: json.dump(PAIR_BRAIN, f)
    except: pass
def get_pair_stats(pair):
    if pair not in PAIR_BRAIN: PAIR_BRAIN[pair] = {"wins":0,"loss":0,"history":[],"blocked_until":0,"score_boost":0}
    return PAIR_BRAIN[pair]
def get_pair_winrate(pair):
    s = get_pair_stats(pair); total = s["wins"] + s["loss"]
    if total < 3: return None
    return s["wins"] / total * 100
def is_pair_blocked(pair):
    s = get_pair_stats(pair); return time.time() < s["blocked_until"]
def record_brain(pair, won, conf, rsi, adx):
    s = get_pair_stats(pair)
    if won: s["wins"] += 1
    else: s["loss"] += 1
    s["history"].append({"win":won,"conf":conf,"rsi":rsi,"adx":adx,"time":time.time()})
    s["history"] = s["history"][-30:]
    wr = get_pair_winrate(pair); total = s["wins"] + s["loss"]
    if total >= 5:
        if wr < 40: s["blocked_until"] = time.time() + 7200; s["score_boost"] = -15
        elif wr < 50: s["score_boost"] = -8
        elif wr >= 65: s["score_boost"] = +8; s["blocked_until"] = 0
        elif wr >= 55: s["score_boost"] = +3
        else: s["score_boost"] = 0
    save_brain()
load_brain()

def is_signal_active(): return ACTIVE_SIGNAL["active"]
def start_signal(pair, dir_, conf=0, rsi=0, adx=0): ACTIVE_SIGNAL.update({"active":True,"pair":pair,"dir":dir_,"conf":conf,"rsi":rsi,"adx":adx,"started":time.time()})
def clear_signal(): ACTIVE_SIGNAL.update({"active":False,"pair":None,"dir":None,"conf":0,"rsi":0,"adx":0,"started":0})
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
def get_mode_text(): return "REAL SIGNAL (7AM-8PM)" if is_real_hours() else "OTC DISABLED - Waiting for REAL 7AM"
def can_trade_today():
    today = datetime.now(pytz.timezone("Africa/Lagos")).strftime("%Y-%m-%d")
    if STATS["daily_date"] != today: STATS["daily_date"] = today; STATS["daily_trades"] = 0
    return STATS["daily_trades"] < 30
def count_trade(): STATS["daily_trades"] += 1

@app.route("/")
def home(): return f"V14 BRAIN+SKIP RUNNING IQ:{IQ_CONNECTED} {datetime.now(pytz.timezone('Africa/Lagos')).strftime('%H:%M:%S')}"
@app.route(f"/{BOT_TOKEN}",methods=['POST'])
def wh():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode("utf-8"))]); return "ok"

def background_iq():
    global iq, IQ_CONNECTED
    time.sleep(3)
    for attempt in range(10):
        try:
            from iqoptionapi.stable_api import IQ_Option
            EMAIL=os.getenv("IQ_EMAIL"); PWD=os.getenv("IQ_PASS"); PROXY=os.getenv("PROXY_URL")
            if not EMAIL or not PWD: print("IQ_EMAIL/PASS missing"); return
            iq=IQ_Option(EMAIL,PWD)
            if PROXY:
                try:
                    pc = PROXY.replace("http://","").replace("https://","")
                    if "@" in pc:
                        up, hp = pc.split("@"); pu, pp = up.split(":"); ph, pt = hp.split(":"); iq.set_proxy(proxy_type="http", host=ph, port=int(pt), user=pu, password=pp)
                except: pass
            logging.disable(logging.CRITICAL); iq.connect(); IQ_CONNECTED=iq.check_connect()
            if IQ_CONNECTED:
                try: iq.change_balance("PRACTICE"); time.sleep(1); STATS["real_balance"]=iq.get_balance(); print(f"[IQ] SUCCESS ${STATS['real_balance']}")
                except: pass
                return
            time.sleep(8)
        except Exception as e: print(f"[IQ] Fail {e}"); time.sleep(10)
    IQ_CONNECTED=False

def iq_reconnect():
    global iq, IQ_CONNECTED
    try:
        from iqoptionapi.stable_api import IQ_Option
        logging.disable(logging.CRITICAL); iq=IQ_Option(os.getenv("IQ_EMAIL"),os.getenv("IQ_PASS")); PROXY=os.getenv("PROXY_URL")
        if PROXY:
            try:
                pc = PROXY.replace("http://","").replace("https://","")
                if "@" in pc:
                    up, hp = pc.split("@"); pu, pp = up.split(":"); ph, pt = hp.split(":"); iq.set_proxy(proxy_type="http", host=ph, port=int(pt), user=pu, password=pp)
            except: pass
        iq.connect(); IQ_CONNECTED=iq.check_connect()
        if IQ_CONNECTED:
            try: STATS["real_balance"]=iq.get_balance()
            except: pass
        return IQ_CONNECTED
    except: IQ_CONNECTED=False; return False

def get_real_balance(bal_type="PRACTICE"):
    try:
        with IQ_LOCK: logging.disable(logging.CRITICAL); iq.change_balance(bal_type); return iq.get_balance()
    except: return 0.0
def get_payout(pair):
    global PAYOUT_CACHE, PAYOUT_TIME
    if time.time()-PAYOUT_TIME<60 and pair in PAYOUT_CACHE: return PAYOUT_CACHE[pair]
    try:
        logging.disable(logging.CRITICAL); all_p=iq.get_all_profit()
        if pair in all_p:
            for k in ['blitz','turbo','binary']:
                if k in all_p[pair]: PAYOUT_CACHE[pair]=float(all_p[pair][k]); PAYOUT_TIME=time.time(); return float(all_p[pair][k])
        return 0.85
    except: return PAYOUT_CACHE.get(pair,0.85)
def get_candles(pair):
    if not IQ_CONNECTED and not iq_reconnect(): return None
    if pair not in REAL_PAIRS and pair not in OTC_PAIRS: return None
    for _ in range(3):
        try:
            logging.disable(logging.CRITICAL); c=iq.get_candles(pair,60,100,time.time())
            if c and len(c)>50: return pd.DataFrame(sorted(c,key=lambda x:x['from']))
            c2=iq.get_candles(pair,300,50,time.time())
            if c2 and len(c2)>20: return pd.DataFrame(sorted(c2,key=lambda x:x['from']))
            time.sleep(0.4)
        except: time.sleep(0.4)
    return None
def calc_rsi(closes, period=7):
    delta=closes.diff(); gain=delta.where(delta>0,0); loss=-delta.where(delta<0,0)
    avg_gain=gain.ewm(alpha=1/period, adjust=False).mean(); avg_loss=loss.ewm(alpha=1/period, adjust=False).mean()
    rs=avg_gain/avg_loss; return 100-(100/(1+rs))
def calc_atr(df, period=14):
    try:
        high=df['max']; low=df['min']; close=df['close']; tr1=high-low; tr2=(high-close.shift()).abs(); tr3=(low-close.shift()).abs(); tr=pd.concat([tr1,tr2,tr3],axis=1).max(axis=1); return tr.rolling(period).mean().iloc[-1]
    except: return 0.0005
def legit_live_scan(cid, mid, pair):
    steps = [(0,"🚀 V14 Brain Init...",0.15),(20,f"🔌 Checking {pair}...",0.2),(40,"📊 ADX + ATR + Brain...",0.25),(60,"📈 EMA + MACD + 5M Trend...",0.2),(80,"💹 RSI + Stochastic + BB...",0.2),(100,"🔒 SNIPER LOCKED!",0.3)]
    last_pct=-1
    for pct, text, delay in steps:
        if pct==last_pct: time.sleep(delay); continue
        last_pct=pct; filled=int(pct//5); bar="█"*filled+"░"*(20-filled); color="🟥" if pct<40 else "🟨" if pct<80 else "🟩" if pct<100 else "💎"
        txt=f"""{color} **Z-BOT V14 BRAIN** {color}\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n💎 IQ: {'✅' if IQ_CONNECTED else '❌'}\n\n{bar} {pct}%\n\n🔍 {text}\n⏳ V14"""
        try: bot.edit_message_text(txt,cid,mid,parse_mode="Markdown")
        except: pass
        time.sleep(delay)
def calc_adx_v12(df, period=14):
    try:
        high=df['max']; low=df['min']; close=df['close']
        tr1=high-low; tr2=(high-close.shift()).abs(); tr3=(low-close.shift()).abs()
        tr=pd.concat([tr1,tr2,tr3],axis=1).max(axis=1); atr=tr.rolling(period).mean()
        up=high-high.shift(); down=low.shift()-low
        plus_dm=((up>down)&(up>0))*up; minus_dm=((down>up)&(down>0))*down
        plus_di=100*(plus_dm.rolling(period).mean()/atr); minus_di=100*(minus_dm.rolling(period).mean()/atr)
        dx=100*((plus_di-minus_di).abs()/(plus_di+minus_di)); adx=dx.rolling(period).mean().iloc[-1]
        return float(adx), float(plus_di.iloc[-1]), float(minus_di.iloc[-1])
    except: return 0, 0, 0

def analyze_sniper_v12(pair, sniper_mode=False):
    df = get_candles(pair)
    if df is None: return None
    try:
        df5 = None
        try:
            logging.disable(logging.CRITICAL); c5 = iq.get_candles(pair, 300, 50, time.time())
            if c5 and len(c5) > 20: df5 = pd.DataFrame(sorted(c5, key=lambda x: x['from']))
        except: df5 = None
        close=df['close']; open_=df['open']; high=df['max']; low=df['min']
        ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean(); ema50=close.ewm(50).mean()
        rsi7=calc_rsi(close,7); rsi14=calc_rsi(close,14)
        atr=calc_atr(df,14); adx, pdi, mdi = calc_adx_v12(df)
        ema12=close.ewm(12).mean(); ema26=close.ewm(26).mean(); macd=ema12-ema26; signal=macd.ewm(9).mean()
        macd_val=float(macd.iloc[-1]); sig_val=float(signal.iloc[-1])
        sma20=close.rolling(20).mean(); std20=close.rolling(20).std()
        upper=float((sma20+2*std20).iloc[-1]); lower=float((sma20-2*std20).iloc[-1])
        low14=low.rolling(14).min(); high14=high.rolling(14).max(); stoch=100*(close-low14)/(high14-low14); stoch_val=float(stoch.iloc[-1])
        c_now=float(close.iloc[-1]); o_now=float(open_.iloc[-1]); c_prev=float(close.iloc[-2]); o_prev=float(open_.iloc[-2])
        h_now=float(high.iloc[-1]); l_now=float(low.iloc[-1]); e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1]); e50=float(ema50.iloc[-1])
        r7=float(rsi7.iloc[-1]); r14=float(rsi14.iloc[-1]); mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100; mom3=(close.iloc[-1]-close.iloc[-4])/close.iloc[-4]*100
        body=abs(c_now-o_now); upper_wick=h_now-max(c_now,o_now); lower_wick=min(c_now,o_now)-l_now; is_green=c_now>o_now; payout=get_payout(pair); sig="CALL" if is_green else "PUT"
        if is_pair_blocked(pair): return {"pair":pair,"dir":sig,"conf":40,"price":c_now,"rsi":r7,"reason":f"🧠 BRAIN Blocked {pair}","payout":payout,"expiry":120,"atr":atr,"rejected":True}
        if adx < 25: return {"pair":pair,"dir":sig,"conf":42,"price":c_now,"rsi":r7,"reason":"Choppy - ADX Low","payout":payout,"expiry":120,"atr":atr,"rejected":True}
        if body < atr*0.30: return {"pair":pair,"dir":sig,"conf":48,"price":c_now,"rsi":r7,"reason":"Doji - No Body","payout":payout,"expiry":120,"atr":atr,"rejected":True}
        if payout < 0.80: return {"pair":pair,"dir":sig,"conf":52,"price":c_now,"rsi":r7,"reason":f"Low Payout {int(payout*100)}%","payout":payout,"expiry":120,"atr":atr,"rejected":True}
        score=30; reasons=[]
        if df5 is not None:
            c5=df5['close']; e9_5=c5.ewm(9).mean(); e21_5=c5.ewm(21).mean(); trend_5m = 1 if float(e9_5.iloc[-1]) > float(e21_5.iloc[-1]) else -1
            if (is_green and trend_5m==-1) or (not is_green and trend_5m==1): return {"pair":pair,"dir":sig,"conf":45,"price":c_now,"rsi":r7,"reason":"Against 5M Trend - REJECT","payout":payout,"expiry":120,"atr":atr,"rejected":True}
            else: score+=12; reasons.append("5M Trend Align")
        else: return {"pair":pair,"dir":sig,"conf":45,"price":c_now,"rsi":r7,"reason":"No 5M Data - REJECT","payout":payout,"expiry":120,"atr":atr,"rejected":True}
        if is_green:
            if e9>e21>e50: score+=18; reasons.append("EMA Bull Align")
            elif e9>e21: score+=10
            else: score-=8
        else:
            if e9<e21<e50: score+=18; reasons.append("EMA Bear Align")
            elif e9<e21: score+=10
            else: score-=8
        if adx >= 28: score+=12; reasons.append(f"ADX Strong {adx:.0f}")
        elif adx >= 22: score+=7
        if is_green and pdi > mdi: score+=8
        elif not is_green and mdi > pdi: score+=8
        else: score-=10
        if is_green:
            if 52 <= r7 <= 65 and 48 <= r14 <= 62: score+=15; reasons.append(f"RSI Safe {r7:.0f}")
            elif r7 > 75 or r7 < 45: score-=12
            else: score+=6
        else:
            if 35 <= r7 <= 48 and 38 <= r14 <= 52: score+=15; reasons.append(f"RSI Safe {r7:.0f}")
            elif r7 < 25 or r7 > 55: score-=12
            else: score+=6
        if is_green and macd_val > sig_val: score+=10; reasons.append("MACD Bull")
        elif not is_green and macd_val < sig_val: score+=10; reasons.append("MACD Bear")
        else: score-=8
        if is_green:
            if mom1 > 0.03 and mom3 > 0.06: score+=12; reasons.append(f"Mom {mom1:.3f}%")
            elif mom1 > 0.01: score+=5
            elif mom1 < 0: score-=12
        else:
            if mom1 < -0.03 and mom3 < -0.06: score+=12; reasons.append(f"Mom {mom1:.3f}%")
            elif mom1 < -0.01: score+=5
            elif mom1 > 0: score-=12
        bull_eng = c_now > o_prev and o_now < c_prev and is_green and c_prev < o_prev
        bear_eng = c_now < o_prev and o_now > c_prev and not is_green and c_prev > o_prev
        pin_bull = lower_wick > body*1.8 and lower_wick > upper_wick*1.5 and is_green
        pin_bear = upper_wick > body*1.8 and upper_wick > lower_wick*1.5 and not is_green
        has_pattern = False
        if is_green:
            if bull_eng: score+=10; reasons.append("Bull Engulf"); has_pattern=True
            if pin_bull: score+=10; reasons.append("Pin Bull"); has_pattern=True
        else:
            if bear_eng: score+=10; reasons.append("Bear Engulf"); has_pattern=True
            if pin_bear: score+=10; reasons.append("Pin Bear"); has_pattern=True
        if is_green and stoch_val > 85: score-=12
        if not is_green and stoch_val < 15: score-=12
        if is_green and 50 < stoch_val < 80: score+=5
        if not is_green and 20 < stoch_val < 50: score+=5
        if is_green and c_now > upper: score-=10
        if not is_green and c_now < lower: score-=10
        if not has_pattern and score < 88: return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":"No Pattern - REJECT","payout":payout,"expiry":120,"atr":atr,"rejected":True}
        brain = get_pair_stats(pair); boost = brain.get("score_boost", 0); score += boost
        if boost != 0: reasons.append(f"🧠 Brain {boost:+d}")
        if boost <= -8 and sniper_mode and score < 92: return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":f"🧠 Weak pair {pair} needs 92%","payout":payout,"expiry":120,"atr":atr,"rejected":True}
        score = max(40, min(96, score)); reason = " + ".join(reasons) if reasons else "Weak PA"
        if sniper_mode and score < 88: return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":reason,"payout":payout,"expiry":120,"atr":atr,"rejected":True}
        return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":reason,"payout":payout,"expiry":120,"atr":atr,"rejected":False,"adx":adx}
    except Exception as e: print(f"V14 err {pair} {e}"); return None

def check_pullback_entry(pair, original_dir):
    df = get_candles(pair)
    if df is None: return None
    try:
        close = df['close']; ema9 = close.ewm(9).mean(); ema21 = close.ewm(21).mean()
        rsi7 = calc_rsi(close, 7); rsi14 = calc_rsi(close, 14)
        r7 = float(rsi7.iloc[-1]); r7_prev = float(rsi7.iloc[-2]); r14 = float(rsi14.iloc[-1])
        c_now = float(close.iloc[-1]); e9 = float(ema9.iloc[-1]); e21 = float(ema21.iloc[-1]); payout = get_payout(pair)
        near_ema = abs(c_now - e9) / c_now * 100 < 0.05 or abs(c_now - e21) / c_now * 100 < 0.05
        if not near_ema or payout < 0.80: return None
        if original_dir == "CALL":
            if 40 <= r7 <= 55 and 42 <= r14 <= 58 and r7 > r7_prev and c_now > e21:
                return {"pair":pair,"dir":"CALL","conf":88,"price":c_now,"rsi":r7,"reason":f"Pullback CALL | RSI7 {r7:.0f}↑ RSI14 {r14:.0f} at EMA","payout":payout,"expiry":120,"atr":0,"rejected":False}
        else:
            if 45 <= r7 <= 60 and 42 <= r14 <= 58 and r7 < r7_prev and c_now < e21:
                return {"pair":pair,"dir":"PUT","conf":88,"price":c_now,"rsi":r7,"reason":f"Pullback PUT | RSI7 {r7:.0f}↓ RSI14 {r14:.0f} at EMA","payout":payout,"expiry":120,"atr":0,"rejected":False}
        return None
    except: return None

def pullback_scanner_loop(cid, pair, original_dir):
    start = time.time(); PULLBACK_STATE[cid] = {"pair":pair,"dir":original_dir,"active":True}
    bot.send_message(cid, f"🔍 **Pullback Scan ON**\n\n💱 {pair} looking for {original_dir} pullback\n📊 Scanning every 10 sec...\n📍 RSI7 + RSI14 both safe + RSI turning + Price at EMA\n⏳ Timeout 5 min\n\nPress ✅ WIN / ❌ LOSS / ⏭️ SKIP")
    while PULLBACK_STATE.get(cid, {}).get("active") and time.time() - start < 300:
        if not can_trade_today(): bot.send_message(cid, "⛔ Max 30 trades reached today. Pullback scan stopped."); PULLBACK_STATE[cid]["active"] = False; return
        d = check_pullback_entry(pair, original_dir)
        if d:
            levels = OTC_MARTI["levels"]; idx = OTC_MARTI["loss_streak"]; mult = levels[idx]; amt = OTC_MARTI["base"] * mult
            names = ["Real Entry","Martingale 1","Martingale 2","Martingale 3"]; dir_e = "🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"
            mk = types.InlineKeyboardMarkup(row_width=2)
            mk.add(types.InlineKeyboardButton("✅ WIN", callback_data=f"manual_win_{pair}"), types.InlineKeyboardButton("❌ LOSS", callback_data=f"manual_loss_{pair}_{d['dir']}"))
            mk.add(types.InlineKeyboardButton("⏭️ SKIP THIS TRADE", callback_data=f"skip_{pair}"))
            bot.send_message(cid, f"🎯 **PULLBACK ENTRY FOUND!**\n\n💱 {pair}\n📊 {dir_e} | {d['reason']}\n💸 Payout {int(d['payout']*100)}%\n💰 Next: **{names[idx]} - ${amt:.2f} Level {idx+1}/4 ({mult}x)**\n⏱️ Enter NOW - 2 Min - MANUAL\n\nPress WIN/LOSS/SKIP after result:", reply_markup=mk, parse_mode="Markdown")
            PULLBACK_STATE[cid]["active"] = False; return
        time.sleep(10)
    PULLBACK_STATE[cid] = {"active":False}; bot.send_message(cid, "⏱️ Pullback scan timeout (5 min) - No safe entry. Waiting for next signal.")

def daily_summary_loop():
    global DAILY_SUMMARY_SENT
    tz = pytz.timezone("Africa/Lagos")
    while True:
        try:
            now = datetime.now(tz); today_str = now.strftime("%Y-%m-%d")
            if now.hour == 20 and now.minute < 5 and DAILY_SUMMARY_SENT != today_str:
                DAILY_SUMMARY_SENT = today_str; total = STATS['wins'] + STATS['loss']; wr = (STATS['wins']/total*100) if total else 0
                best_pair=""; best_wr=0; bad_pair=""; bad_wr=100
                for pair, s in PAIR_BRAIN.items():
                    t = s["wins"] + s["loss"]
                    if t >= 3:
                        w = s["wins"]/t*100
                        if w > best_wr: best_wr=w; best_pair=f"{pair} {w:.0f}% (W{s['wins']} L{s['loss']})"
                        if w < bad_wr: bad_wr=w; bad_pair=f"{pair} {w:.0f}% (W{s['wins']} L{s['loss']})"
                msg = f"""📊 **DAILY SUMMARY - {today_str}** 📊

🕗 Trading closed for today (8PM)

🏆 Wins: {STATS['wins']}
❌ Losses: {STATS['loss']}
📈 Win Rate: {wr:.1f}%
📅 Total Trades Today: {STATS['daily_trades']}/30

🏆 **Best Pair:** {best_pair if best_pair else 'Not enough data yet'}
💀 **Worst Pair:** {bad_pair if bad_pair else 'None - all good'}

🧠 **Brain Status:**
Brain has learned from {len(PAIR_BRAIN)} pairs so far.
Bad pairs will be blocked tomorrow.

🌙 Bot will restart scanning tomorrow 7AM.
Rest well, don't chase losses.
"""
                try: bot.send_message(OWNER_ID, msg, parse_mode="Markdown")
                except: pass
            time.sleep(60)
        except: time.sleep(60)

def real_signal_scanner():
    last_signal={}; tz=pytz.timezone("Africa/Lagos")
    while True:
        try:
            if is_signal_active(): time.sleep(15); continue
            if is_real_hours() and IQ_CONNECTED:
                if not can_trade_today(): time.sleep(60); continue
                for pair in REAL_PAIRS:
                    if is_pair_blocked(pair): continue
                    if pair in last_signal and time.time()-last_signal[pair]<600: continue
                    d=analyze_sniper_v12(pair,sniper_mode=True)
                    if d and not d.get('rejected') and d['conf']>=88:
                        now=datetime.now(tz); entry=now+timedelta(seconds=45); dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]
                        mk = types.InlineKeyboardMarkup(row_width=2)
                        mk.add(types.InlineKeyboardButton("✅ WIN - Reset", callback_data=f"manual_win_{pair}"), types.InlineKeyboardButton("❌ LOSS - Pullback Scan", callback_data=f"manual_loss_{pair}_{d['dir']}"))
                        mk.add(types.InlineKeyboardButton("⏭️ SKIP THIS TRADE", callback_data=f"skip_{pair}"))
                        brain = get_pair_stats(pair); wr = get_pair_winrate(pair); wr_txt = f" | 🧠 Brain WR {wr:.0f}%" if wr is not None else ""
                        msg=f"""📡 **REAL SIGNAL V14 BRAIN - MANUAL** 📡

💱 {PAIR_EMOJI.get(pair,pair)}
📊 {dir_e} | 🎯 {d['conf']:.0f}% SNIPER{wr_txt}
📈 {d['reason']} | RSI {d['rsi']:.1f} | ATR {d['atr']:.5f}
💸 {int(d['payout']*100)}% | 2 Min
📅 Today: {STATS['daily_trades']}/30

⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)

**Real Entry:** ${base:.2f}
**If LOSS ->** Martingale 1: ${base*2:.2f}
**If LOSS ->** Martingale 2: ${base*4:.2f}
**If LOSS ->** Martingale 3: ${base*8:.2f}

⚠️ MANUAL - Press WIN / LOSS / SKIP
"""
                        try: bot.send_message(OWNER_ID,msg,parse_mode="Markdown",reply_markup=mk); last_signal[pair]=time.time(); start_signal(pair, d['dir'], d['conf'], d['rsi'], d.get('adx',30))
                        except: pass
                    time.sleep(3)
            time.sleep(25)
        except: time.sleep(30)

@bot.message_handler(commands=['start','stop','mode','balance','results','brain'])
def start(m):
    if not is_allowed(m.from_user.id): bot.send_message(m.chat.id,"❌ Private"); return
    if m.text.startswith('/brain'):
        txt="🧠 **AI BRAIN - PAIR LEARNING**\n\n"; best=[]; bad=[]
        for pair, s in PAIR_BRAIN.items():
            total=s["wins"]+s["loss"]
            if total>=3:
                wr=s["wins"]/total*100; line=f"{PAIR_EMOJI.get(pair,pair)}: W{s['wins']} L{s['loss']} = {wr:.0f}% {'🚫 BLOCKED' if is_pair_blocked(pair) else ''}\n"
                if wr>=60: best.append(line)
                elif wr<50: bad.append(line)
        txt+="🏆 **BEST PAIRS:**\n"+("".join(best) if best else "Not enough data yet - trade more\n")+"\n💀 **BAD PAIRS (Avoiding):**\n"+("".join(bad) if bad else "None - all pairs good\n")+f"\n📅 Today: {STATS['daily_trades']}/30"
        if is_signal_active(): txt+=f"\n⏳ Active: {ACTIVE_SIGNAL['pair']} {ACTIVE_SIGNAL['dir']}"
        bot.send_message(m.chat.id,txt,parse_mode="Markdown"); return
    if m.text.startswith('/stop'):
        if m.chat.id in AUTO_STATE: AUTO_STATE[m.chat.id]['running']=False; bot.send_message(m.chat.id,"🛑 Stopping...")
        else: bot.send_message(m.chat.id,"Auto not running"); return
    if m.text.startswith('/results'):
        if not OTC_SESSION_RESULTS: bot.send_message(m.chat.id,"📭 No trades yet this session"); return
        wins=sum(1 for x in OTC_SESSION_RESULTS if x['win']); losses=len(OTC_SESSION_RESULTS)-wins; pnl_total=sum(x['pnl'] for x in OTC_SESSION_RESULTS); idx=OTC_MARTI["loss_streak"]
        txt=f"📊 **RESULTS (1 Real + 3 Marti)**\n\nTotal: {len(OTC_SESSION_RESULTS)} | W:{wins} L:{losses} | PnL: ${pnl_total:.2f}\nToday: {STATS['daily_trades']}/30 | Current: Level {idx+1}/4 | Base: ${OTC_MARTI['base']}\n\n"
        for r in OTC_SESSION_RESULTS[-25:]: txt+=f"{'✅' if r['win'] else '❌'} {r['time']} {r['pair']} {r['dir']} ${r['amt']} L{r['level']} {r['conf']}% {r['pnl']:+.2f}\n"
        bot.send_message(m.chat.id,txt,parse_mode="Markdown"); return
    if m.text.startswith('/mode'):
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz)
        txt=f"""📍 **MODE CHECK V14 BRAIN**

⏰ Now: {now.strftime('%A %H:%M:%S WAT')}
📊 Mode: {get_mode_text()}
💎 IQ: {'✅' if IQ_CONNECTED else '❌ False'}
🛡️ Martingale: 1 Real + 3 Marti (1-2-4-8)
📅 Today: {STATS['daily_trades']}/30 trades
🧠 Brain: {'ON - Learning' if PAIR_BRAIN else 'ON - No data yet'}
⏳ Active Signal: {ACTIVE_SIGNAL['pair'] if is_signal_active() else 'None'}
OTC: {'✅ ON' if ENABLE_OTC else '⛔ DISABLED - REAL only'}
"""
        bot.send_message(m.chat.id,txt,parse_mode="Markdown"); return
    if m.text.startswith('/balance'):
        try:
            if not IQ_CONNECTED: bot.send_message(m.chat.id,f"💰 **BALANCES**\nIQ: ❌ Not connected yet\n📍 {get_mode_text()}\n\nWait 1 min and try /start again"); return
            demo=get_real_balance("PRACTICE"); real=get_real_balance("REAL"); bot.send_message(m.chat.id,f"💰 **BALANCES**\n🟢 DEMO: ${demo:.2f}\n🔴 REAL: ${real:.2f}\n📍 {get_mode_text()}")
        except Exception as e: bot.send_message(m.chat.id,f"Balance error {e}")
        return
    try: bal_demo=get_real_balance("PRACTICE") if IQ_CONNECTED else STATS.get("real_balance",0.0)
    except: bal_demo=0.0
    mk=types.InlineKeyboardMarkup(row_width=1); mk.add(types.InlineKeyboardButton(f"📈 TRADE REAL (22) AUTO EXPIRY - ${bal_demo:.2f}",callback_data="trade_real")); mk.add(types.InlineKeyboardButton("📊 MY STATS",callback_data="stats"),types.InlineKeyboardButton("🧠 AI BRAIN",callback_data="brain_btn"),types.InlineKeyboardButton("⚙️ SETTINGS",callback_data="settings"))
    txt=f"""🤖 **Z-BOT V14 BRAIN - MANUAL** 🤖

💎 IQ: {'✅' if IQ_CONNECTED else '❌ False - Retrying...'} | 💰 DEMO ${bal_demo:.2f}
🏆 W:{STATS['wins']} L:{STATS['loss']} | 🔥 {STATS['streak']}
📅 Today: {STATS['daily_trades']}/30
🧠 Brain: Learning your best pairs
📍 {get_mode_text()}
⛔ OTC Disabled - REAL signals start 7AM

👇 **Select:**
"""
    bot.send_message(m.chat.id,txt,reply_markup=mk,parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_allowed(c.from_user.id): bot.answer_callback_query(c.id,"❌ Private"); return
    data=c.data; cid=c.message.chat.id
    if data.startswith("skip_"):
        pair=data.replace("skip_","")
        if cid in PULLBACK_STATE: PULLBACK_STATE[cid]["active"]=False
        clear_signal(); bot.answer_callback_query(c.id,"Skipped - Next signal can come")
        bot.send_message(cid,f"⏭️ **SKIPPED**\n\n💱 {pair}\nYou skipped this trade.\nNo WIN / LOSS recorded.\nNo Brain change.\n✅ Lock opened - Next signal can now come."); return
    if data.startswith("manual_win_"):
        pair=data.replace("manual_win_",""); record_brain(pair, True, ACTIVE_SIGNAL.get("conf",88), ACTIVE_SIGNAL.get("rsi",50), ACTIVE_SIGNAL.get("adx",30)); OTC_MARTI["loss_streak"]=0
        if cid in PULLBACK_STATE: PULLBACK_STATE[cid]["active"]=False
        clear_signal(); STATS['wins']+=1; count_trade(); wr=get_pair_winrate(pair); wr_txt=f"\n🧠 {pair} Brain WR now {wr:.0f}%" if wr is not None else ""
        bot.answer_callback_query(c.id,"WIN - Reset to Real Entry"); bot.send_message(cid,f"✅ **WIN Recorded**\n\n💱 {pair}\n♻️ RESET to Real Entry $1\n🔍 Pullback scan STOPPED{wr_txt}\n📅 Today: {STATS['daily_trades']}/30 trades\n✅ Next signal can now come."); return
    if data.startswith("manual_loss_"):
        parts=data.replace("manual_loss_","").rsplit("_",1); pair=parts[0]; orig_dir=parts[1] if len(parts)>1 else "CALL"
        record_brain(pair, False, ACTIVE_SIGNAL.get("conf",88), ACTIVE_SIGNAL.get("rsi",50), ACTIVE_SIGNAL.get("adx",30)); OTC_MARTI["loss_streak"]+=1; STATS['loss']+=1; count_trade()
        if OTC_MARTI["loss_streak"]>=4:
            OTC_MARTI["loss_streak"]=0
            if cid in PULLBACK_STATE: PULLBACK_STATE[cid]["active"]=False
            clear_signal(); wr=get_pair_winrate(pair); wr_txt=f"\n🧠 {pair} Brain WR now {wr:.0f}%" if wr is not None else ""
            bot.answer_callback_query(c.id,"Chain finished - Reset to $1"); bot.send_message(cid,f"⛔ **CHAIN FINISHED**\n\n💱 {pair}\n❌ Lost: $1 + $2 + $4 + $8 = -$15\n♻️ RESET to Real Entry $1\n🛑 No more martingale for this pair.{wr_txt}\n📅 Today: {STATS['daily_trades']}/30\n✅ Next signal can now come."); return
        levels=OTC_MARTI["levels"]; idx=OTC_MARTI["loss_streak"]; mult=levels[idx]; next_amt=OTC_MARTI["base"]*mult; names=["","Martingale 1","Martingale 2","Martingale 3"]; wr=get_pair_winrate(pair); wr_txt=f"\n🧠 {pair} Brain WR {wr:.0f}%" if wr is not None else ""
        bot.answer_callback_query(c.id,f"LOSS - Next {names[idx]} ${next_amt}"); bot.send_message(cid,f"❌ **LOSS Recorded**\n\n💱 {pair}\n👉 Next: **{names[idx]} - ${next_amt:.2f} Level {idx+1}/4 ({mult}x)**{wr_txt}\n🔍 Scanning every 10 sec for pullback entry...\n📍 RSI7 + RSI14 safe + RSI turning + Price at EMA\n\nPress ✅ WIN / ❌ LOSS / ⏭️ SKIP after you trade it manually.")
        threading.Thread(target=pullback_scanner_loop, args=(cid, pair, orig_dir), daemon=True).start(); return
    if data=="brain_btn":
        txt="🧠 **AI BRAIN**\n\n"; best=[]; bad=[]
        for pair,s in PAIR_BRAIN.items():
            total=s["wins"]+s["loss"]
            if total>=3:
                wr=s["wins"]/total*100; line=f"{PAIR_EMOJI.get(pair,pair)}: W{s['wins']} L{s['loss']} = {wr:.0f}% {'🚫' if is_pair_blocked(pair) else ''}\n"
                if wr>=60: best.append(line)
                elif wr<50: bad.append(line)
        txt+="🏆 BEST:\n"+("".join(best) if best else "No data yet\n")+"\n💀 BAD:\n"+("".join(bad) if bad else "None\n"); bot.send_message(cid,txt,parse_mode="Markdown"); return
    if data=="trade_real":
        mk=types.InlineKeyboardMarkup(row_width=1); mk.add(types.InlineKeyboardButton("🔍 📊 SCAN ALL REAL NOW (22 PAIRS)",callback_data="scan_all_real"))
        for p in REAL_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}",callback_data=f"real_pair_{p}"))
        bot.send_message(cid,f"📈 **TRADE REAL V14 BRAIN MANUAL**\n📍 {get_mode_text()}\n📅 Today: {STATS['daily_trades']}/30",reply_markup=mk,parse_mode="Markdown"); return
    if data=="scan_all_real":
        if is_signal_active(): bot.send_message(cid,f"⏳ **One signal already active**\n\n💱 {ACTIVE_SIGNAL['pair']} {ACTIVE_SIGNAL['dir']}\nFinish it first - Press ✅ WIN / ❌ LOSS / ⏭️ SKIP\nNo new signal until that chain ends."); return
        if not can_trade_today(): bot.send_message(cid,"⛔ Max 30 trades reached today. Come back tomorrow 7AM."); return
        bot.answer_callback_query(c.id,"Scanning 22 REAL pairs V14..."); scan_msg=bot.send_message(cid,"🔍 **SCANNING ALL 22 REAL PAIRS V14 BRAIN...**\n\n⏳ ~12 sec"); results=[]; datas={}
        for pair in REAL_PAIRS:
            if is_pair_blocked(pair): results.append((pair,0,"-","🧠 Blocked","🔴 BLOCKED",120)); continue
            d=analyze_sniper_v12(pair,sniper_mode=False)
            if not d: results.append((pair,0,"-","No data","🔴 NO TRADE",120)); continue
            conf=d['conf']; dir_=d['dir']; reason=d['reason']; exp=d['expiry']
            if conf>=88: status="🟢 READY"
            elif conf>=65: status="🟡 WAIT"
            else: status="🔴 NO TRADE"
            results.append((pair,conf,dir_,reason,status,exp)); datas[pair]=d
            try: bot.edit_message_text(f"🔍 Scanning V14... {pair} {conf:.0f}%",cid,scan_msg.message_id)
            except: pass
            time.sleep(0.3)
        results.sort(key=lambda x: x[1], reverse=True); txt="📊 **REAL V14 BRAIN READINESS** 📊\n"; txt+=f"📍 {get_mode_text()}\n⏰ {datetime.now(pytz.timezone('Africa/Lagos')).strftime('%H:%M:%S WAT')}\n📅 Today: {STATS['daily_trades']}/30\n\n"
        for pair,conf,dir_,reason,status,exp in results:
            emoji=PAIR_EMOJI.get(pair,pair)
            if conf>=65: txt+=f"{status} {emoji}: {conf:.0f}% {dir_} - {reason}\n"
            else: txt+=f"{status} {emoji}: {conf:.0f}% - {reason}\n"
        best=results[0] if results else None
        if best and best[1]>=88: txt+=f"\n💡 **BEST NOW:** {PAIR_EMOJI.get(best[0],best[0])} {best[1]:.0f}%"
        mk=types.InlineKeyboardMarkup(row_width=2)
        if best and best[1]>=88: mk.add(types.InlineKeyboardButton(f"✅ TRADE BEST {best[0]}",callback_data=f"real_pair_{best[0]}"))
        mk.add(types.InlineKeyboardButton("🔄 RE-SCAN ALL",callback_data="scan_all_real")); bot.send_message(cid,txt,reply_markup=mk,parse_mode="Markdown")
        if best and best[1]>=88 and best[0] in datas:
            time.sleep(0.5); best_data=datas[best[0]]; tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=45); dir_e="🟢 CALL ⬆️" if best_data['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]
            mk2=types.InlineKeyboardMarkup(row_width=2); mk2.add(types.InlineKeyboardButton("✅ WIN - Reset",callback_data=f"manual_win_{best_data['pair']}"),types.InlineKeyboardButton("❌ LOSS - Pullback Scan",callback_data=f"manual_loss_{best_data['pair']}_{best_data['dir']}")); mk2.add(types.InlineKeyboardButton("⏭️ SKIP THIS TRADE",callback_data=f"skip_{best_data['pair']}"))
            signal_txt=f"""📡 **REAL TOP SIGNAL V14 - MANUAL** 📡

💱 {PAIR_EMOJI.get(best_data['pair'],best_data['pair'])}
📊 {dir_e} | 🎯 {best_data['conf']:.0f}% SNIPER
📈 {best_data['reason']} | RSI {best_data['rsi']:.1f}
💸 {int(best_data['payout']*100)}% | 💰 {best_data['price']:.5f}

⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)

**Real Entry:** ${base:.2f}
**Marti 1:** ${base*2:.2f} | **Marti 2:** ${base*4:.2f} | **Marti 3:** ${base*8:.2f}

⚠️ MANUAL - Press WIN / LOSS / SKIP
"""
            bot.send_message(cid,signal_txt,parse_mode="Markdown",reply_markup=mk2); start_signal(best_data['pair'], best_data['dir'], best_data['conf'], best_data['rsi'], best_data.get('adx',30))
        return
    if data.startswith("real_pair_"):
        pair=data.replace("real_pair_","")
        if is_signal_active() and ACTIVE_SIGNAL['pair']!=pair: bot.send_message(cid,f"⏳ **One signal already active**\n\n💱 {ACTIVE_SIGNAL['pair']} {ACTIVE_SIGNAL['dir']}\nFinish it first - Press ✅ WIN / ❌ LOSS / ⏭️ SKIP"); return
        if is_pair_blocked(pair): bot.send_message(cid,f"🧠 **{pair} Blocked by Brain**\n\nThis pair has been losing for you. Brain blocked it for 2h.\nTry another pair or /brain"); return
        bot.answer_callback_query(c.id,f"Scanning {pair} V14..."); scan_msg=bot.send_message(cid,f"🔍 **V14 BRAIN SCAN {PAIR_EMOJI.get(pair,pair)}**\n\n0%\n🚀 Sniper..."); legit_live_scan(cid,scan_msg.message_id,pair); d=analyze_sniper_v12(pair,sniper_mode=False)
        if not d or d['conf']<88:
            mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🔄 RETRY",callback_data=f"real_pair_{pair}"),types.InlineKeyboardButton("📈 SCAN ALL",callback_data="scan_all_real")); bot.send_message(cid,f"⚠️ **No safe trade now for {pair}**\n\n📊 Conf: {d['conf'] if d else 0}% < 88%\n🛡️ {d['reason'] if d else 'No data'}",reply_markup=mk); return
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=45); dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]
        signal_txt=f"""📡 **REAL SIGNAL V14 BRAIN - MANUAL** 📡

💱 {PAIR_EMOJI.get(pair,pair)}
📊 {dir_e} | 🎯 {d['conf']:.0f}% SNIPER
📈 {d['reason']} | RSI {d['rsi']:.1f} | ATR {d['atr']:.5f}
💸 {int(d['payout']*100)}% | 💰 {d['price']:.5f}

⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)
⏱️ EXPIRY: 2 Min

**Real Entry:** ${base:.2f}
**Marti 1:** ${base*2:.2f} | **Marti 2:** ${base*4:.2f} | **Marti 3:** ${base*8:.2f}

⚠️ **MANUAL PLACE - Press WIN / LOSS / SKIP**
"""
        mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("✅ WIN - Reset",callback_data=f"manual_win_{pair}"),types.InlineKeyboardButton("❌ LOSS - Pullback Scan",callback_data=f"manual_loss_{pair}_{d['dir']}")); mk.add(types.InlineKeyboardButton("⏭️ SKIP THIS TRADE",callback_data=f"skip_{pair}")); mk.add(types.InlineKeyboardButton("🔁 SAME PAIR",callback_data=f"real_pair_{pair}"),types.InlineKeyboardButton("📈 SCAN ALL",callback_data="scan_all_real"))
        bot.send_message(cid,signal_txt,reply_markup=mk,parse_mode="Markdown"); start_signal(pair, d['dir'], d['conf'], d['rsi'], d.get('adx',30)); return
    if data=="trade" or data=="scan_all_otc" or data=="auto_setup" or data.startswith("auto_pair_") or data.startswith("auto_bal_") or data.startswith("auto_amt_") or data.startswith("pair_"):
        bot.answer_callback_query(c.id,"OTC Disabled"); bot.send_message(cid,"⛔ **OTC DISABLED**\n\nOTC dey cause hang. Bot go only send REAL signals from 7AM.\n\nUse TRADE REAL for now."); return
    if data=="stop_auto":
        if cid in AUTO_STATE: AUTO_STATE[cid]['running']=False; bot.send_message(cid,"🛑 Stopping..."); return
    if data=="stats":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0; bal=get_real_balance("PRACTICE"); bot.send_message(cid,f"📊 **STATS V14**\n📍 {get_mode_text()}\n🏆 Wins: {STATS['wins']}\n❌ Loss: {STATS['loss']}\n📈 Winrate: {wr:.1f}%\n🔥 Streak: {STATS['streak']}\n💰 Bal: ${bal:.2f}\n📅 Today: {STATS['daily_trades']}/30\n🧠 Brain pairs: {len(PAIR_BRAIN)}\n📦 OTC: DISABLED | REAL only",parse_mode="Markdown")
    if data=="settings": bot.send_message(cid,f"⚙️ **SETTINGS V14 BRAIN MANUAL**\n\n🛡️ V14: 5M Trend + ADX 25+ + MACD + Stochastic + BB + Payout 80%+\n⏱️ Expiry: 2 Min\n📊 OTC: DISABLED\nREAL: 7AM-8PM auto 88%+ signals\n📅 Max: 30 trades/day\n💰 Martingale: 1 Real + 3 Marti (1-2-4-8) MANUAL\n🧠 Brain: Learns best/bad pairs, blocks bad 2h\n⏭️ Skip: Available on all signals\n📊 Daily Summary: Auto at 8PM")

threading.Thread(target=background_iq, daemon=True).start()
threading.Thread(target=real_signal_scanner,daemon=True).start()
threading.Thread(target=daily_summary_loop,daemon=True).start()

if __name__ == "__main__":
    try:
        url=os.getenv("RENDER_EXTERNAL_URL")
        if url and BOT_TOKEN: requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={url}/{BOT_TOKEN}", timeout=5); print(f"Webhook set {url}")
    except: pass
    port=int(os.getenv("PORT",10000)); print(f"Starting Flask on 0.0.0.0:{port} - V14 BRAIN+SKIP - OTC DISABLED - MANUAL"); app.run(host="0.0.0.0", port=port, threaded=True)
