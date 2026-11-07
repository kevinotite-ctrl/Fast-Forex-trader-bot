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

# ===== YOUR 8 OTC PAIRS - AS IN YOUR CODE =====
OTC_PAIRS = ["EURUSD-OTC","GBPUSD-OTC","EURGBP-OTC","USDJPY-OTC","GBPJPY-OTC","AUDUSD-OTC","USDCHF-OTC","EURJPY-OTC"]
# ===== REAL PAIRS - SAME 8, REAL MARKET =====
REAL_PAIRS = ["EURUSD","GBPUSD","EURGBP","USDJPY","GBPJPY","AUDUSD","USDCHF","EURJPY"]

PAIR_EMOJI = {
    "EURUSD-OTC":"🇪🇺 EUR/USD OTC","GBPUSD-OTC":"🇬🇧 GBP/USD OTC","EURGBP-OTC":"🇪🇺 EUR/GBP OTC","USDJPY-OTC":"🇺🇸 USD/JPY OTC",
    "GBPJPY-OTC":"🇬🇧 GBP/JPY OTC","AUDUSD-OTC":"🇦🇺 AUD/USD OTC","USDCHF-OTC":"🇺🇸 USD/CHF OTC","EURJPY-OTC":"🇪🇺 EUR/JPY OTC",
    "EURUSD":"🇪🇺 EUR/USD REAL","GBPUSD":"🇬🇧 GBP/USD REAL","EURGBP":"🇪🇺 EUR/GBP REAL","USDJPY":"🇺🇸 USD/JPY REAL",
    "GBPJPY":"🇬🇧 GBP/JPY REAL","AUDUSD":"🇦🇺 AUD/USD REAL","USDCHF":"🇺🇸 USD/CHF REAL","EURJPY":"🇪🇺 EUR/JPY REAL"
}
STATS = {"balance":100.0,"wins":0,"loss":0,"streak":0}
user_states = {}
IQ_LOCK = threading.Lock()
IQ_CONNECTED=False; iq=None
PAYOUT_CACHE={}; PAYOUT_TIME=0

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
    if is_real_hours(): return "REAL MARKET (7AM-8PM)"
    return "OTC MARKET (Night/Weekend)"

@app.route("/")
def home():
    return f"V48 + V13 RUNNING IQ:{IQ_CONNECTED} {datetime.now(pytz.timezone('Africa/Lagos')).strftime('%H:%M:%S')}"

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def wh():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode("utf-8"))])
    return "ok"

# ===== IQ CONNECT - IN BACKGROUND, NO BLOCK =====
def background_iq():
    global iq, IQ_CONNECTED
    time.sleep(2)
    for attempt in range(10):
        try:
            from iqoptionapi.stable_api import IQ_Option
            EMAIL=os.getenv("IQ_EMAIL"); PWD=os.getenv("IQ_PASS")
            PROXY=os.getenv("PROXY_URL")
            if not EMAIL or not PWD:
                print("IQ_EMAIL/PASS missing"); return
            iq=IQ_Option(EMAIL,PWD)
            if PROXY:
                try:
                    pc = PROXY.replace("http://","").replace("https://","")
                    if "@" in pc:
                        up, hp = pc.split("@")
                        pu, pp = up.split(":")
                        ph, pt = hp.split(":")
                        iq.set_proxy(proxy_type="http", host=ph, port=int(pt), user=pu, password=pp)
                except: pass
            logging.disable(logging.CRITICAL)
            iq.connect()
            IQ_CONNECTED=iq.check_connect()
            if IQ_CONNECTED:
                try:
                    iq.change_balance("PRACTICE"); time.sleep(1)
                    print(f"[IQ] SUCCESS BALANCE ${iq.get_balance()}")
                except: pass
                print("[IQ] CONNECTED TRUE"); return
            time.sleep(8)
        except Exception as e:
            print(f"[IQ] Fail {attempt+1}: {e}"); time.sleep(10)
    IQ_CONNECTED=False

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
                    up, hp = pc.split("@"); pu, pp = up.split(":"); ph, pt = hp.split(":")
                    iq.set_proxy(proxy_type="http", host=ph, port=int(pt), user=pu, password=pp)
            except: pass
        iq.connect(); IQ_CONNECTED=iq.check_connect()
        return IQ_CONNECTED
    except: IQ_CONNECTED=False; return False

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
        mins = now.hour*60 + now.minute; weekday = now.weekday()
        if 810 <= mins <= 870: return True, "US News 13:30-14:30 WAT"
        if 540 <= mins <= 570: return True, "London Open 09:00-09:30"
        if 870 <= mins <= 900: return True, "NY Open 14:30-15:00"
        if weekday == 4 and now.day <= 7 and 810 <= mins <= 900: return True, "NFP Friday"
        return False, ""
    except: return False, ""

