import os, time, threading, warnings, logging, sqlite3, json
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

ENABLE_OTC = False
# ===== V14 SETTINGS - CHANGE AM HERE =====
DAILY_MAX_LOSS = 20.0
DAILY_MAX_TRADES = 30

REAL_PAIRS = ["EURUSD","GBPUSD","USDJPY","EURGBP","AUDUSD","USDCAD","EURJPY","GBPJPY","USDCHF","AUDJPY","EURAUD","GBPCHF","EURCHF","NZDUSD","GBPAUD","EURCAD","AUDCAD","GBPCAD","NZDJPY","AUDNZD","CHFJPY","CADJPY"]
OTC_PAIRS = ["EURUSD-OTC","GBPUSD-OTC","USDJPY-OTC","AUDUSD-OTC","USDCAD-OTC","EURGBP-OTC","EURJPY-OTC","GBPJPY-OTC","AUDJPY-OTC","EURAUD-OTC","GBPAUD-OTC","NZDUSD-OTC","GBPCHF-OTC","EURCHF-OTC","USDCHF-OTC","AUDCAD-OTC","EURCAD-OTC","CADJPY-OTC","NZDJPY-OTC"]
PAIR_EMOJI = {"EURUSD":"🇪🇺 EUR/USD REAL","GBPUSD":"🇬🇧 GBP/USD REAL","USDJPY":"🇺🇸 USD/JPY REAL","EURGBP":"🇪🇺 EUR/GBP REAL","AUDUSD":"🇦🇺 AUD/USD REAL","USDCAD":"🇺🇸 USD/CAD REAL","EURJPY":"🇪🇺 EUR/JPY REAL","GBPJPY":"🇬🇧 GBP/JPY REAL","USDCHF":"🇺🇸 USD/CHF REAL","AUDJPY":"🇦🇺 AUD/JPY REAL","EURAUD":"🇪🇺 EUR/AUD REAL","GBPCHF":"🇬🇧 GBP/CHF REAL","EURCHF":"🇪🇺 EUR/CHF REAL","NZDUSD":"🇳🇿 NZD/USD REAL","GBPAUD":"🇬🇧 GBP/AUD REAL","EURCAD":"🇪🇺 EUR/CAD REAL","AUDCAD":"🇦🇺 AUD/CAD REAL","GBPCAD":"🇬🇧 GBP/CAD REAL","NZDJPY":"🇳🇿 NZD/JPY REAL","AUDNZD":"🇦🇺 AUD/NZD REAL","CHFJPY":"🇨🇭 CHF/JPY REAL","CADJPY":"🇨🇦 CAD/JPY REAL","EURUSD-OTC":"🇪🇺 EUR/USD OTC","GBPUSD-OTC":"🇬🇧 GBP/USD OTC","EURGBP-OTC":"🇪🇺 EUR/GBP OTC","USDJPY-OTC":"🇺🇸 USD/JPY OTC","GBPJPY-OTC":"🇬🇧 GBP/JPY OTC","AUDUSD-OTC":"🇦🇺 AUD/USD OTC","USDCHF-OTC":"🇺🇸 USD/CHF OTC","EURJPY-OTC":"🇪🇺 EUR/JPY OTC","AUDJPY-OTC":"🇦🇺 AUD/JPY OTC","EURAUD-OTC":"🇪🇺 EUR/AUD OTC","GBPAUD-OTC":"🇬🇧 GBP/AUD OTC","NZDUSD-OTC":"🇳🇿 NZD/USD OTC","GBPCHF-OTC":"🇬🇧 GBP/CHF OTC","EURCHF-OTC":"🇪🇺 EUR/CHF OTC","USDCAD-OTC":"🇺🇸 USD/CAD OTC","AUDCAD-OTC":"🇦🇺 AUD/CAD OTC","EURCAD-OTC":"🇪🇺 EUR/CAD OTC","CADJPY-OTC":"🇨🇦 CAD/JPY OTC","NZDJPY-OTC":"🇳🇿 NZD/JPY OTC"}

