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

ENABLE_OTC = True

REAL_PAIRS = ["EURUSD","GBPUSD","USDJPY","EURGBP","AUDUSD","USDCAD","EURJPY","GBPJPY","USDCHF","AUDJPY","EURAUD","GBPCHF","EURCHF","NZDUSD","GBPAUD","EURCAD","AUDCAD","GBPCAD","NZDJPY","AUDNZD","CHFJPY","CADJPY"]
OTC_PAIRS = ["EURUSD-OTC","GBPUSD-OTC","USDJPY-OTC","AUDUSD-OTC","USDCAD-OTC","EURGBP-OTC","EURJPY-OTC","GBPJPY-OTC","AUDJPY-OTC","EURAUD-OTC","NZDUSD-OTC","USDCHF-OTC","EURCHF-OTC"]
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
def get_mode_text():
    if is_real_hours(): return "REAL SIGNAL (7AM-8PM)"
    return "OTC SIGNAL (Night/Weekend) - MANUAL ONLY"

@app.route("/")
def home():
    return f"V13 + V13-OTC 13 PAIRS RUNNING IQ:{IQ_CONNECTED} OTC:{ENABLE_OTC} {datetime.now(pytz.timezone('Africa/Lagos')).strftime('%H:%M:%S')}"

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
    steps = [(0,"🚀 V13 Sniper Init...",0.15),(20,f"🔌 Checking {pair}...",0.2),(40,"📊 ADX + ATR + SR...",0.25),(60,"📈 EMA + MACD + 5M Trend...",0.2),(80,"💹 RSI + Stochastic + BB...",0.2),(100,"🔒 SNIPER LOCKED!",0.3)]
    last_pct=-1
    for pct, text, delay in steps:
        if pct==last_pct: time.sleep(delay); continue
        last_pct=pct; filled=int(pct//5); bar="█"*filled+"░"*(20-filled); color="🟥" if pct<40 else "🟨" if pct<80 else "🟩" if pct<100 else "💎"
        txt=f"""{color} **Z-BOT V13 SNIPER PRO** {color}\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n💎 IQ: {'✅' if IQ_CONNECTED else '❌'}\n\n{bar} {pct}%\n\n🔍 {text}\n⏳ V13 Sniper"""
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
            with IQ_LOCK:
                logging.disable(logging.CRITICAL)
                c5 = iq.get_candles(pair, 300, 30, time.time())
            if c5 and len(c5) > 20:
                df5 = pd.DataFrame(sorted(c5, key=lambda x: x['from']))
        except: df5 = None
        close=df['close']; open_=df['open']; high=df['max']; low=df['min']
        vol = df['volume'] if 'volume' in df else pd.Series([1]*len(df))
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
        if adx < 18: return {"pair":pair,"dir":sig,"conf":42,"price":c_now,"rsi":r7,"reason":"Choppy - ADX Low","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if body < atr*0.30: return {"pair":pair,"dir":sig,"conf":48,"price":c_now,"rsi":r7,"reason":"Doji - No Body","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if payout < 0.70: return {"pair":pair,"dir":sig,"conf":52,"price":c_now,"rsi":r7,"reason":f"Low Payout {int(payout*100)}%","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        score=30; reasons=[]
        if df5 is not None:
            c5=df5['close']; e9_5=c5.ewm(9).mean(); e21_5=c5.ewm(21).mean()
            trend_5m = 1 if float(e9_5.iloc[-1]) > float(e21_5.iloc[-1]) else -1
            if (is_green and trend_5m==-1) or (not is_green and trend_5m==1): score-=18; reasons.append("Against 5M Trend")
            else: score+=12; reasons.append("5M Trend Align")
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
        if is_green:
            if bull_eng: score+=10; reasons.append("Bull Engulf")
            if pin_bull: score+=10; reasons.append("Pin Bull")
        else:
            if bear_eng: score+=10; reasons.append("Bear Engulf")
            if pin_bear: score+=10; reasons.append("Pin Bear")
        if is_green and stoch_val > 85: score-=12
        if not is_green and stoch_val < 15: score-=12
        if is_green and 50 < stoch_val < 80: score+=5
        if not is_green and 20 < stoch_val < 50: score+=5
        if is_green and c_now > upper: score+=5; reasons.append("BB Breakout")
        if not is_green and c_now < lower: score+=5; reasons.append("BB Breakout")
        avg_vol=float(vol.rolling(20).mean().iloc[-1]) if len(vol)>20 else 1; curr_vol=float(vol.iloc[-1]) if len(vol)>0 else 1
        if curr_vol > avg_vol*1.2: score+=8; reasons.append("Vol Spike")
        elif curr_vol > avg_vol: score+=4
        score = max(40, min(96, score)); reason = " + ".join(reasons) if reasons else "Weak PA"
        if sniper_mode and score < 88: return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":reason,"payout":payout,"expiry":120,"atr":atr,"rejected":True}
        return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":reason,"payout":payout,"expiry":120,"atr":atr,"rejected":False}
    except Exception as e:
        print(f"V12 err {pair} {e}"); return None

def get_sr_levels(df, lookback=50):
    try:
        if df is None or len(df) < lookback: return None, None, None, None
        recent = df.tail(lookback)
        support = float(recent['min'].min()); resistance = float(recent['max'].max())
        recent20 = df.tail(20); s20 = float(recent20['min'].min()); r20 = float(recent20['max'].max())
        return (support, resistance, s20, r20)
    except: return None, None, None, None

def is_news_time():
    try:
        tz = pytz.timezone("Africa/Lagos"); now = datetime.now(tz)
        h = now.hour; m = now.minute; mins = h*60 + m; weekday = now.weekday()
        if 810 <= mins <= 870: return True, "US News 13:30-14:30 WAT"
        if 540 <= mins <= 570: return True, "London Open 09:00-09:30"
        if 870 <= mins <= 900: return True, "NY Open 14:30-15:00"
        if weekday == 4 and now.day <= 7 and 810 <= mins <= 900: return True, "NFP Friday - No Trade"
        return False, ""
    except: return False, ""

def analyze_sniper_v13(pair, sniper_mode=False):
    is_news, news_reason = is_news_time()
    if is_news:
        try:
            df_tmp = get_candles(pair); price_tmp = float(df_tmp['close'].iloc[-1]) if df_tmp is not None else 0
        except: price_tmp = 0
        return {"pair":pair,"dir":"CALL","conf":35,"price":price_tmp,"rsi":50,"reason":f"NEWS BLOCK - {news_reason}","payout":0.85,"expiry":120,"atr":0,"rejected":False}
    d = analyze_sniper_v12(pair, sniper_mode=False)
    if d is None: return None
    if d['conf'] < 60: return d
    try:
        df = get_candles(pair)
        if df is None: return d
        c_now = d['price']; atr = d['atr'] if d.get('atr') else 0.0005
        support, resistance, s20, r20 = get_sr_levels(df, 50)
        if support is None: return d
        dist_to_res = abs(c_now - resistance) / atr if atr else 999; dist_to_sup = abs(c_now - support) / atr if atr else 999
        dist_to_r20 = abs(c_now - r20) / atr if atr else 999; dist_to_s20 = abs(c_now - s20) / atr if atr else 999
        conf = d['conf']; reason = d['reason']; is_green = d['dir'] == "CALL"
        if is_green and (dist_to_res < 0.8 or dist_to_r20 < 0.8):
            if "BB Breakout" not in reason or "Vol Spike" not in reason:
                conf -= 15; reason += " | Near Resistance - Risky"
                if sniper_mode and conf < 88: return {"pair":pair,"dir":d['dir'],"conf":conf,"price":c_now,"rsi":d['rsi'],"reason":reason,"payout":d['payout'],"expiry":120,"atr":atr,"rejected":True}
            else: conf += 5; reason += " | Resistance Breakout + Vol"
        if not is_green and (dist_to_sup < 0.8 or dist_to_s20 < 0.8):
            if "BB Breakout" not in reason or "Vol Spike" not in reason:
                conf -= 15; reason += " | Near Support - Risky"
                if sniper_mode and conf < 88: return {"pair":pair,"dir":d['dir'],"conf":conf,"price":c_now,"rsi":d['rsi'],"reason":reason,"payout":d['payout'],"expiry":120,"atr":atr,"rejected":True}
            else: conf += 5; reason += " | Support Breakout + Vol"
        if is_green and dist_to_sup < 1.5: conf += 7; reason += " | Bounce from Support"
        if not is_green and dist_to_res < 1.5: conf += 7; reason += " | Rejection from Resistance"
        conf = max(40, min(96, conf))
        if sniper_mode and conf < 88: return {"pair":pair,"dir":d['dir'],"conf":conf,"price":c_now,"rsi":d['rsi'],"reason":reason,"payout":d['payout'],"expiry":120,"atr":atr,"rejected":True}
        return {"pair":pair,"dir":d['dir'],"conf":conf,"price":c_now,"rsi":d['rsi'],"reason":reason,"payout":d['payout'],"expiry":120,"atr":atr,"rejected":False}
    except Exception as e:
        print(f"V13 err {pair} {e}"); return d

def analyze_otc_v13(pair, sniper_mode=False):
    df = get_candles(pair)
    if df is None: return None
    try:
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
        if adx < 22: return {"pair":pair,"dir":sig,"conf":42,"price":c_now,"rsi":r7,"reason":"OTC Choppy - ADX Low","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if body < atr*0.35: return {"pair":pair,"dir":sig,"conf":48,"price":c_now,"rsi":r7,"reason":"OTC Doji - No Body","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if payout < 0.80: return {"pair":pair,"dir":sig,"conf":52,"price":c_now,"rsi":r7,"reason":f"OTC Low Payout {int(payout*100)}%","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if is_green and (r7 > 68 or r7 < 50): return {"pair":pair,"dir":sig,"conf":55,"price":c_now,"rsi":r7,"reason":f"OTC RSI Not Safe {r7:.0f}","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if not is_green and (r7 < 32 or r7 > 50): return {"pair":pair,"dir":sig,"conf":55,"price":c_now,"rsi":r7,"reason":f"OTC RSI Not Safe {r7:.0f}","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        score=30; reasons=[]
        if is_green:
            if e9>e21>e50: score+=20; reasons.append("OTC EMA Bull Align")
            else: score-=15; reasons.append("OTC EMA Not Align")
        else:
            if e9<e21<e50: score+=20; reasons.append("OTC EMA Bear Align")
            else: score-=15; reasons.append("OTC EMA Not Align")
        if adx >= 30: score+=14; reasons.append(f"OTC ADX Strong {adx:.0f}")
        elif adx >= 25: score+=8
        else: score-=5
        if is_green and pdi > mdi: score+=10
        elif not is_green and mdi > pdi: score+=10
        else: score-=15
        if is_green:
            if 52 <= r7 <= 62 and 48 <= r14 <= 60: score+=16; reasons.append(f"OTC RSI Safe {r7:.0f}")
            else: score+=4
        else:
            if 38 <= r7 <= 48 and 40 <= r14 <= 52: score+=16; reasons.append(f"OTC RSI Safe {r7:.0f}")
            else: score+=4
        if is_green and macd_val > sig_val: score+=12; reasons.append("OTC MACD Bull")
        elif not is_green and macd_val < sig_val: score+=12; reasons.append("OTC MACD Bear")
        else: score-=12
        if is_green:
            if mom1 > 0.04 and mom3 > 0.08: score+=14; reasons.append(f"OTC Mom {mom1:.3f}%")
            elif mom1 > 0.02: score+=5
            elif mom1 < 0: score-=15
        else:
            if mom1 < -0.04 and mom3 < -0.08: score+=14; reasons.append(f"OTC Mom {mom1:.3f}%")
            elif mom1 < -0.02: score+=5
            elif mom1 > 0: score-=15
        bull_eng = c_now > o_prev and o_now < c_prev and is_green and c_prev < o_prev
        bear_eng = c_now < o_prev and o_now > c_prev and not is_green and c_prev > o_prev
        pin_bull = lower_wick > body*1.8 and lower_wick > upper_wick*1.5 and is_green
        pin_bear = upper_wick > body*1.8 and upper_wick > lower_wick*1.5 and not is_green
        has_pattern = False
        if is_green:
            if bull_eng: score+=14; reasons.append("OTC Bull Engulf"); has_pattern=True
            if pin_bull: score+=14; reasons.append("OTC Pin Bull"); has_pattern=True
        else:
            if bear_eng: score+=14; reasons.append("OTC Bear Engulf"); has_pattern=True
            if pin_bear: score+=14; reasons.append("OTC Pin Bear"); has_pattern=True
        if not has_pattern:
            return {"pair":pair,"dir":sig,"conf":58,"price":c_now,"rsi":r7,"reason":"OTC No Candle Pattern - Skip","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if is_green and stoch_val > 80: score-=15
        if not is_green and stoch_val < 20: score-=15
        if is_green and 50 < stoch_val < 75: score+=6
        if not is_green and 25 < stoch_val < 50: score+=6
        if is_green and c_now > upper: score+=3; reasons.append("OTC BB Break")
        if not is_green and c_now < lower: score+=3; reasons.append("OTC BB Break")
        score = max(40, min(97, score)); reason = " + ".join(reasons) if reasons else "OTC Weak"
        if sniper_mode and score < 91: return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":reason,"payout":payout,"expiry":120,"atr":atr,"rejected":True}
        return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":reason,"payout":payout,"expiry":120,"atr":atr,"rejected":False}
    except Exception as e:
        print(f"OTC V13 err {pair} {e}"); return None

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

def real_signal_scanner():
    last_signal={}; tz=pytz.timezone("Africa/Lagos")
    while True:
        try:
            if is_real_hours() and IQ_CONNECTED:
                for pair in REAL_PAIRS:
                    if pair in last_signal and time.time()-last_signal[pair]<600: continue
                    d=analyze_sniper_v13(pair,sniper_mode=True)
                    if d and not d.get('rejected') and d['conf']>=88:
                        now=datetime.now(tz); entry=now+timedelta(seconds=45); entry2=entry+timedelta(seconds=120); entry3=entry+timedelta(seconds=240); exp=d['expiry']; dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]
                        msg=f"""📡 **REAL SIGNAL V13 - 3 LEVELS (2 MIN EACH)** 📡\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n📊 {dir_e} | 🎯 {d['conf']:.0f}% SNIPER\n📈 {d['reason']} | RSI {d['rsi']:.1f} | ATR {d['atr']:.5f}\n💸 {int(d['payout']*100)}% | 2 Min Each Level\n\n⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)\n📅 {now.strftime('%A %d %b %H:%M WAT')}\n\n**Level 1:** {entry.strftime('%H:%M:%S')} - 2 Min - ${base:.2f}\n**Level 2:** {entry2.strftime('%H:%M:%S')} - 2 Min - ${base*2:.2f}\n**Level 3:** {entry3.strftime('%H:%M:%S')} - 2 Min - ${base*4:.2f}\n\n⛔ STOP after Level 3. No Level 4.\n⚠️ MANUAL - Follow levels only\n"""
                        try: bot.send_message(OWNER_ID,msg,parse_mode="Markdown"); last_signal[pair]=time.time()
                        except: pass
                    time.sleep(3)
            time.sleep(25)
        except: time.sleep(30)

def otc_signal_scanner():
    last_signal={}; tz=pytz.timezone("Africa/Lagos")
    while True:
        try:
            if not is_real_hours() and IQ_CONNECTED and ENABLE_OTC:
                for pair in OTC_PAIRS:
                    if pair in last_signal and time.time()-last_signal[pair]<600: continue
                    d=analyze_otc_v13(pair,sniper_mode=True)
                    if d and not d.get('rejected') and d['conf']>=91:
                        now=datetime.now(tz); entry=now+timedelta(seconds=45); entry2=entry+timedelta(seconds=120); entry3=entry+timedelta(seconds=240); exp=d['expiry']; dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]
                        msg=f"""📡 **OTC SIGNAL V13-OTC STRICT - 3 LEVELS (2 MIN EACH)** 📡\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n📊 {dir_e} | 🎯 {d['conf']:.0f}% SNIPER STRICT\n📈 {d['reason']} | RSI {d['rsi']:.1f} | ATR {d['atr']:.5f}\n💸 {int(d['payout']*100)}% | 2 Min Each Level\n\n⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)\n📅 {now.strftime('%A %d %b %H:%M WAT')}\n\n**Level 1:** {entry.strftime('%H:%M:%S')} - 2 Min - ${base:.2f}\n**Level 2:** {entry2.strftime('%H:%M:%S')} - 2 Min - ${base*2:.2f}\n**Level 3:** {entry3.strftime('%H:%M:%S')} - 2 Min - ${base*4:.2f}\n\n⛔ STOP after Level 3. No Level 4.\n⚠️ MANUAL - Follow levels only\n"""
                        try: bot.send_message(OWNER_ID,msg,parse_mode="Markdown"); last_signal[pair]=time.time()
                        except: pass
                    time.sleep(3)
            time.sleep(25)
        except: time.sleep(30)

@bot.message_handler(commands=['start','stop','mode','balance','results'])
def start(m):
    if not is_allowed(m.from_user.id): bot.send_message(m.chat.id,"❌ Private"); return
    if m.text.startswith('/stop'):
        if m.chat.id in AUTO_STATE: AUTO_STATE[m.chat.id]['running']=False; bot.send_message(m.chat.id,"🛑 Stopping...")
        else: bot.send_message(m.chat.id,"Auto not running"); return
    if m.text.startswith('/results'):
        if not OTC_SESSION_RESULTS: bot.send_message(m.chat.id,"📭 No trades yet this session"); return
        wins=sum(1 for x in OTC_SESSION_RESULTS if x['win']); losses=len(OTC_SESSION_RESULTS)-wins; pnl_total=sum(x['pnl'] for x in OTC_SESSION_RESULTS); levels = OTC_MARTI["levels"]; idx = OTC_MARTI["loss_streak"] % len(levels)
        txt=f"📊 **RESULTS (1-2-4)**\n\nTotal: {len(OTC_SESSION_RESULTS)} | W:{wins} L:{losses} | PnL: ${pnl_total:.2f}\nCurrent Level: {idx+1} ({levels[idx]}x) | Base: ${OTC_MARTI['base']} | Each Level 2 Min\n\n"
        for r in OTC_SESSION_RESULTS[-25:]: txt+=f"{'✅' if r['win'] else '❌'} {r['time']} {r['pair']} {r['dir']} ${r['amt']} L{r['level']} {r['conf']}% {r['pnl']:+.2f}\n"
        bot.send_message(m.chat.id,txt,parse_mode="Markdown"); return
    if m.text.startswith('/mode'):
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz)
        txt=f"""📍 **MODE CHECK V13 + OTC STRICT**

⏰ Now: {now.strftime('%A %H:%M:%S WAT')}
📊 Mode: {get_mode_text()}
💎 IQ: {'✅' if IQ_CONNECTED else '❌ False - Check email/pass or IP blocked'}
🛡️ REAL: V13 (88%+) | OTC: V13-OTC Strict (91%+)
OTC Pairs: 13 | REAL Pairs: 22
OTC Signals: {'✅ ON - MANUAL ONLY' if ENABLE_OTC else '⛔ OFF'}
Auto Trade: ⛔ REMOVED - MANUAL ONLY
"""
        bot.send_message(m.chat.id,txt,parse_mode="Markdown"); return
    if m.text.startswith('/balance'):
        try:
            if not IQ_CONNECTED:
                bot.send_message(m.chat.id,f"💰 **BALANCES**\nIQ: ❌ Not connected yet\n📍 {get_mode_text()}\n\nWait 1 min and try /start again")
                return
            demo=get_real_balance("PRACTICE"); real=get_real_balance("REAL")
            bot.send_message(m.chat.id,f"💰 **BALANCES**\n🟢 DEMO: ${demo:.2f}\n🔴 REAL: ${real:.2f}\n📍 {get_mode_text()}")
        except Exception as e: bot.send_message(m.chat.id,f"Balance error {e}")
        return
    try: bal_demo = get_real_balance("PRACTICE") if IQ_CONNECTED else STATS.get("real_balance",0.0)
    except: bal_demo = 0.0
    mk=types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton(f"📈 TRADE REAL (22) - ${bal_demo:.2f}",callback_data="trade_real"))
    mk.add(types.InlineKeyboardButton(f"📈 TRADE OTC (13) - MANUAL",callback_data="trade_otc"))
    mk.add(types.InlineKeyboardButton("📊 MY STATS",callback_data="stats"),types.InlineKeyboardButton("⚙️ SETTINGS",callback_data="settings"))
    txt=f"""🤖 **Z-BOT V13 + OTC STRICT - SIGNAL ONLY** 🤖

💎 IQ: {'✅' if IQ_CONNECTED else '❌ False - Retrying...'} | 💰 DEMO ${bal_demo:.2f}
🏆 W:{STATS['wins']} L:{STATS['loss']} | 🔥 {STATS['streak']}
📍 {get_mode_text()}
⛔ NO AUTO TRADE - You place manually

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
        bot.send_message(cid,f"📈 **TRADE REAL V13**\n📍 {get_mode_text()}",reply_markup=mk,parse_mode="Markdown"); return
    if data=="trade_otc":
        mk=types.InlineKeyboardMarkup(row_width=1); mk.add(types.InlineKeyboardButton("🔍 📊 SCAN ALL OTC NOW (13 PAIRS)",callback_data="scan_all_otc"))
        for p in OTC_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}",callback_data=f"otc_pair_{p}"))
        bot.send_message(cid,f"📈 **TRADE OTC V13-OTC STRICT - MANUAL ONLY**\n📍 {get_mode_text()}",reply_markup=mk,parse_mode="Markdown"); return
    if data=="scan_all_real":
        bot.answer_callback_query(c.id,"Scanning 22 REAL pairs V13..."); scan_msg=bot.send_message(cid,"🔍 **SCANNING ALL 22 REAL PAIRS V13...**\n\n⏳ ~12 sec"); results=[]; datas={}
        for pair in REAL_PAIRS:
            d=analyze_sniper_v13(pair,sniper_mode=False)
            if not d: results.append((pair,0,"-","No data","🔴 NO TRADE",120)); continue
            conf=d['conf']; dir_=d['dir']; reason=d['reason']; exp=d['expiry']
            if conf>=88: status="🟢 READY"
            elif conf>=65: status="🟡 READY"
            else: status="🔴 NO TRADE"
            results.append((pair,conf,dir_,reason,status,exp)); datas[pair]=d
            try: bot.edit_message_text(f"🔍 Scanning V13... {pair} {conf:.0f}%",cid,scan_msg.message_id)
            except: pass
            time.sleep(0.3)
        results.sort(key=lambda x: x[1], reverse=True); txt="📊 **REAL V13 SNIPER READINESS** 📊\n"; txt+=f"📍 {get_mode_text()}\n⏰ {datetime.now(pytz.timezone('Africa/Lagos')).strftime('%H:%M:%S WAT')}\n\n"
        for pair,conf,dir_,reason,status,exp in results:
            emoji=PAIR_EMOJI.get(pair,pair)
            if conf>=65: txt+=f"{status} {emoji}: {conf:.0f}% {dir_} Safe 2 min - {reason}\n"
            else: txt+=f"{status} {emoji}: {conf:.0f}% - {reason}\n"
        best = results[0] if results else None
        if best and best[1]>=65: txt+=f"\n💡 **BEST NOW:** {PAIR_EMOJI.get(best[0],best[0])} {best[1]:.0f}% Safe 2 min"
        mk=types.InlineKeyboardMarkup(row_width=2)
        if best and best[1]>=65: mk.add(types.InlineKeyboardButton(f"✅ TRADE BEST {best[0]}",callback_data=f"real_pair_{best[0]}"))
        mk.add(types.InlineKeyboardButton("🔄 RE-SCAN ALL",callback_data="scan_all_real"))
        bot.send_message(cid,txt,reply_markup=mk,parse_mode="Markdown")
        if best and best[1]>=65 and best[0] in datas:
            time.sleep(0.5); best_data=datas[best[0]]; tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=45); entry2=entry+timedelta(seconds=120); entry3=entry+timedelta(seconds=240); exp=best_data['expiry']; dir_e="🟢 CALL ⬆️" if best_data['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]
            signal_txt=f"""📡 **REAL TOP SIGNAL V13 - 3 LEVELS** 📡\n\n💱 {PAIR_EMOJI.get(best_data['pair'],best_data['pair'])}\n📊 {dir_e} | 🎯 {best_data['conf']:.0f}% SNIPER\n📈 {best_data['reason']} | RSI {best_data['rsi']:.1f}\n💸 {int(best_data['payout']*100)}% | 💰 {best_data['price']:.5f}\n\n⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)\n\n**Level 1:** {entry.strftime('%H:%M:%S')} - 2 Min - ${base:.2f}\n**Level 2:** {entry2.strftime('%H:%M:%S')} - 2 Min - ${base*2:.2f}\n**Level 3:** {entry3.strftime('%H:%M:%S')} - 2 Min - ${base*4:.2f}\n\n⛔ STOP after Level 3.\n"""
            bot.send_message(cid,signal_txt,parse_mode="Markdown")
        return
    if data=="scan_all_otc":
        bot.answer_callback_query(c.id,"Scanning 13 OTC pairs V13-OTC..."); scan_msg=bot.send_message(cid,"🔍 **SCANNING ALL 13 OTC PAIRS V13-OTC STRICT...**\n\n⏳ ~12 sec"); results=[]; datas={}
        for pair in OTC_PAIRS:
            d=analyze_otc_v13(pair,sniper_mode=False)
            if not d: results.append((pair,0,"-","No data","🔴 NO TRADE",120)); continue
            conf=d['conf']; dir_=d['dir']; reason=d['reason']; exp=d['expiry']
            if conf>=91: status="🟢 READY"
            elif conf>=65: status="🟡 READY"
            else: status="🔴 NO TRADE"
            results.append((pair,conf,dir_,reason,status,exp)); datas[pair]=d
            try: bot.edit_message_text(f"🔍 Scanning V13-OTC... {pair} {conf:.0f}%",cid,scan_msg.message_id)
            except: pass
            time.sleep(0.3)
        results.sort(key=lambda x: x[1], reverse=True); txt="📊 **OTC V13-OTC STRICT READINESS** 📊\n"; txt+=f"📍 {get_mode_text()}\n⏰ {datetime.now(pytz.timezone('Africa/Lagos')).strftime('%H:%M:%S WAT')}\n\n"
        for pair,conf,dir_,reason,status,exp in results:
            emoji=PAIR_EMOJI.get(pair,pair)
            if conf>=65: txt+=f"{status} {emoji}: {conf:.0f}% {dir_} Safe 2 min - {reason}\n"
            else: txt+=f"{status} {emoji}: {conf:.0f}% - {reason}\n"
        best = results[0] if results else None
        if best and best[1]>=65: txt+=f"\n💡 **BEST NOW:** {PAIR_EMOJI.get(best[0],best[0])} {best[1]:.0f}% Safe 2 min"
        mk=types.InlineKeyboardMarkup(row_width=2)
        if best and best[1]>=65: mk.add(types.InlineKeyboardButton(f"✅ TRADE BEST {best[0]}",callback_data=f"otc_pair_{best[0]}"))
        mk.add(types.InlineKeyboardButton("🔄 RE-SCAN ALL",callback_data="scan_all_otc"))
        bot.send_message(cid,txt,reply_markup=mk,parse_mode="Markdown")
        if best and best[1]>=65 and best[0] in datas:
            time.sleep(0.5); best_data=datas[best[0]]; tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=45); entry2=entry+timedelta(seconds=120); entry3=entry+timedelta(seconds=240); exp=best_data['expiry']; dir_e="🟢 CALL ⬆️" if best_data['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]
            signal_txt=f"""📡 **OTC TOP SIGNAL V13-OTC STRICT - 3 LEVELS** 📡\n\n💱 {PAIR_EMOJI.get(best_data['pair'],best_data['pair'])}\n📊 {dir_e} | 🎯 {best_data['conf']:.0f}% SNIPER STRICT\n📈 {best_data['reason']} | RSI {best_data['rsi']:.1f}\n💸 {int(best_data['payout']*100)}% | 💰 {best_data['price']:.5f}\n\n⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)\n\n**Level 1:** {entry.strftime('%H:%M:%S')} - 2 Min - ${base:.2f}\n**Level 2:** {entry2.strftime('%H:%M:%S')} - 2 Min - ${base*2:.2f}\n**Level 3:** {entry3.strftime('%H:%M:%S')} - 2 Min - ${base*4:.2f}\n\n⛔ STOP after Level 3.\n⚠️ MANUAL - Place yourself\n"""
            bot.send_message(cid,signal_txt,parse_mode="Markdown")
        return
    if data.startswith("real_pair_"):
        pair=data.replace("real_pair_",""); bot.answer_callback_query(c.id,f"Scanning {pair} V13..."); scan_msg=bot.send_message(cid,f"🔍 **V13 SNIPER SCAN {PAIR_EMOJI.get(pair,pair)}**\n\n0%\n🚀 Sniper..."); legit_live_scan(cid,scan_msg.message_id,pair); d=analyze_sniper_v13(pair,sniper_mode=False)
        if not d or d['conf'] < 65:
            mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🔄 RETRY",callback_data=f"real_pair_{pair}"),types.InlineKeyboardButton("📈 SCAN ALL",callback_data="scan_all_real"))
            bot.send_message(cid,f"⚠️ **No safe trade now for {pair}**\n\n📊 Conf: {d['conf'] if d else 0}% < 65%\n🛡️ {d['reason'] if d else 'No data'}",reply_markup=mk); return
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=45); entry2=entry+timedelta(seconds=120); entry3=entry+timedelta(seconds=240); exp=d['expiry']; dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]
        signal_txt=f"""📡 **REAL SIGNAL V13 SNIPER - 3 LEVELS** 📡\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n📊 {dir_e} | 🎯 {d['conf']:.0f}% SNIPER\n📈 {d['reason']} | RSI {d['rsi']:.1f} | ATR {d['atr']:.5f}\n💸 {int(d['payout']*100)}% | 💰 {d['price']:.5f}\n\n⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)\n⏱️ EXPIRY: 2 Min Each Level\n\n**Level 1:** {entry.strftime('%H:%M:%S')} - 2 Min - ${base:.2f}\n**Level 2:** {entry2.strftime('%H:%M:%S')} - 2 Min - ${base*2:.2f}\n**Level 3:** {entry3.strftime('%H:%M:%S')} - 2 Min - ${base*4:.2f}\n\n⛔ STOP after Level 3.\n⚠️ **MANUAL PLACE**\n"""
        mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("🔁 SAME PAIR",callback_data=f"real_pair_{pair}"),types.InlineKeyboardButton("📈 SCAN ALL",callback_data="scan_all_real"))
        bot.send_message(cid,signal_txt,reply_markup=mk,parse_mode="Markdown"); return
    if data.startswith("otc_pair_"):
        pair=data.replace("otc_pair_",""); bot.answer_callback_query(c.id,f"Scanning {pair} V13-OTC..."); scan_msg=bot.send_message(cid,f"🔍 **V13-OTC SNIPER SCAN {PAIR_EMOJI.get(pair,pair)}**\n\n0%\n🚀 Sniper..."); legit_live_scan(cid,scan_msg.message_id,pair); d=analyze_otc_v13(pair,sniper_mode=False)
        if not d or d['conf'] < 65:
            mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🔄 RETRY",callback_data=f"otc_pair_{pair}"),types.InlineKeyboardButton("📈 SCAN ALL OTC",callback_data="scan_all_otc"))
            bot.send_message(cid,f"⚠️ **No safe trade now for {pair}**\n\n📊 Conf: {d['conf'] if d else 0}% < 65%\n🛡️ {d['reason'] if d else 'No data'}",reply_markup=mk); return
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=45); entry2=entry+timedelta(seconds=120); entry3=entry+timedelta(seconds=240); exp=d['expiry']; dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]
        signal_txt=f"""📡 **OTC SIGNAL V13-OTC STRICT - 3 LEVELS** 📡\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n📊 {dir_e} | 🎯 {d['conf']:.0f}% SNIPER STRICT\n📈 {d['reason']} | RSI {d['rsi']:.1f} | ATR {d['atr']:.5f}\n💸 {int(d['payout']*100)}% | 💰 {d['price']:.5f}\n\n⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)\n⏱️ EXPIRY: 2 Min Each Level\n\n**Level 1:** {entry.strftime('%H:%M:%S')} - 2 Min - ${base:.2f}\n**Level 2:** {entry2.strftime('%H:%M:%S')} - 2 Min - ${base*2:.2f}\n**Level 3:** {entry3.strftime('%H:%M:%S')} - 2 Min - ${base*4:.2f}\n\n⛔ STOP after Level 3.\n⚠️ **MANUAL PLACE**\n"""
        mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("🔁 SAME PAIR",callback_data=f"otc_pair_{pair}"),types.InlineKeyboardButton("📈 SCAN ALL OTC",callback_data="scan_all_otc"))
        bot.send_message(cid,signal_txt,reply_markup=mk,parse_mode="Markdown"); return
    if data=="trade" or data=="auto_setup" or data.startswith("auto_pair_") or data.startswith("auto_bal_") or data.startswith("auto_amt_") or data.startswith("pair_"):
        bot.answer_callback_query(c.id,"Auto Disabled")
        bot.send_message(cid,"⛔ **AUTO TRADE REMOVED**\n\nBot na SIGNAL ONLY now. Use TRADE REAL or TRADE OTC, place manually.")
        return
    if data=="stop_auto":
        if cid in AUTO_STATE: AUTO_STATE[cid]['running']=False; bot.send_message(cid,"🛑 Stopping..."); return
    if data.startswith("bal_"):
        parts=data.split("_"); bal=parts[1]; pair=parts[2]; expiry=int(parts[3]); mk=types.InlineKeyboardMarkup(row_width=3); mk.add(types.InlineKeyboardButton("💵 $1",callback_data=f"amt_1_{pair}_{bal}_{expiry}"),types.InlineKeyboardButton("💵 $2",callback_data=f"amt_2_{pair}_{bal}_{expiry}"),types.InlineKeyboardButton("💵 $4",callback_data=f"amt_4_{pair}_{bal}_{expiry}")); mk.add(types.InlineKeyboardButton("✏️ CUSTOM",callback_data=f"custom_{pair}_{bal}_{expiry}"))
        bot.send_message(cid,f"✅ {pair} Safe 2 Min | {bal}\n\n💰 **AMOUNT**",reply_markup=mk,parse_mode="Markdown"); return
    if data.startswith("amt_") or data.startswith("custom_"):
        bot.answer_callback_query(c.id,"Manual Only")
        bot.send_message(cid,"⚠️ **MANUAL ONLY**\n\nAuto place don remove. Copy the signal, go IQ app, place am yourself for 2 Min.")
        return
    if data=="stats":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0; bal=get_real_balance("PRACTICE"); mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("📈 TRADE REAL",callback_data="trade_real"),types.InlineKeyboardButton("📈 TRADE OTC",callback_data="trade_otc"))
        bot.send_message(cid,f"📊 **STATS V13**\n📍 {get_mode_text()}\n🏆 Wins: {STATS['wins']}\n❌ Loss: {STATS['loss']}\n📈 Winrate: {wr:.1f}%\n🔥 Streak: {STATS['streak']}\n💰 Bal: ${bal:.2f}\n📦 Auto Trade: REMOVED | Signal Only",reply_markup=mk,parse_mode="Markdown")
    if data=="settings":
        bot.send_message(cid,f"⚙️ **SETTINGS V13 + OTC STRICT**\n\n🛡️ REAL: V13 - 5M Trend + ADX + MACD + Stochastic + BB + Volume + Payout + SR + News Filter - 88%+\n🛡️ OTC: V13-OTC Strict - EMA Full Align + ADX 22+ + RSI Tight + Pin/Engulf MUST + No Volume/SR - 91%+\n⏱️ Expiry: FIXED 2 Min (120s) for Level 1, 2, 3\n📊 REAL: 22 Pairs - 7AM-8PM auto 88%+ signals\n📊 OTC: 13 Pairs - Night/Weekend auto 91%+ signals\n🤖 Auto Trade: REMOVED - MANUAL ONLY")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id,{}).get("step")=="await_amt")
def handle_custom_amt(m):
    cid=m.chat.id; st=user_states.get(cid,{})
    if not is_allowed(m.from_user.id): return
    bot.send_message(cid,"⚠️ Manual Only - Place am yourself for IQ app.")

threading.Thread(target=background_iq, daemon=True).start()
threading.Thread(target=real_signal_scanner,daemon=True).start()
threading.Thread(target=otc_signal_scanner,daemon=True).start()

if __name__ == "__main__":
    try:
        url=os.getenv("RENDER_EXTERNAL_URL")
        if url and BOT_TOKEN:
            requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={url}/{BOT_TOKEN}", timeout=5)
            print(f"Webhook set {url}")
    except: pass
    port=int(os.getenv("PORT",10000))
    print(f"Starting Flask on 0.0.0.0:{port} - V13 + OTC STRICT 13 PAIRS SIGNAL ONLY - NO AUTO TRADE")
    app.run(host="0.0.0.0", port=port, threaded=True)