# ===== REAL MARKET V13 =====
def analyze_sniper_v12(pair):
    df = get_candles(pair)
    if df is None: return None
    try:
        df5 = None
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL); c5 = iq.get_candles(pair, 300, 30, time.time())
            if c5 and len(c5) > 20: df5 = pd.DataFrame(sorted(c5, key=lambda x: x['from']))
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
        if adx < 18: return {"pair":pair,"dir":sig,"conf":42,"price":c_now,"rsi":r7,"reason":"Choppy - ADX Low","payout":payout,"atr":atr,"df":df.tail(30)}
        if body < atr*0.30: return {"pair":pair,"dir":sig,"conf":48,"price":c_now,"rsi":r7,"reason":"Doji - No Body","payout":payout,"atr":atr,"df":df.tail(30)}
        if payout < 0.70: return {"pair":pair,"dir":sig,"conf":52,"price":c_now,"rsi":r7,"reason":f"Low Payout {int(payout*100)}%","payout":payout,"atr":atr,"df":df.tail(30)}
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
        return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":reason,"payout":payout,"atr":atr,"df":df.tail(30)}
    except Exception as e:
        print(f"V12 err {pair} {e}"); return None

def analyze_sniper_v13(pair):
    is_news, news_reason = is_news_time()
    if is_news:
        try: df_tmp = get_candles(pair); price_tmp = float(df_tmp['close'].iloc[-1]) if df_tmp is not None else 0
        except: price_tmp = 0
        return {"pair":pair,"dir":"CALL","conf":35,"price":price_tmp,"rsi":50,"reason":f"NEWS BLOCK - {news_reason}","payout":0.85,"atr":0,"df":None}
    d = analyze_sniper_v12(pair)
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
            if "BB Breakout" not in reason or "Vol Spike" not in reason: conf -= 15; reason += " | Near Resistance - Risky"
            else: conf += 5; reason += " | Resistance Breakout + Vol"
        if not is_green and (dist_to_sup < 0.8 or dist_to_s20 < 0.8):
            if "BB Breakout" not in reason or "Vol Spike" not in reason: conf -= 15; reason += " | Near Support - Risky"
            else: conf += 5; reason += " | Support Breakout + Vol"
        if is_green and dist_to_sup < 1.5: conf += 7; reason += " | Bounce from Support"
        if not is_green and dist_to_res < 1.5: conf += 7; reason += " | Rejection from Resistance"
        conf = max(40, min(96, conf))
        return {"pair":pair,"dir":d['dir'],"conf":conf,"price":c_now,"rsi":d['rsi'],"reason":reason,"payout":d['payout'],"atr":atr,"df":d.get('df')}
    except Exception as e:
        print(f"V13 err {pair} {e}"); return d