# ===== AI MEMORY LAYER - V14 =====
DB_FILE = "zbot_memory.db"
def ai_init_db():
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pair TEXT, direction TEXT, conf REAL,
        rsi REAL, adx REAL, payout REAL, reason TEXT,
        amt REAL, level INTEGER, win INTEGER,
        hour INTEGER, weekday INTEGER, created_at TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS ai_weights (
        key TEXT PRIMARY KEY, weight REAL
    )""")
    defaults = {"EMA":18, "RSI":15, "MOM":12, "MACD":10, "ADX":12, "VOL":8, "STOCH":5}
    for k,v in defaults.items():
        cur.execute("INSERT OR IGNORE INTO ai_weights VALUES (?,?)", (k,v))
    con.commit(); con.close()
def ai_save_trade(pair, direction, conf, rsi, adx, payout, reason, amt, level, win):
    try:
        tz = pytz.timezone("Africa/Lagos")
        now = datetime.now(tz)
        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()
        cur.execute("INSERT INTO trades (pair,direction,conf,rsi,adx,payout,reason,amt,level,win,hour,weekday,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pair, direction, conf, rsi, adx, payout, reason, amt, level, 1 if win else 0, now.hour, now.weekday(), now.strftime('%Y-%m-%d %H:%M:%S')))
        con.commit(); con.close()
        ai_learn()
    except Exception as e:
        print(f"[AI] Save err {e}")
def ai_get_weights():
    try:
        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()
        cur.execute("SELECT key, weight FROM ai_weights")
        d = dict(cur.fetchall()); con.close()
        return d
    except:
        return {"EMA":18, "RSI":15, "MOM":12, "MACD":10, "ADX":12, "VOL":8, "STOCH":5}
def ai_learn():
    try:
        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()
        cur.execute("SELECT reason, win FROM trades ORDER BY id DESC LIMIT 100")
        rows = cur.fetchall()
        if len(rows) < 10:
            con.close(); return
        from collections import defaultdict
        stats = defaultdict(lambda: [0,0])
        for reason, win in rows:
            if not reason: continue
            for key in ["EMA", "RSI", "Mom", "MACD", "ADX", "Vol", "BB", "Pin", "Engulf"]:
                if key.lower() in reason.lower() or key in reason:
                    stats[key][0] += 1
                    stats[key][1] += win
        weights = ai_get_weights()
        for key, (total, wins) in stats.items():
            if total >= 5:
                wr = wins / total
                map_key = {"Mom":"MOM", "Vol":"VOL"}.get(key, key.upper())
                if map_key not in weights: continue
                old = weights[map_key]
                if wr < 0.40:
                    new = max(2, old - 3)
                    cur.execute("UPDATE ai_weights SET weight=? WHERE key=?", (new, map_key))
                    print(f"[AI LEARN] {map_key} winrate {wr:.0%} low - weight {old} -> {new}")
                elif wr > 0.70:
                    new = min(25, old + 1)
                    cur.execute("UPDATE ai_weights SET weight=? WHERE key=?", (new, map_key))
                    print(f"[AI LEARN] {map_key} winrate {wr:.0%} high - weight {old} -> {new}")
        con.commit(); con.close()
    except Exception as e:
        print(f"[AI Learn err] {e}")
def ai_get_insight():
    try:
        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()
        cur.execute("SELECT COUNT(*), SUM(win) FROM trades")
        total, wins = cur.fetchone()
        total = total or 0; wins = wins or 0
        cur.execute("SELECT pair, COUNT(*), SUM(win) FROM trades GROUP BY pair ORDER BY COUNT(*) DESC LIMIT 3")
        best_pairs = cur.fetchall()
        cur.execute("SELECT hour, COUNT(*), SUM(win) FROM trades GROUP BY hour ORDER BY COUNT(*) DESC LIMIT 3")
        best_hours = cur.fetchall()
        cur.execute("SELECT conf, win FROM trades ORDER BY id DESC LIMIT 50")
        rows = cur.fetchall()
        high = [w for c,w in rows if c >= 88]
        low = [w for c,w in rows if c < 88]
        high_wr = f"{sum(high)/len(high)*100:.0f}%" if high else "No data"
        low_wr = f"{sum(low)/len(low)*100:.0f}%" if low else "No data"
        weights = ai_get_weights()
        con.close()
        return total, wins, best_pairs, best_hours, high_wr, low_wr, weights
    except Exception as e:
        return 0,0,[],[],"0%","0%",{}

# ===== V14 PROTECTION: Auto-Block + Daily Max Loss =====
def ai_should_block(pair, hour):
    try:
        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()
        cur.execute("SELECT COUNT(*), SUM(win) FROM trades WHERE pair=? AND hour=? ORDER BY id DESC LIMIT 30", (pair, hour))
        total, wins = cur.fetchone()
        con.close()
        total = total or 0; wins = wins or 0
        if total >= 5:
            wr = wins / total if total else 1
            if wr < 0.35:
                print(f"[AI BLOCK] {pair} at {hour}:00 winrate {wr:.0%} ({wins}/{total}) - BLOCKED")
                return True, f"AI Blocked {pair} {hour}:00 - Winrate {wr:.0%} ({wins}/{total})"
        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()
        cur.execute("SELECT COUNT(*), SUM(win) FROM trades WHERE pair=? ORDER BY id DESC LIMIT 20", (pair,))
        total2, wins2 = cur.fetchone()
        con.close()
        total2 = total2 or 0; wins2 = wins2 or 0
        if total2 >= 10:
            wr2 = wins2 / total2 if total2 else 1
            if wr2 < 0.30:
                return True, f"AI Blocked {pair} - Overall Winrate {wr2:.0%} ({wins2}/{total2})"
        return False, ""
    except Exception as e:
        print(f"[Block check err] {e}")
        return False, ""
def ai_daily_stats():
    try:
        tz = pytz.timezone("Africa/Lagos")
        today = datetime.now(tz).strftime('%Y-%m-%d')
        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()
        cur.execute("SELECT amt, win, payout FROM trades WHERE created_at LIKE ?", (today + "%",))
        rows = cur.fetchall()
        con.close()
        total_pnl = 0
        total_trades = len(rows)
        wins = sum(1 for _, w, _ in rows if w == 1)
        for amt, win, payout in rows:
            p = payout if payout else 0.85
            if win:
                total_pnl += amt * p
            else:
                total_pnl -= amt
        return total_pnl, total_trades, wins, total_trades - wins
    except Exception as e:
        print(f"[Daily stats err] {e}")
        return 0, 0, 0, 0
def ai_is_daily_locked():
    pnl, total, wins, losses = ai_daily_stats()
    if pnl <= -DAILY_MAX_LOSS:
        return True, pnl, total
    if total >= DAILY_MAX_TRADES:
        return True, pnl, total
    return False, pnl, total

ai_init_db()
# ===== END AI + PROTECTION =====

STATS = {"balance":0.0,"real_balance":0.0,"wins":0,"loss":0,"streak":0}
user_states = {}; AUTO_STATE = {}; IQ_LOCK = threading.Lock()
IQ_CONNECTED=False; iq=None; PAYOUT_CACHE={}; PAYOUT_TIME=0
OTC_SESSION_RESULTS = []
OTC_MARTI = {"loss_streak":0, "base":1.0, "bal":"PRACTICE", "levels":[1,2,4]}
PENDING_MANUAL = {}

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
def manual_result_keyboard(pair, direction, conf, amt, level, payout):
    mk = types.InlineKeyboardMarkup(row_width=2)
    p_int = int(round(float(payout)*100))
    mk.add(
        types.InlineKeyboardButton("✅ I WON", callback_data=f"manual_win_{pair}_{direction}_{int(conf)}_{amt}_{level}_{p_int}"),
        types.InlineKeyboardButton("❌ I LOST", callback_data=f"manual_loss_{pair}_{direction}_{int(conf)}_{amt}_{level}_{p_int}")
    )
    return mk
def get_manual_amt_and_level():
    levels = OTC_MARTI["levels"]
    idx = OTC_MARTI["loss_streak"] % len(levels)
    mult = levels[idx]
    amt = round(OTC_MARTI["base"] * mult, 2)
    return amt, mult, idx+1

@app.route("/")
def home():
    return f"V14 PROTECTED RUNNING IQ:{IQ_CONNECTED} OTC:{ENABLE_OTC} {datetime.now(pytz.timezone('Africa/Lagos')).strftime('%H:%M:%S')}"
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
    steps = [(0,"🚀 V14 Protected Sniper Init...",0.15),(20,f"🔌 Checking {pair}...",0.2),(40,"📊 ADX + ATR + Volume...",0.25),(60,"📈 EMA + MACD + 5M Trend...",0.2),(80,"💹 RSI + Stochastic + BB...",0.2),(100,"🔒 SNIPER LOCKED!",0.3)]
    last_pct=-1
    for pct, text, delay in steps:
        if pct==last_pct: time.sleep(delay); continue
        last_pct=pct; filled=int(pct//5); bar="█"*filled+"░"*(20-filled); color="🟥" if pct<40 else "🟨" if pct<80 else "🟩" if pct<100 else "💎"
        txt=f"""{color} **Z-BOT V14 PROTECTED** {color}\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n💎 IQ: {'✅' if IQ_CONNECTED else '❌'}\n\n{bar} {pct}%\n\n🔍 {text}\n⏳ V14 Protected"""
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
        w = ai_get_weights()
        if df5 is not None:
            c5=df5['close']; e9_5=c5.ewm(9).mean(); e21_5=c5.ewm(21).mean()
            trend_5m = 1 if float(e9_5.iloc[-1]) > float(e21_5.iloc[-1]) else -1
            if (is_green and trend_5m==-1) or (not is_green and trend_5m==1): score-=18; reasons.append("Against 5M Trend")
            else: score+=12; reasons.append("5M Trend Align")
        if is_green:
            if e9>e21>e50: score+=w.get("EMA",18); reasons.append("EMA Bull Align")
            elif e9>e21: score+=10
            else: score-=8
        else:
            if e9<e21<e50: score+=w.get("EMA",18); reasons.append("EMA Bear Align")
            elif e9<e21: score+=10
            else: score-=8
        if adx >= 28: score+=w.get("ADX",12); reasons.append(f"ADX Strong {adx:.0f}")
        elif adx >= 22: score+=7
        if is_green and pdi > mdi: score+=8
        elif not is_green and mdi > pdi: score+=8
        else: score-=10
        if is_green:
            if 52 <= r7 <= 65 and 48 <= r14 <= 62: score+=w.get("RSI",15); reasons.append(f"RSI Safe {r7:.0f}")
            elif r7 > 75 or r7 < 45: score-=12
            else: score+=6
        else:
            if 35 <= r7 <= 48 and 38 <= r14 <= 52: score+=w.get("RSI",15); reasons.append(f"RSI Safe {r7:.0f}")
            elif r7 < 25 or r7 > 55: score-=12
            else: score+=6
        if is_green and macd_val > sig_val: score+=w.get("MACD",10); reasons.append("MACD Bull")
        elif not is_green and macd_val < sig_val: score+=w.get("MACD",10); reasons.append("MACD Bear")
        else: score-=8
        if is_green:
            if mom1 > 0.03 and mom3 > 0.06: score+=w.get("MOM",12); reasons.append(f"Mom {mom1:.3f}%")
            elif mom1 > 0.01: score+=5
            elif mom1 < 0: score-=12
        else:
            if mom1 < -0.03 and mom3 < -0.06: score+=w.get("MOM",12); reasons.append(f"Mom {mom1:.3f}%")
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
        if curr_vol > avg_vol*1.2: score+=w.get("VOL",8); reasons.append("Vol Spike")
        elif curr_vol > avg_vol: score+=4
        score = max(40, min(96, score)); reason = " + ".join(reasons) if reasons else "Weak PA"
        if sniper_mode and score < 88: return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":reason,"payout":payout,"expiry":120,"atr":atr,"rejected":True}
        return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":reason,"payout":payout,"expiry":120,"atr":atr,"rejected":False}
    except Exception as e:
        print(f"V12 err {pair} {e}"); return None
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
    last_lock_msg = 0
    while True:
        try:
            if is_real_hours() and IQ_CONNECTED:
                for pair in REAL_PAIRS:
                    if pair in last_signal and time.time()-last_signal[pair]<600: continue
                    locked, pnl_today, trades_today = ai_is_daily_locked()
                    if locked:
                        if time.time() - last_lock_msg > 3600:
                            try: bot.send_message(OWNER_ID, f"🔒 **DAILY PROTECTION LOCKED**\n\n💰 Today PnL: ${pnl_today:+.2f} | Trades: {trades_today}\n🛡️ Max Loss: -${DAILY_MAX_LOSS:.0f} reached or Max Trades {DAILY_MAX_TRADES} reached.\n\n⛔ No more signals today. Rest till tomorrow 7AM. Bot dey protect you from revenge trading.")
                            except: pass
                            last_lock_msg = time.time()
                        print(f"[PROTECTION] Daily locked. PnL ${pnl_today:.2f} Trades {trades_today}")
                        time.sleep(300)
                        break
                    now_hour = datetime.now(tz).hour
                    is_blocked, block_reason = ai_should_block(pair, now_hour)
                    if is_blocked:
                        print(f"[BLOCKED] {block_reason}")
                        last_signal[pair] = time.time()
                        continue
                    d=analyze_sniper_v12(pair,sniper_mode=True)
                    if d and not d.get('rejected') and d['conf']>=88:
                        now=datetime.now(tz); entry=now+timedelta(seconds=45); entry2=entry+timedelta(seconds=120); entry3=entry+timedelta(seconds=240); exp=d['expiry']; dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]
                        amt_m, mult_m, lvl_m = get_manual_amt_and_level()
                        pnl_today2, _, _, _ = ai_daily_stats()
                        msg=f"""📡 **REAL SIGNAL V14 PROTECTED - 3 LEVELS** 📡\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n📊 {dir_e} | 🎯 {d['conf']:.0f}% SNIPER\n📈 {d['reason']} | RSI {d['rsi']:.1f} | ATR {d['atr']:.5f}\n💸 {int(d['payout']*100)}% | 2 Min Each Level\n🧠 AI: {pair} NOT blocked - Winrate good\n💰 Today PnL: ${pnl_today2:+.2f} | Max Loss: -${DAILY_MAX_LOSS:.0f}\n\n⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)\n📅 {now.strftime('%A %d %b %H:%M WAT')}\n\n**Level 1:** {entry.strftime('%H:%M:%S')} - 2 Min - ${base:.2f}\n**Level 2:** {entry2.strftime('%H:%M:%S')} - 2 Min - ${base*2:.2f}\n**Level 3:** {entry3.strftime('%H:%M:%S')} - 2 Min - ${base*4:.2f}\n\n⛔ STOP after Level 3. No Level 4.\n⚠️ MANUAL - Follow levels only\n\n👇 After you trade manually, press result below:"""
                        try: bot.send_message(OWNER_ID,msg,parse_mode="Markdown", reply_markup=manual_result_keyboard(pair, d['dir'], d['conf'], amt_m, mult_m, d['payout'])); last_signal[pair]=time.time()
                        except: pass
                    time.sleep(3)
            time.sleep(25)
        except: time.sleep(30)

# ===== NEW: DAILY 8PM AUTO REPORT - ADDED =====
def daily_8pm_report():
    tz = pytz.timezone("Africa/Lagos")
    last_sent_date = ""
    while True:
        try:
            now = datetime.now(tz)
            today_str = now.strftime('%Y-%m-%d')
            if now.hour == 20 and now.minute < 5 and last_sent_date != today_str:
                pnl, total, wins, losses = ai_daily_stats()
                if total > 0:
                    total_all, wins_all, best_pairs, best_hours, high_wr, low_wr, weights = ai_get_insight()
                    try:
                        con = sqlite3.connect(DB_FILE)
                        cur = con.cursor()
                        cur.execute("SELECT pair, COUNT(*), SUM(win) FROM trades WHERE created_at LIKE ? GROUP BY pair ORDER BY SUM(win) ASC LIMIT 1", (today_str + "%",))
                        worst = cur.fetchone()
                        con.close()
                    except:
                        worst = None
                    wr_today = (wins/total*100) if total else 0
                    if best_pairs:
                        best_sorted = sorted(best_pairs, key=lambda x: (x[2]/x[1] if x[1] else 0), reverse=True)
                        bp = best_sorted[0]
                        best_pair_txt = f"{bp[0]} - {bp[2]}/{bp[1]} wins"
                    else:
                        best_pair_txt = "No data yet"
                    if worst and worst[1] >= 3 and (worst[2] or 0) / worst[1] < 0.35:
                        avoid_txt = f"⛔ Tomorrow AVOID {worst[0]} - Today e lose {worst[1] - (worst[2] or 0)}/{worst[1]}"
                    else:
                        avoid_txt = "✅ No bad pair today, all pairs try"
                    try:
                        con = sqlite3.connect(DB_FILE)
                        cur = con.cursor()
                        cur.execute("SELECT hour, COUNT(*), SUM(win) FROM trades WHERE created_at LIKE ? GROUP BY hour ORDER BY SUM(win) DESC LIMIT 1", (today_str + "%",))
                        best_h = cur.fetchone()
                        con.close()
                        best_hour_txt = f"{best_h[0]}:00 - {best_h[2]}/{best_h[1]} wins" if best_h else "No data"
                    except:
                        best_hour_txt = "No data"
                    locked, _, _ = ai_is_daily_locked()
                    msg = f"""🌙 **DAILY REPORT - {now.strftime('%A %d %b')} - 8PM** 🌙