# ===== OTC FUNCTION - YOUR OTC PAIRS, STRICT =====
def analyze_otc_v13(pair):
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
        if adx < 22: return {"pair":pair,"dir":sig,"conf":42,"price":c_now,"rsi":r7,"reason":"OTC Choppy - ADX Low","payout":payout,"atr":atr,"df":df.tail(30)}
        if body < atr*0.35: return {"pair":pair,"dir":sig,"conf":48,"price":c_now,"rsi":r7,"reason":"OTC Doji - No Body","payout":payout,"atr":atr,"df":df.tail(30)}
        if payout < 0.80: return {"pair":pair,"dir":sig,"conf":52,"price":c_now,"rsi":r7,"reason":f"OTC Low Payout {int(payout*100)}%","payout":payout,"atr":atr,"df":df.tail(30)}
        if is_green and (r7 > 68 or r7 < 50): return {"pair":pair,"dir":sig,"conf":55,"price":c_now,"rsi":r7,"reason":f"OTC RSI Not Safe {r7:.0f}","payout":payout,"atr":atr,"df":df.tail(30)}
        if not is_green and (r7 < 32 or r7 > 50): return {"pair":pair,"dir":sig,"conf":55,"price":c_now,"rsi":r7,"reason":f"OTC RSI Not Safe {r7:.0f}","payout":payout,"atr":atr,"df":df.tail(30)}
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
            return {"pair":pair,"dir":sig,"conf":58,"price":c_now,"rsi":r7,"reason":"OTC No Candle Pattern - Skip","payout":payout,"atr":atr,"df":df.tail(30)}
        if is_green and stoch_val > 80: score-=15
        if not is_green and stoch_val < 20: score-=15
        if is_green and 50 < stoch_val < 75: score+=6
        if not is_green and 25 < stoch_val < 50: score+=6
        if is_green and c_now > upper: score+=3; reasons.append("OTC BB Break")
        if not is_green and c_now < lower: score+=3; reasons.append("OTC BB Break")
        score = max(40, min(97, score)); reason = " + ".join(reasons) if reasons else "OTC Weak"
        return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":reason,"payout":payout,"atr":atr,"df":df.tail(30)}
    except Exception as e:
        print(f"OTC V13 err {pair} {e}"); return None

# ===== UNIFIED ANALYZE - AUTO PICK BRAIN =====
def analyze_momentum(pair):
    if pair.endswith("-OTC"):
        return analyze_otc_v13(pair)
    else:
        return analyze_sniper_v13(pair)

def iq_trade(pair,direction,amount,bal):
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL); iq.change_balance(bal)
            try:
                _,oid=iq.buy_blitz(pair,amount,direction.lower(),120)
                return True,oid,120
            except:
                _,oid=iq.buy(amount,pair,direction.lower(),2)
                return True,oid,120
    except Exception as e:
        print(f"Trade err {e}"); return False,None,0

@bot.message_handler(commands=['start'])
def start(m):
    if not is_allowed(m.from_user.id): bot.send_message(m.chat.id,"❌ Private"); return
    mk=types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton("💹 TRADE NOW", callback_data="trade"))
    mk.add(types.InlineKeyboardButton("📊 MY STATS", callback_data="stats"), types.InlineKeyboardButton("⚙️ SETTINGS", callback_data="settings"))
    txt=f"""🤖 **Z-BOT PRO V48 + V13** 🤖

✨ *REAL V13 + OTC V13-OTC Strict*

💎 IQ Connected: {'✅' if IQ_CONNECTED else '❌ Retrying...'}
💰 Balance: ${STATS['balance']:.2f}
📍 {get_mode_text()}
🎯 Win Rate: {STATS['wins']}/{STATS['wins']+STATS['loss'] if STATS['wins']+STATS['loss']>0 else 0}

**REAL:** V13 - 88%+ | 2 Min
**OTC:** V13-OTC Strict - 91%+ | 2 Min

👇 **Click TRADE to Start**
"""
    bot.send_message(m.chat.id, txt, reply_markup=mk, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_allowed(c.from_user.id): bot.answer_callback_query(c.id,"❌ Private"); return
    data=c.data; cid=c.message.chat.id
    if data=="trade":
        bot.answer_callback_query(c.id, "📋 Loading...")
        mk=types.InlineKeyboardMarkup(row_width=1)
        mk.add(types.InlineKeyboardButton("📈 TRADE REAL (8) - V13", callback_data="trade_real"))
        mk.add(types.InlineKeyboardButton("📈 TRADE OTC (8) - V13-OTC STRICT", callback_data="trade_otc"))
        mk.add(types.InlineKeyboardButton("⬅️ BACK", callback_data="back_start"))
        bot.send_message(cid, f"💹 **SELECT MARKET**\n\n📍 {get_mode_text()}\n\n👇 Choose:", reply_markup=mk, parse_mode="Markdown")
        return
    if data=="back_start":
        bot.send_message(cid, "Send /start again"); return
    if data=="trade_real":
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in REAL_PAIRS:
            mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"pair_{p}"))
        mk.add(types.InlineKeyboardButton("⬅️ BACK", callback_data="trade"))
        bot.send_message(cid, "💹 **REAL - SELECT PAIR (V13)**\n\n👇 Choose:", reply_markup=mk, parse_mode="Markdown")
        return
    if data=="trade_otc":
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in OTC_PAIRS:
            mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"pair_{p}"))
        mk.add(types.InlineKeyboardButton("⬅️ BACK", callback_data="trade"))
        bot.send_message(cid, "💹 **OTC - SELECT PAIR (V13-OTC STRICT)**\n\n👇 Choose:", reply_markup=mk, parse_mode="Markdown")
        return
    if data.startswith("pair_"):
        pair=data.replace("pair_","")
        bot.answer_callback_query(c.id, f"{pair} selected")
        user_states[cid]={"pair":pair}
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🟢 DEMO ACCOUNT", callback_data=f"bal_PRACTICE_{pair}"))
        mk.add(types.InlineKeyboardButton("🔴 REAL ACCOUNT", callback_data=f"bal_REAL_{pair}"))
        mk.add(types.InlineKeyboardButton("⬅️ BACK", callback_data="trade"))
        bot.send_message(cid, f"✅ **PAIR: {PAIR_EMOJI.get(pair,pair)}**\n\n💳 **STEP 2/3 - SELECT ACCOUNT**\n\n👇 Choose account type:", reply_markup=mk, parse_mode="Markdown")
        return
    if data.startswith("bal_"):
        parts=data.split("_"); bal=parts[1]; pair=parts[2]
        bot.answer_callback_query(c.id, f"{bal}")
        user_states[cid]={"pair":pair,"bal":bal}
        mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("💵 $1", callback_data=f"amt_1_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $5", callback_data=f"amt_5_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $10", callback_data=f"amt_10_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("💵 $20", callback_data=f"amt_20_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $50", callback_data=f"amt_50_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $100", callback_data=f"amt_100_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("✏️ CUSTOM AMOUNT", callback_data=f"custom_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("⬅️ BACK", callback_data=f"pair_{pair}"))
        bot.send_message(cid, f"✅ **PAIR: {PAIR_EMOJI.get(pair,pair)}**\n✅ **ACCOUNT: {bal}**\n\n💰 **STEP 3/3 - SELECT AMOUNT**\n\n👇 Choose investment:", reply_markup=mk, parse_mode="Markdown")
        return
    if data.startswith("amt_") or data.startswith("custom_"):
        if data.startswith("custom_"):
            parts=data.split("_"); pair=parts[1]; bal=parts[2]
            user_states[cid]={"pair":pair,"bal":bal,"step":"await_amt"}
            bot.send_message(cid, f"✏️ **Type your amount**\n\nExample: `10` or `100`\n\nFor {pair} {bal}", parse_mode="Markdown")
            return
        parts=data.split("_"); amt=float(parts[1]); pair=parts[2]; bal=parts[3]
        bot.answer_callback_query(c.id, f"Analyzing {pair}...")
        is_otc = pair.endswith("-OTC")
        brain = "V13-OTC STRICT" if is_otc else "V13 REAL"
        min_conf = 91 if is_otc else 88
        bot.send_message(cid, f"""🔍 **ANALYZING {PAIR_EMOJI.get(pair,pair)} - {brain}**

⏳ Checking momentum...
⏳ Reading candles...
⏳ Calculating RSI & EMA...

Please wait 2 seconds...""", parse_mode="Markdown")
        d=analyze_momentum(pair)
        if not d:
            mk=types.InlineKeyboardMarkup()
            mk.add(types.InlineKeyboardButton("🔄 RETRY", callback_data=f"amt_{int(amt)}_{pair}_{bal}"))
            bot.send_message(cid, f"❌ Failed to analyze {pair}\nTap retry", reply_markup=mk)
            return
        # BLOCK LOW CONF - V13 / OTC STRICT
        if d['conf'] < min_conf:
            mk=types.InlineKeyboardMarkup()
            mk.add(types.InlineKeyboardButton("🔄 RETRY", callback_data=f"amt_{int(amt)}_{pair}_{bal}"))
            mk.add(types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"))
            bot.send_message(cid, f"""⛔ **NO SAFE TRADE - {brain} BLOCKED**

💱 {PAIR_EMOJI.get(pair,pair)}
📊 Conf: {d['conf']:.0f}% < {min_conf}% needed
🛡️ {d['reason']}

Wait for better setup, tap RETRY.""", reply_markup=mk, parse_mode="Markdown")
            return
        dir_emoji = "🟢 CALL - BUY 🟢" if d['dir']=="CALL" else "🔴 PUT - SELL 🔴"
        signal_txt=f"""━━━━━━━━━━━━━━━
📡 **SIGNAL FOUND - {brain}**
━━━━━━━━━━━━━━━

💱 **Pair:** {PAIR_EMOJI.get(pair,pair)}
📊 **Direction:** {dir_emoji}
🎯 **Confidence:** {d['conf']:.0f}% (Min {min_conf}%)
💸 **Payout:** {int(d['payout']*100)}%
💰 **Amount:** ${amt} {bal}
⏱️ **Expiry:** 2 Min

📈 **Analysis:** {d['reason']}
📍 **Price:** {d['price']:.5f}
📊 **RSI:** {d['rsi']:.0f}

━━━━━━━━━━━━━━━
🤖 **AUTO PLACING TRADE...**
━━━━━━━━━━━━━━━
"""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            plt.figure(figsize=(6,3)); plt.plot(d['df']['close'], color='#FFD700', linewidth=2); plt.title(f"{pair} {d['dir']} {d['conf']:.0f}%"); plt.grid(alpha=0.3); plt.tight_layout(); p="/tmp/c.png"; plt.savefig(p); plt.close()
            bot.send_photo(cid, open(p,'rb'), caption=signal_txt, parse_mode="Markdown")
        except:
            bot.send_message(cid, signal_txt, parse_mode="Markdown")
        time.sleep(1)
        bot.send_message(cid, f"🚀 **PLACING TRADE NOW...**\n\n💱 {pair} | {d['dir']} | ${amt}\n🔄 Connecting to IQ Option...", parse_mode="Markdown")
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal)
        if not ok:
            bot.send_message(cid, "❌ **Trade Failed - Reconnecting**\nTry again"); iq_reconnect(); return
        bot.send_message(cid, f"""✅ **TRADE PLACED SUCCESSFULLY!**

━━━━━━━━━━━━━━━
🆔 **Order ID:** `{oid}`
💱 **Pair:** {pair}
📊 **Direction:** {d['dir']}
💰 **Amount:** ${amt}
⏱️ **Expiry:** {exp} seconds (2 Min)
💳 **Account:** {bal}
━━━━━━━━━━━━━━━

⏳ **INITIALIZING... WAIT 2 MIN**
🕐 Trade is running...

I will send result in 2 minutes...
""", parse_mode="Markdown")
        time.sleep(exp+5)
        try:
            with IQ_LOCK: pnl=iq.check_win_v4(oid)
            if pnl>0:
                STATS['wins']+=1; STATS['balance']+=pnl; STATS['streak']+=1
                mk=types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton("🔁 TRADE AGAIN SAME", callback_data=f"amt_{int(amt)}_{pair}_{bal}"),
                       types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"))
                bot.send_message(cid, f"""✅ **WINNER! ✅**

━━━━━━━━━━━━━━━
💰 **Profit:** +${pnl:.2f}
💱 **Pair:** {pair} {d['dir']}
💵 **New Balance:** ${STATS['balance']:.2f}
📊 **Result:** WIN
━━━━━━━━━━━━━━━

🎉 Congratulations!
""", reply_markup=mk, parse_mode="Markdown")
            else:
                STATS['loss']+=1; STATS['balance']-=amt; STATS['streak']=0
                mk=types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton(f"🔁 MARTINGALE ${amt*2.2:.0f}", callback_data=f"amt_{int(amt*2.2)}_{pair}_{bal}"),
                       types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"))
                bot.send_message(cid, f"""❌ **LOSS**

━━━━━━━━━━━━━━━
💸 **Loss:** -${amt:.2f}
💱 **Pair:** {pair} {d['dir']}
💵 **Balance:** ${STATS['balance']:.2f}
📊 **Result:** LOSS
━━━━━━━━━━━━━━━

💪 Don't give up! Try Martingale
""", reply_markup=mk, parse_mode="Markdown")
        except:
            mk=types.InlineKeyboardMarkup()
            mk.add(types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"))
            bot.send_message(cid, f"⏱️ **TRADE EXPIRED**\n\nCheck IQ Option app for result\nID: {oid}\n\nTap new trade", reply_markup=mk)
        return
    if data=="stats":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0
        bot.send_message(cid, f"📊 **STATS**\n\n🏆 Wins: {STATS['wins']}\n❌ Loss: {STATS['loss']}\n📈 Winrate: {wr:.1f}%\n💰 Balance: ${STATS['balance']:.2f}\n📍 {get_mode_text()}", parse_mode="Markdown")
    if data=="settings":
        bot.send_message(cid, "⚙️ **SETTINGS**\n\n🛡️ REAL: V13 - 5M Trend + ADX + MACD + Stochastic + BB + Volume + Payout + SR + News Filter - 88%+\n🛡️ OTC: V13-OTC Strict - EMA Full Align + ADX 22+ + RSI Tight + Pin/Engulf MUST + No Volume/SR - 91%+\n⏱️ Expiry: FIXED 2 Min\n📊 REAL: 8 Pairs | OTC: 8 Pairs")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get("step")=="await_amt")
def handle_custom_amt(m):
    cid=m.chat.id; st=user_states.get(cid, {})
    if not is_allowed(m.from_user.id): return
    try:
        amt=float(m.text.strip())
        pair=st.get("pair"); bal=st.get("bal")
        if not pair: return
        d=analyze_momentum(pair)
        if not d: bot.send_message(cid, "Failed analyze"); return
        min_conf = 91 if pair.endswith("-OTC") else 88
        if d['conf'] < min_conf:
            bot.send_message(cid, f"⛔ Blocked {d['conf']:.0f}% < {min_conf}% - {d['reason']}\nTry again"); return
        dir_emoji = "🟢 CALL - BUY 🟢" if d['dir']=="CALL" else "🔴 PUT - SELL 🔴"
        bot.send_message(cid, f"📡 **SIGNAL** {PAIR_EMOJI.get(pair,pair)} {dir_emoji} {d['conf']:.0f}% ${amt} - {d['reason']}")
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal)
        if ok:
            bot.send_message(cid, f"✅ Placed {oid}\n⏳ Initializing wait {exp} sec...")
            time.sleep(exp+5)
            try:
                with IQ_LOCK: pnl=iq.check_win_v4(oid)
                if pnl>0: bot.send_message(cid, f"✅ WIN +${pnl:.2f}")
                else: bot.send_message(cid, f"❌ LOSS -${amt}")
            except: bot.send_message(cid, "Check IQ app")
        user_states.pop(cid,None)
    except: bot.send_message(cid, "❌ Send number only, e.g 100")

threading.Thread(target=background_iq, daemon=True).start()

if __name__ == "__main__":
    try:
        url=os.getenv("RENDER_EXTERNAL_URL")
        if url and BOT_TOKEN:
            requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={url}/{BOT_TOKEN}", timeout=5)
            print(f"Webhook set {url}")
    except: pass
    port=int(os.getenv("PORT",10000))
    print(f"Starting Flask on 0.0.0.0:{port} - V48 + V13 + OTC STRICT")
    app.run(host="0.0.0.0", port=port, threaded=True)