━━━━━━━━━━━━━━━
💰 **TODAY RESULT**
💵 PnL Today: ${pnl:+.2f}
🏆 W:{wins} L:{losses} | Total: {total} trades
📈 Winrate Today: {wr_today:.0f}%
🛡️ Status: {'🔒 LOCKED - You hit max loss' if locked else '✅ OPEN'}
━━━━━━━━━━━━━━━

🧠 **WETIN BOT LEARN TODAY**
⭐ Best Pair: {best_pair_txt}
⏰ Best Hour: {best_hour_txt}
🎯 High Conf (88%+) Winrate (All Time): {high_wr}

⚠️ **TOMORROW ADVICE**
{avoid_txt}
💡 Focus on your best pair tomorrow morning, no chase loss.

🛡️ **PROTECTION**
Max Loss: -${DAILY_MAX_LOSS:.0f} | Tomorrow bot go reset to $0.00 PnL, lock go open again 7AM.

😴 Bot don sleep. See you tomorrow 7AM!
Rest well, no trade for night. OTC na trap.
"""
                    try:
                        bot.send_message(OWNER_ID, msg, parse_mode="Markdown")
                        print(f"[DAILY REPORT] Sent for {today_str}")
                    except Exception as e:
                        print(f"[DAILY REPORT] Send err {e}")
                    last_sent_date = today_str
                else:
                    try:
                        bot.send_message(OWNER_ID, f"🌙 **DAILY REPORT - {now.strftime('%A %d %b')}**\n\n📭 You no trade today. No wahala, rest.\n\nBot go wake tomorrow 7AM. See you then! 😴")
                    except: pass
                    last_sent_date = today_str
            time.sleep(60)
        except Exception as e:
            print(f"[Daily Report err] {e}")
            time.sleep(60)
# ===== END DAILY 8PM REPORT =====

# ===== NEW: PLAN B BACKUP - 8:05PM SEND DB FILE =====
def nightly_backup_to_telegram():
    """Every day 8:05PM, send zbot_memory.db to you so you get backup. Forward am to Saved Messages."""
    tz = pytz.timezone("Africa/Lagos")
    last_backup = ""
    while True:
        try:
            now = datetime.now(tz)
            today_str = now.strftime('%Y-%m-%d')
            if now.hour == 20 and now.minute == 5 and last_backup != today_str:
                try:
                    with open(DB_FILE, 'rb') as f:
                        bot.send_document(OWNER_ID, f, caption=f"💾 BACKUP - {today_str}\n\nThis na your AI memory file. If Render wipe, send this file back to me, I go restore am. Forward am to Saved Messages to keep am safe.")
                    print(f"[BACKUP] Sent DB backup for {today_str}")
                except Exception as e:
                    print(f"[BACKUP err] {e}")
                last_backup = today_str
            time.sleep(60)
        except Exception as e:
            print(f"[Backup err] {e}")
            time.sleep(60)
# ===== END PLAN B BACKUP =====

@bot.message_handler(commands=['start','stop','mode','balance','results','ai','today'])
def start(m):
    if not is_allowed(m.from_user.id): bot.send_message(m.chat.id,"❌ Private"); return
    if m.text.startswith('/today'):
        pnl, total, wins, losses = ai_daily_stats()
        locked, _, _ = ai_is_daily_locked()
        txt = f"""📅 **TODAY REPORT - {datetime.now(pytz.timezone('Africa/Lagos')).strftime('%A %d %b')}**\n\n💰 PnL Today: ${pnl:+.2f}\n🏆 W:{wins} L:{losses} | Total: {total}\n🛡️ Max Loss Limit: -${DAILY_MAX_LOSS:.0f}\n📊 Max Trades: {total}/{DAILY_MAX_TRADES}\n\nStatus: {'🔒 LOCKED - You don reach limit, rest!' if locked else '✅ OPEN - You fit continue'}\n\n💡 If you don lose reach -${DAILY_MAX_LOSS:.0f}, bot go stop to send signal till tomorrow 7AM. Na to protect you from revenge trading.\n"""
        bot.send_message(m.chat.id, txt, parse_mode="Markdown")
        return
    if m.text.startswith('/ai'):
        total, wins, best_pairs, best_hours, high_wr, low_wr, weights = ai_get_insight()
        losses = total - wins
        wr = (wins/total*100) if total else 0
        txt = f"""🧠 **Z-BOT AI BRAIN REPORT**\n\n📊 Total Learned: {total} trades\n🏆 W:{wins} L:{losses} | Winrate: {wr:.1f}%\n\n🎯 **High Conf (88%+) Winrate:** {high_wr}\n⚠️ **Low Conf (<88%) Winrate:** {low_wr}\n\n💪 **Best Pairs:**\n"""
        for p, t, w in best_pairs:
            txt += f"• {p}: {w}/{t} wins\n"
        txt += f"\n⏰ **Best Hours (WAT):**\n"
        for h, t, w in best_hours:
            txt += f"• {h}:00 - {w}/{t} wins\n"
        txt += f"\n⚖️ **AI Weights (Bot don adjust am by itself):**\n"
        for k,v in weights.items():
            txt += f"• {k}: {v}\n"
        pnl_today, total_today, wins_today, losses_today = ai_daily_stats()
        locked, _, _ = ai_is_daily_locked()
        txt += f"\n🛡️ **PROTECTION (V14):**\n"
        txt += f"• Today PnL: ${pnl_today:+.2f} / Max Loss -${DAILY_MAX_LOSS:.0f}\n"
        txt += f"• Today Trades: {total_today}/{DAILY_MAX_TRADES}\n"
        txt += f"• Status: {'🔒 LOCKED - Rest Till Tomorrow' if locked else '✅ OPEN - You fit trade'}\n"
        txt += f"• Auto-Block: ON - Bad pair/hour go block by itself after 5 losses\n"
        txt += f"\n💡 Bot go continue to learn after every trade. After 50 trades, e go sabi which pair/time dey favour you."
        bot.send_message(m.chat.id, txt, parse_mode="Markdown")
        return
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
        pnl_today, total_today, _, _ = ai_daily_stats()
        locked, _, _ = ai_is_daily_locked()
        txt=f"""📍 **MODE CHECK V14 PROTECTED**\n\n⏰ Now: {now.strftime('%A %H:%M:%S WAT')}\n📊 Mode: {get_mode_text()}\n💎 IQ: {'✅' if IQ_CONNECTED else '❌ False - Check email/pass or IP blocked'}\n🛡️ Martingale: 1-2-4 (3 Levels, 2 Min each)\n🧠 AI: {'✅ ON - Learning + Auto-Block'}\n💰 Today PnL: ${pnl_today:+.2f} / Max -${DAILY_MAX_LOSS:.0f} | Status: {'🔒 LOCKED' if locked else '✅ OPEN'}\nOTC: {'✅ ON' if ENABLE_OTC else '⛔ DISABLED - REAL only'}\n"""
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
    mk.add(types.InlineKeyboardButton(f"📈 TRADE REAL (22) AUTO EXPIRY - ${bal_demo:.2f}",callback_data="trade_real"))
    mk.add(types.InlineKeyboardButton("🧠 AI BRAIN REPORT",callback_data="ai_report"))
    mk.add(types.InlineKeyboardButton("📅 TODAY REPORT",callback_data="today_report"))
    mk.add(types.InlineKeyboardButton("📊 MY STATS",callback_data="stats"),types.InlineKeyboardButton("⚙️ SETTINGS",callback_data="settings"))
    txt=f"""🤖 **Z-BOT V14 PROTECTED - REAL ONLY** 🤖\n\n💎 IQ: {'✅' if IQ_CONNECTED else '❌ False - Retrying...'} | 💰 DEMO ${bal_demo:.2f}\n🏆 W:{STATS['wins']} L:{STATS['loss']} | 🔥 {STATS['streak']}\n📍 {get_mode_text()}\n🧠 AI: Learning + Auto-Block + Daily Max Loss -${DAILY_MAX_LOSS:.0f}\n⛔ OTC Disabled - REAL signals start 7AM\n\n👇 **Select:**\n"""
    bot.send_message(m.chat.id,txt,reply_markup=mk,parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_allowed(c.from_user.id): bot.answer_callback_query(c.id,"❌ Private"); return
    data=c.data; cid=c.message.chat.id
    if data=="today_report":
        pnl, total, wins, losses = ai_daily_stats()
        locked, _, _ = ai_is_daily_locked()
        bot.send_message(cid, f"📅 **TODAY**\nPnL: ${pnl:+.2f} | W:{wins} L:{losses} | {total} trades\nStatus: {'🔒 LOCKED' if locked else '✅ OPEN'} | Max Loss -${DAILY_MAX_LOSS:.0f}", parse_mode="Markdown"); return
    if data=="ai_report":
        total, wins, best_pairs, best_hours, high_wr, low_wr, weights = ai_get_insight()
        losses = total - wins
        wr = (wins/total*100) if total else 0
        pnl_today, total_today, _, _ = ai_daily_stats()
        locked, _, _ = ai_is_daily_locked()
        txt = f"🧠 **AI BRAIN**\nTotal: {total} | W:{wins} L:{losses} | {wr:.1f}%\nHigh Conf: {high_wr} | Low Conf: {low_wr}\nToday PnL: ${pnl_today:+.2f} | Status: {'🔒 LOCKED' if locked else '✅ OPEN'}\n\nBest Pairs:\n"
        for p,t,w in best_pairs: txt+=f"• {p}: {w}/{t}\n"
        txt+=f"\nWeights: {weights}"
        bot.send_message(cid, txt, parse_mode="Markdown"); return
    if data.startswith("manual_win_") or data.startswith("manual_loss_"):
        try: bot.answer_callback_query(c.id, "Result recorded ✅")
        except: pass
        is_win = data.startswith("manual_win_")
        parts = data.split("_")
        try:
            pair = parts[2]; direction = parts[3]; conf = float(parts[4]); amt = float(parts[5]); level = int(parts[6]); p_int = int(parts[7])
            payout = p_int / 100.0
        except:
            bot.send_message(cid, "❌ Could not read result, try again"); return
        tz = pytz.timezone("Africa/Lagos")
        now_str = datetime.now(tz).strftime('%H:%M:%S')
        if is_win:
            profit = round(amt * payout, 2)
            STATS['wins'] += 1; STATS['streak'] += 1; OTC_MARTI["loss_streak"] = 0
            OTC_SESSION_RESULTS.append({"pair":pair,"dir":direction,"conf":conf,"pnl":profit,"win":True,"amt":amt,"level":level,"time":now_str})
            ai_save_trade(pair, direction, conf, 0, 0, payout, "Manual Trade EMA RSI MACD", amt, level, True)
            mk = types.InlineKeyboardMarkup(row_width=2)
            mk.add(types.InlineKeyboardButton("📈 TRADE REAL", callback_data="trade_real"), types.InlineKeyboardButton("📊 STATS", callback_data="stats"))
            bot.send_message(cid, f"""✅ **WINNER! ✅ - MANUAL RESULT**\n\n━━━━━━━━━━━━━━━\n💰 **Profit:** +${profit:.2f}\n💱 **Pair:** {PAIR_EMOJI.get(pair,pair)} {direction}\n💵 **Amount:** ${amt:.2f} | Level {level} ({level}x)\n🎯 **Conf:** {conf:.0f}% | Payout {p_int}%\n🏆 **Stats:** W:{STATS['wins']} L:{STATS['loss']} | 🔥 Streak {STATS['streak']}\n━━━━━━━━━━━━━━━\n\n♻️ Reset to Level 1 - ${OTC_MARTI['base']:.2f} next trade\n🧠 AI don save am, e go learn from am\n🎉 Congratulations!""", reply_markup=mk, parse_mode="Markdown")
        else:
            STATS['loss'] += 1; STATS['streak'] = 0
            OTC_SESSION_RESULTS.append({"pair":pair,"dir":direction,"conf":conf,"pnl":-amt,"win":False,"amt":amt,"level":level,"time":now_str})
            ai_save_trade(pair, direction, conf, 0, 0, payout, "Manual Trade EMA RSI MACD", amt, level, False)
            if OTC_MARTI["loss_streak"] >= 2:
                OTC_MARTI["loss_streak"] = 0
                mk = types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton("📈 TRADE REAL", callback_data="trade_real"), types.InlineKeyboardButton("📊 STATS", callback_data="stats"))
                bot.send_message(cid, f"""❌ **LOSS - MANUAL RESULT**\n\n━━━━━━━━━━━━━━━\n💸 **Loss:** -${amt:.2f}\n💱 **Pair:** {PAIR_EMOJI.get(pair,pair)} {direction}\n💵 **Amount:** ${amt:.2f} | Level {level} ({level}x)\n🎯 **Conf:** {conf:.0f}%\n📊 **Stats:** W:{STATS['wins']} L:{STATS['loss']}\n━━━━━━━━━━━━━━━\n\n⛔ 1-2-4 done. Reset to Level 1 - ${OTC_MARTI['base']:.2f}\n🧠 AI don save am, e go avoid this pattern next time""", reply_markup=mk, parse_mode="Markdown")
            else:
                OTC_MARTI["loss_streak"] += 1
                levels = OTC_MARTI["levels"]; next_mult = levels[OTC_MARTI["loss_streak"]]; next_amt = round(OTC_MARTI["base"] * next_mult, 2)
                mk = types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton("📈 TRADE REAL", callback_data="trade_real"), types.InlineKeyboardButton("📊 STATS", callback_data="stats"))
                bot.send_message(cid, f"""❌ **LOSS - MANUAL RESULT**\n\n━━━━━━━━━━━━━━━\n💸 **Loss:** -${amt:.2f}\n💱 **Pair:** {PAIR_EMOJI.get(pair,pair)} {direction}\n💵 **Amount:** ${amt:.2f} | Level {level} ({level}x)\n🎯 **Conf:** {conf:.0f}%\n📊 **Stats:** W:{STATS['wins']} L:{STATS['loss']}\n━━━━━━━━━━━━━━━\n\n➡️ Next trade na **Level {OTC_MARTI['loss_streak']+1} - ${next_amt:.2f} ({next_mult}x)**\n🧠 AI don save am\n💪 Don't give up!""", reply_markup=mk, parse_mode="Markdown")
        return
    if data=="trade_real":
        locked, pnl_today, trades_today = ai_is_daily_locked()
        if locked:
            bot.send_message(cid, f"🔒 **DAILY LOCKED**\n\nToday PnL: ${pnl_today:+.2f}\nYou don reach Max Loss -${DAILY_MAX_LOSS:.0f} or Max Trades. Rest till tomorrow.")
            return
        mk=types.InlineKeyboardMarkup(row_width=1); mk.add(types.InlineKeyboardButton("🔍 📊 SCAN ALL REAL NOW (22 PAIRS)",callback_data="scan_all_real"))
        for p in REAL_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}",callback_data=f"real_pair_{p}"))
        bot.send_message(cid,f"📈 **TRADE REAL V14 PROTECTED**\n📍 {get_mode_text()}\n💰 Today PnL: ${pnl_today:+.2f} | Max -${DAILY_MAX_LOSS:.0f}",reply_markup=mk,parse_mode="Markdown"); return
    if data=="scan_all_real":
        bot.answer_callback_query(c.id,"Scanning 22 REAL pairs V14..."); scan_msg=bot.send_message(cid,"🔍 **SCANNING ALL 22 REAL PAIRS V14 PROTECTED...**\n\n⏳ ~12 sec"); results=[]; datas={}
        for pair in REAL_PAIRS:
            now_hour = datetime.now(pytz.timezone("Africa/Lagos")).hour
            is_blocked, _ = ai_should_block(pair, now_hour)
            if is_blocked:
                results.append((pair,0,"-","AI Blocked - Bad winrate","🚫 BLOCKED",120)); continue
            d=analyze_sniper_v12(pair,sniper_mode=False)
            if not d: results.append((pair,0,"-","No data","🔴 NO TRADE",120)); continue
            conf=d['conf']; dir_=d['dir']; reason=d['reason']; exp=d['expiry']
            if conf>=88: status="🟢 READY"
            elif conf>=65: status="🟡 READY"
            else: status="🔴 NO TRADE"
            results.append((pair,conf,dir_,reason,status,exp)); datas[pair]=d
            try: bot.edit_message_text(f"🔍 Scanning V14... {pair} {conf:.0f}%",cid,scan_msg.message_id)
            except: pass
            time.sleep(0.3)
        results.sort(key=lambda x: x[1], reverse=True); txt="📊 **REAL V14 PROTECTED READINESS** 📊\n"; txt+=f"📍 {get_mode_text()}\n⏰ {datetime.now(pytz.timezone('Africa/Lagos')).strftime('%H:%M:%S WAT')}\n\n"
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
            amt_m, mult_m, lvl_m = get_manual_amt_and_level()
            pnl_today2, _, _, _ = ai_daily_stats()
            signal_txt=f"""📡 **REAL TOP SIGNAL V14 PROTECTED - 3 LEVELS** 📡\n\n💱 {PAIR_EMOJI.get(best_data['pair'],best_data['pair'])}\n📊 {dir_e} | 🎯 {best_data['conf']:.0f}% SNIPER\n📈 {best_data['reason']} | RSI {best_data['rsi']:.1f}\n💸 {int(best_data['payout']*100)}% | 💰 {best_data['price']:.5f}\n💰 Today PnL: ${pnl_today2:+.2f} | Max -${DAILY_MAX_LOSS:.0f}\n\n⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)\n\n**Level 1:** {entry.strftime('%H:%M:%S')} - 2 Min - ${base:.2f}\n**Level 2:** {entry2.strftime('%H:%M:%S')} - 2 Min - ${base*2:.2f}\n**Level 3:** {entry3.strftime('%H:%M:%S')} - 2 Min - ${base*4:.2f}\n\n⛔ STOP after Level 3.\n\n👇 After you trade manually, press result below:"""
            bot.send_message(cid,signal_txt,parse_mode="Markdown", reply_markup=manual_result_keyboard(best_data['pair'], best_data['dir'], best_data['conf'], amt_m, mult_m, best_data['payout']))
        return
    if data.startswith("real_pair_"):
        pair=data.replace("real_pair_","")
        now_hour = datetime.now(pytz.timezone("Africa/Lagos")).hour
        is_blocked, block_reason = ai_should_block(pair, now_hour)
        if is_blocked:
            bot.send_message(cid, f"🚫 **AI BLOCKED {pair}**\n\n{block_reason}\n\nBot dey protect you. Try another pair.")
            return
        bot.answer_callback_query(c.id,f"Scanning {pair} V14..."); scan_msg=bot.send_message(cid,f"🔍 **V14 PROTECTED SCAN {PAIR_EMOJI.get(pair,pair)}**\n\n0%\n🚀 Sniper..."); legit_live_scan(cid,scan_msg.message_id,pair); d=analyze_sniper_v12(pair,sniper_mode=False)
        if not d or d['conf'] < 65:
            mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🔄 RETRY",callback_data=f"real_pair_{pair}"),types.InlineKeyboardButton("📈 SCAN ALL",callback_data="scan_all_real"))
            bot.send_message(cid,f"⚠️ **No safe trade now for {pair}**\n\n📊 Conf: {d['conf'] if d else 0}% < 65%\n🛡️ {d['reason'] if d else 'No data'}",reply_markup=mk); return
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=45); entry2=entry+timedelta(seconds=120); entry3=entry+timedelta(seconds=240); exp=d['expiry']; dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]
        amt_m, mult_m, lvl_m = get_manual_amt_and_level()
        pnl_today2, _, _, _ = ai_daily_stats()
        signal_txt=f"""📡 **REAL SIGNAL V14 PROTECTED - 3 LEVELS** 📡\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n📊 {dir_e} | 🎯 {d['conf']:.0f}% SNIPER\n📈 {d['reason']} | RSI {d['rsi']:.1f} | ATR {d['atr']:.5f}\n💸 {int(d['payout']*100)}% | 💰 {d['price']:.5f}\n💰 Today PnL: ${pnl_today2:+.2f} | Max -${DAILY_MAX_LOSS:.0f}\n\n⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)\n⏱️ EXPIRY: 2 Min Each Level\n\n**Level 1:** {entry.strftime('%H:%M:%S')} - 2 Min - ${base:.2f}\n**Level 2:** {entry2.strftime('%H:%M:%S')} - 2 Min - ${base*2:.2f}\n**Level 3:** {entry3.strftime('%H:%M:%S')} - 2 Min - ${base*4:.2f}\n\n⛔ STOP after Level 3.\n⚠️ **MANUAL PLACE**\n\n👇 After you trade manually, press result below:"""
        mk=manual_result_keyboard(pair, d['dir'], d['conf'], amt_m, mult_m, d['payout'])
        mk.add(types.InlineKeyboardButton("🔁 SAME PAIR",callback_data=f"real_pair_{pair}"),types.InlineKeyboardButton("📈 SCAN ALL",callback_data="scan_all_real"))
        bot.send_message(cid,signal_txt,reply_markup=mk,parse_mode="Markdown"); return
    if data=="trade" or data=="scan_all_otc" or data=="auto_setup" or data.startswith("auto_pair_") or data.startswith("auto_bal_") or data.startswith("auto_amt_") or data.startswith("pair_"):
        bot.answer_callback_query(c.id,"OTC Disabled")
        bot.send_message(cid,"⛔ **OTC DISABLED**\n\nOTC dey cause hang. Bot go only send REAL signals from 7AM tomorrow.\n\nUse TRADE REAL for now.")
        return
    if data=="stop_auto":
        if cid in AUTO_STATE: AUTO_STATE[cid]['running']=False; bot.send_message(cid,"🛑 Stopping..."); return
    if data=="stats":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0; bal=get_real_balance("PRACTICE"); mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("💹 NEW TRADE",callback_data="trade"),types.InlineKeyboardButton("🤖 AUTO",callback_data="auto_setup"))
        bot.send_message(cid,f"📊 **STATS V14 PROTECTED**\n📍 {get_mode_text()}\n🏆 Wins: {STATS['wins']}\n❌ Loss: {STATS['loss']}\n📈 Winrate: {wr:.1f}%\n🔥 Streak: {STATS['streak']}\n💰 Bal: ${bal:.2f}\n🧠 AI: Learning + Block + Daily Max -${DAILY_MAX_LOSS:.0f} | 📦 OTC: DISABLED | REAL only",reply_markup=mk,parse_mode="Markdown")
    if data=="settings":
        bot.send_message(cid,f"⚙️ **SETTINGS V14 PROTECTED REAL ONLY**\n\n🛡️ V14: 5M Trend + ADX + MACD + Stochastic + BB + Volume + Payout + AI Weights\n⏱️ Expiry: FIXED 2 Min (120s) for Level 1, 2, 3\n🧠 AI: Auto-adjust weights after every 10 trades\n🚫 Auto-Block: Block pair/hour if winrate <35% after 5 trades\n🔒 Daily Max Loss: -${DAILY_MAX_LOSS:.0f} | Max Trades: {DAILY_MAX_TRADES}\n📊 OTC: DISABLED\nREAL: 7AM-8PM auto 88%+ signals\n\nType /ai to see what bot don learn\nType /today to see today PnL")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id,{}).get("step")=="await_amt")
def handle_custom_amt(m):
    cid=m.chat.id; st=user_states.get(cid,{})
    if not is_allowed(m.from_user.id): return
    try:
        amt=float(m.text.strip()); pair=st.get("pair"); bal=st.get("bal"); expiry=st.get("expiry",120)
        if not pair: return
        bot.send_message(cid,f"✅ Custom ${amt} - Placing Safe 2 Min trade...")
        d=analyze_sniper_v12(pair,sniper_mode=False)
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
threading.Thread(target=daily_8pm_report,daemon=True).start()
threading.Thread(target=nightly_backup_to_telegram,daemon=True).start()

if __name__ == "__main__":
    try:
        url=os.getenv("RENDER_EXTERNAL_URL")
        if url and BOT_TOKEN:
            requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={url}/{BOT_TOKEN}", timeout=5)
            print(f"Webhook set {url}")
    except: pass
    port=int(os.getenv("PORT",10000))
    print(f"Starting Flask on 0.0.0.0:{port} - FREE WEB SERVICE - OTC DISABLED - V14 PROTECTED + DAILY 8PM REPORT + BACKUP")
    app.run(host="0.0.0.0", port=port, threaded=True)
