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
# ===== V18 SAFE SETTINGS =====
DAILY_MAX_LOSS = 20.0
DAILY_MAX_TRADES = 6
SIGNAL_COOLDOWN = 600
LAST_SIGNAL_TIME = 0

SAFE_PAIRS = ["EURUSD","GBPUSD","USDJPY","EURGBP","AUDUSD","USDCAD","EURJPY","GBPJPY","USDCHF","AUDJPY","EURAUD","GBPCHF","EURCHF","NZDUSD","GBPAUD","EURCAD","AUDCAD","GBPCAD","NZDJPY","AUDNZD","CHFJPY","CADJPY"]
# V18: ALL 22 pairs back - Safe strategy go filter them, no need cut pairs
SAFE_MIN_CONF = 92
SAFE_MIN_PAYOUT = 0.80
SAFE_MIN_ADX = 25

# ===== V18 AUTO EXPIRY BY CONFIDENCE =====
def get_expiry_by_conf(conf):
    if conf >= 94:
        return 120
    elif conf >= 92:
        return 180
    elif conf >= 88:
        return 180
    else:
        return 180

REAL_PAIRS = ["EURUSD","GBPUSD","USDJPY","EURGBP","AUDUSD","USDCAD","EURJPY","GBPJPY","USDCHF","AUDJPY","EURAUD","GBPCHF","EURCHF","NZDUSD","GBPAUD","EURCAD","AUDCAD","GBPCAD","NZDJPY","AUDNZD","CHFJPY","CADJPY"]
# V18: ALL 22 pairs back - Safe strategy go filter them, no need cut pairs
OTC_PAIRS = ["EURUSD-OTC","GBPUSD-OTC","USDJPY-OTC","AUDUSD-OTC","USDCAD-OTC","EURGBP-OTC","EURJPY-OTC","GBPJPY-OTC","AUDJPY-OTC","EURAUD-OTC","GBPAUD-OTC","NZDUSD-OTC","GBPCHF-OTC","EURCHF-OTC","USDCHF-OTC","AUDCAD-OTC","EURCAD-OTC","CADJPY-OTC","NZDJPY-OTC"]
PAIR_EMOJI = {"EURUSD":"🇪🇺 EUR/USD REAL","GBPUSD":"🇬🇧 GBP/USD REAL","USDJPY":"🇺🇸 USD/JPY REAL","EURGBP":"🇪🇺 EUR/GBP REAL","AUDUSD":"🇦🇺 AUD/USD REAL","USDCAD":"🇺🇸 USD/CAD REAL","EURJPY":"🇪🇺 EUR/JPY REAL","GBPJPY":"🇬🇧 GBP/JPY REAL","USDCHF":"🇺🇸 USD/CHF REAL","AUDJPY":"🇦🇺 AUD/JPY REAL","EURAUD":"🇪🇺 EUR/AUD REAL","GBPCHF":"🇬🇧 GBP/CHF REAL","EURCHF":"🇪🇺 EUR/CHF REAL","NZDUSD":"🇳🇿 NZD/USD REAL","GBPAUD":"🇬🇧 GBP/AUD REAL","EURCAD":"🇪🇺 EUR/CAD REAL","AUDCAD":"🇦🇺 AUD/CAD REAL","GBPCAD":"🇬🇧 GBP/CAD REAL","NZDJPY":"🇳🇿 NZD/JPY REAL","AUDNZD":"🇦🇺 AUD/NZD REAL","CHFJPY":"🇨🇭 CHF/JPY REAL","CADJPY":"🇨🇦 CAD/JPY REAL","EURUSD-OTC":"🇪🇺 EUR/USD OTC","GBPUSD-OTC":"🇬🇧 GBP/USD OTC","EURGBP-OTC":"🇪🇺 EUR/GBP OTC","USDJPY-OTC":"🇺🇸 USD/JPY OTC","GBPJPY-OTC":"🇬🇧 GBP/JPY OTC","AUDUSD-OTC":"🇦🇺 AUD/USD OTC","USDCHF-OTC":"🇺🇸 USD/CHF OTC","EURJPY-OTC":"🇪🇺 EUR/JPY OTC","AUDJPY-OTC":"🇦🇺 AUD/JPY OTC","EURAUD-OTC":"🇪🇺 EUR/AUD OTC","GBPAUD-OTC":"🇬🇧 GBP/AUD OTC","NZDUSD-OTC":"🇳🇿 NZD/USD OTC","GBPCHF-OTC":"🇬🇧 GBP/CHF OTC","EURCHF-OTC":"🇪🇺 EUR/CHF OTC","USDCAD-OTC":"🇺🇸 USD/CAD OTC","AUDCAD-OTC":"🇦🇺 AUD/CAD OTC","EURCAD-OTC":"🇪🇺 EUR/CAD OTC","CADJPY-OTC":"🇨🇦 CAD/JPY OTC","NZDJPY-OTC":"🇳🇿 NZD/JPY OTC"}

# ===== AI MEMORY LAYER - V18 =====
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
        if len(rows) < 5:
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
            if total >= 3:
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
def ai_should_block(pair, hour):
    try:
        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()
        cur.execute("SELECT COUNT(*), SUM(win) FROM trades WHERE pair=? AND hour=?", (pair, hour))
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
        cur.execute("SELECT COUNT(*), SUM(win) FROM trades WHERE pair=?", (pair,))
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

STATS = {"balance":0.0,"real_balance":0.0,"wins":0,"loss":0,"streak":0}
try:
    _t, _w, _, _, _, _, _ = ai_get_insight()
    STATS["wins"] = _w
    STATS["loss"] = _t - _w
    _con = sqlite3.connect(DB_FILE)
    _cur = _con.cursor()
    _cur.execute("SELECT win FROM trades ORDER BY id DESC LIMIT 20")
    _streak = 0
    for (_win,) in _cur.fetchall():
        if _win == 1: _streak += 1
        else: break
    _con.close()
    STATS["streak"] = _streak
    print(f"[V18] Loaded STATS from DB: W:{STATS['wins']} L:{STATS['loss']} Streak:{_streak}")
except Exception as e:
    print(f"[V18] Load STATS err {e}")

user_states = {}; AUTO_STATE = {}; IQ_LOCK = threading.Lock()
IQ_CONNECTED=False; iq=None; PAYOUT_CACHE={}; PAYOUT_TIME=0
OTC_SESSION_RESULTS = []
OTC_MARTI = {"loss_streak":0, "base":1.0, "bal":"PRACTICE", "levels":[1,2,4]}
PENDING_MANUAL = {}
PENDING_MARTI = {}

# ===== V18: NEWS FILTER + BACKTEST =====
NEWS_CACHE = {"time": 0, "events": []}
def fetch_news_events():
    global NEWS_CACHE
    if time.time() - NEWS_CACHE["time"] < 3600 and NEWS_CACHE["events"]:
        return NEWS_CACHE["events"]
    try:
        r = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json", timeout=10)
        events = r.json()
        NEWS_CACHE = {"time": time.time(), "events": events}
        print(f"[NEWS] Fetched {len(events)} events")
        return events
    except Exception as e:
        print(f"[NEWS] Fetch err {e} - using empty, trading allowed")
        return []
def is_news_time(pair="EURUSD", minutes_before=30, minutes_after=30):
    try:
        tz = pytz.timezone("Africa/Lagos")
        now = datetime.now(tz)
        base = pair[:3]
        quote = pair[3:6] if len(pair) >= 6 else "USD"
        pair_currencies = set([base, quote])
        events = fetch_news_events()
        for ev in events:
            try:
                impact = ev.get("impact", "")
                currency = ev.get("currency", "")
                title = ev.get("title", "")
                date_str = ev.get("date", "")
                if impact != "High":
                    continue
                if currency not in pair_currencies:
                    continue
                ev_time = datetime.fromisoformat(date_str.replace("Z","+00:00"))
                ev_time_lagos = ev_time.astimezone(tz)
                diff_min = (ev_time_lagos - now).total_seconds() / 60
                if -minutes_after <= diff_min <= minutes_before:
                    return True, f"📰 NEWS BLOCK: {currency} {title} for {ev_time_lagos.strftime('%H:%M')} - {int(diff_min)} min away. No trade."
            except:
                continue
        return False, ""
    except Exception as e:
        print(f"[NEWS check err] {e}")
        return False, ""
def run_backtest(pair="EURUSD", candles_to_test=100):
    try:
        df = get_candles(pair)
        if df is None or len(df) < 50:
            return None
        wins = 0; losses = 0
        for i in range(max(30, len(df)-candles_to_test), len(df)-2):
            row = df.iloc[i]
            closes = df['close'].iloc[:i+1]
            ema9 = closes.ewm(9).mean().iloc[-1]
            ema21 = closes.ewm(21).mean().iloc[-1]
            rsi_vals = calc_rsi(closes, 7)
            r7 = float(rsi_vals.iloc[-1]) if len(rsi_vals) > 0 else 50
            is_green = float(row['close']) > float(row['open'])
            if is_green and ema9 > ema21 and 45 <= r7 <= 70:
                pred = "CALL"
            elif not is_green and ema9 < ema21 and 30 <= r7 <= 55:
                pred = "PUT"
            else:
                continue
            next_candle = df.iloc[i+1]
            actual = "CALL" if float(next_candle['close']) > float(next_candle['open']) else "PUT"
            if pred == actual:
                wins += 1
            else:
                losses += 1
        total = wins + losses
        wr = (wins/total*100) if total else 0
        return {"pair": pair, "total": total, "wins": wins, "losses": losses, "winrate": wr}
    except Exception as e:
        print(f"[BACKTEST err] {e}")
        return None

def get_support_resistance(df):
    try:
        last = df.tail(50)
        highs = last['max'].tolist()
        lows = last['min'].tolist()
        resistances = []
        supports = []
        for i in range(2, len(last)-2):
            h = float(last['max'].iloc[i])
            l = float(last['min'].iloc[i])
            if h > float(last['max'].iloc[i-1]) and h > float(last['max'].iloc[i-2]) and h > float(last['max'].iloc[i+1]) and h > float(last['max'].iloc[i+2]):
                resistances.append(h)
            if l < float(last['min'].iloc[i-1]) and l < float(last['min'].iloc[i-2]) and l < float(last['min'].iloc[i+1]) and l < float(last['min'].iloc[i+2]):
                supports.append(l)
        c_now = float(df['close'].iloc[-1])
        res_above = [r for r in resistances if r > c_now]
        sup_below = [s for s in supports if s < c_now]
        nearest_res = min(res_above, key=lambda x: abs(x - c_now)) if res_above else float(max(highs))
        nearest_sup = max(sup_below, key=lambda x: abs(x - c_now)) if sup_below else float(min(lows))
        return nearest_sup, nearest_res
    except:
        return None, None

def get_session_info():
    try:
        tz = pytz.timezone("Africa/Lagos")
        now = datetime.now(tz)
        hour = now.hour
        minute = now.minute
        time_float = hour + minute/60
        if 9 <= time_float < 11:
            return "LONDON", True, "London Open - Big Money"
        elif 14.5 <= time_float < 16.5:
            return "NEWYORK", True, "New York Open - Big Money"
        elif 7 <= time_float < 9:
            return "EARLY", False, "Early - Market Slow"
        elif 11 <= time_float < 14.5:
            return "LUNCH", False, "Lunch - Market Dead"
        elif 16.5 <= time_float < 20:
            return "LATE", False, "Late - Market Tired"
        else:
            return "OFF", False, "Off Hours"
    except:
        return "UNKNOWN", False, ""

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
    return f"V18 SAFE RUNNING IQ:{IQ_CONNECTED} OTC:{ENABLE_OTC} {datetime.now(pytz.timezone('Africa/Lagos')).strftime('%H:%M:%S')}"
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
    steps = [(0,"🚀 V18 Safe Sniper Init...",0.15),(20,f"🔌 Checking {pair}...",0.2),(40,"📊 ADX + ATR + Volume...",0.25),(60,"📈 EMA + MACD + 5M Trend...",0.2),(80,"💹 RSI + S/R + Session + Pullback...",0.2),(100,"🔒 SNIPER LOCKED!",0.3)]
    last_pct=-1
    for pct, text, delay in steps:
        if pct==last_pct: time.sleep(delay); continue
        last_pct=pct; filled=int(pct//5); bar="█"*filled+"░"*(20-filled); color="🟥" if pct<40 else "🟨" if pct<80 else "🟩" if pct<100 else "💎"
        txt=f"""{color} **Z-BOT V18 SAFE** {color}\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n💎 IQ: {'✅' if IQ_CONNECTED else '❌'}\n\n{bar} {pct}%\n\n🔍 {text}\n⏳ V18 Safe"""
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

# ===== V18 SAFE STRATEGY: Trend + Pullback + Bounce - NO CHASE =====
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
        c_now=float(close.iloc[-1]); o_now=float(open_.iloc[-1]); c_prev=float(close.iloc[-2]); o_prev=float(open_.iloc[-2])
        h_now=float(high.iloc[-1]); l_now=float(low.iloc[-1]); e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1]); e50=float(ema50.iloc[-1])
        r7=float(rsi7.iloc[-1]); r14=float(rsi14.iloc[-1])
        body=abs(c_now-o_now); upper_wick=h_now-max(c_now,o_now); lower_wick=min(c_now,o_now)-l_now; is_green=c_now>o_now; payout=get_payout(pair)
        if adx < SAFE_MIN_ADX:
            return {"pair":pair,"dir":"CALL" if is_green else "PUT","conf":42,"price":c_now,"rsi":r7,"adx":adx,"reason":"V18: No trend - ADX low","payout":payout,"expiry":180,"atr":atr,"rejected":False}
        if payout < SAFE_MIN_PAYOUT:
            return {"pair":pair,"dir":"CALL" if is_green else "PUT","conf":52,"price":c_now,"rsi":r7,"adx":adx,"reason":f"V18: Payout low {int(payout*100)}%","payout":payout,"expiry":180,"atr":atr,"rejected":False}
        if body < atr*0.30:
            return {"pair":pair,"dir":"CALL" if is_green else "PUT","conf":48,"price":c_now,"rsi":r7,"adx":adx,"reason":"V18: Doji - No body","payout":payout,"expiry":180,"atr":atr,"rejected":False}
        # STEP 1: TREND
        trend_1m = 1 if e9 > e21 > e50 else -1 if e9 < e21 < e50 else 0
        if trend_1m == 0:
            return {"pair":pair,"dir":"CALL" if is_green else "PUT","conf":45,"price":c_now,"rsi":r7,"adx":adx,"reason":"V18: EMA messy - No clear trend","payout":payout,"expiry":180,"atr":atr,"rejected":True}
        trend_5m = 0
        if df5 is not None:
            c5=df5['close']; e9_5=c5.ewm(9).mean(); e21_5=c5.ewm(21).mean()
            trend_5m = 1 if float(e9_5.iloc[-1]) > float(e21_5.iloc[-1]) else -1
            if trend_5m != trend_1m:
                return {"pair":pair,"dir":"CALL" if is_green else "PUT","conf":45,"price":c_now,"rsi":r7,"adx":adx,"reason":"V18: 1M vs 5M trend disagree","payout":payout,"expiry":180,"atr":atr,"rejected":True}
        sig = "CALL" if trend_1m == 1 else "PUT"
        # STEP 2: PULLBACK - Must be near EMA
        dist_ema21 = abs(c_now - e21) / c_now * 100
        dist_ema9 = abs(c_now - e9) / c_now * 100
        if dist_ema21 > 0.06 and dist_ema9 > 0.06:
            return {"pair":pair,"dir":sig,"conf":50,"price":c_now,"rsi":r7,"adx":adx,"reason":f"V18: Too far from EMA - Chasing {dist_ema21:.3f}%","payout":payout,"expiry":180,"atr":atr,"rejected":True}
        # STEP 3: BOUNCE + RSI
        score = 50
        reasons = [f"V18 Trend {sig} + Pullback {dist_ema21:.3f}%"]
        if sig == "CALL":
            if 45 <= r7 <= 60 and 45 <= r14 <= 60:
                score += 18; reasons.append(f"RSI Safe {r7:.0f}")
            else:
                return {"pair":pair,"dir":sig,"conf":55,"price":c_now,"rsi":r7,"adx":adx,"reason":f"V18: RSI {r7:.0f} not safe for CALL","payout":payout,"expiry":180,"atr":atr,"rejected":True}
        else:
            if 40 <= r7 <= 55 and 40 <= r14 <= 55:
                score += 18; reasons.append(f"RSI Safe {r7:.0f}")
            else:
                return {"pair":pair,"dir":sig,"conf":55,"price":c_now,"rsi":r7,"adx":adx,"reason":f"V18: RSI {r7:.0f} not safe for PUT","payout":payout,"expiry":180,"atr":atr,"rejected":True}
        if sig == "CALL" and not is_green:
            return {"pair":pair,"dir":sig,"conf":58,"price":c_now,"rsi":r7,"adx":adx,"reason":"V18: No bounce yet - Still pulling back","payout":payout,"expiry":180,"atr":atr,"rejected":True}
        if sig == "PUT" and is_green:
            return {"pair":pair,"dir":sig,"conf":58,"price":c_now,"rsi":r7,"adx":adx,"reason":"V18: No bounce yet - Still pulling back","payout":payout,"expiry":180,"atr":atr,"rejected":True}
        score += 10; reasons.append("Bounce Candle")
        if sig == "CALL" and macd_val > sig_val:
            score += 8; reasons.append("MACD Bull")
        elif sig == "PUT" and macd_val < sig_val:
            score += 8; reasons.append("MACD Bear")
        else:
            return {"pair":pair,"dir":sig,"conf":60,"price":c_now,"rsi":r7,"adx":adx,"reason":"V18: MACD disagree","payout":payout,"expiry":180,"atr":atr,"rejected":True}
        if adx >= 28: score += 8; reasons.append(f"ADX {adx:.0f} Strong")
        elif adx >= 25: score += 5
        if sig == "CALL" and pdi > mdi: score += 5
        elif sig == "PUT" and mdi > pdi: score += 5
        else: score -= 5
        bull_eng = c_now > o_prev and o_now < c_prev and is_green and c_prev < o_prev
        bear_eng = c_now < o_prev and o_now > c_prev and not is_green and c_prev > o_prev
        pin_bull = lower_wick > body*1.8 and is_green
        pin_bear = upper_wick > body*1.8 and not is_green
        if sig == "CALL" and (bull_eng or pin_bull): score += 8; reasons.append("Pin/Engulf Bull")
        if sig == "PUT" and (bear_eng or pin_bear): score += 8; reasons.append("Pin/Engulf Bear")
        avg_vol=float(vol.rolling(20).mean().iloc[-1]) if len(vol)>20 else 1; curr_vol=float(vol.iloc[-1]) if len(vol)>0 else 1
        if curr_vol > avg_vol*1.2: score += 5; reasons.append("Vol Spike")
        sup, res = get_support_resistance(df)
        sr_info = ""
        if sup is not None and res is not None:
            dist_res = abs(c_now - res) / atr if atr>0 else 999
            dist_sup = abs(c_now - sup) / atr if atr>0 else 999
            if sig == "CALL":
                if dist_res < 0.8:
                    return {"pair":pair,"dir":sig,"conf":60,"price":c_now,"rsi":r7,"adx":adx,"reason":f"V18: Near Resistance {res:.5f}","payout":payout,"expiry":180,"atr":atr,"rejected":True}
                if dist_sup < 1.2: score += 8; reasons.append(f"Bounce Support {sup:.5f}"); sr_info = f"Sup Bounce {sup:.5f}"
                else: sr_info = "S/R Clear"
            else:
                if dist_sup < 0.8:
                    return {"pair":pair,"dir":sig,"conf":60,"price":c_now,"rsi":r7,"adx":adx,"reason":f"V18: Near Support {sup:.5f}","payout":payout,"expiry":180,"atr":atr,"rejected":True}
                if dist_res < 1.2: score += 8; reasons.append(f"Reject Resistance {res:.5f}"); sr_info = f"Res Reject {res:.5f}"
                else: sr_info = "S/R Clear"
        sess_name, is_golden, sess_reason = get_session_info()
        if not is_golden:
            if sess_name in ["LUNCH", "LATE", "OFF"]:
                return {"pair":pair,"dir":sig,"conf":60,"price":c_now,"rsi":r7,"adx":adx,"reason":f"V18: {sess_name} - No trade outside golden","payout":payout,"expiry":180,"atr":atr,"rejected":True}
            score += 3
        else:
            score += 5; reasons.append(f"{sess_name} Golden")
        score = max(40, min(96, score)); reason = " + ".join(reasons)
        expiry_auto = get_expiry_by_conf(score)
        threshold = SAFE_MIN_CONF
        if sniper_mode and score < threshold:
            return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"adx":adx,"reason":reason,"payout":payout,"expiry":expiry_auto,"atr":atr,"rejected":True, "session":sess_name, "sr":sr_info}
        return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"adx":adx,"reason":reason,"payout":payout,"expiry":expiry_auto,"atr":atr,"rejected":False, "session":sess_name, "sr":sr_info}
    except Exception as e:
        print(f"V18 err {pair} {e}"); return None

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

# ===== V18 PULLBACK MARTINGALE =====
def wait_for_pullback_level(pair, orig_dir, level, amt):
    print(f"[V18 MARTI] Waiting for pullback Level {level} {pair} {orig_dir} - Max 15 min")
    tz = pytz.timezone("Africa/Lagos")
    start = time.time()
    while time.time() - start < 900:
        try:
            locked, _, _ = ai_is_daily_locked()
            if locked:
                bot.send_message(OWNER_ID, f"🔒 Daily locked, no Level {level} for {pair}")
                return
            d = analyze_sniper_v12(pair, sniper_mode=True)
            if d and not d.get('rejected') and d['conf'] >= SAFE_MIN_CONF and d['dir'] == orig_dir:
                exp = d['expiry']; exp_min = int(exp/60)
                now = datetime.now(tz); entry = now + timedelta(seconds=45)
                msg = f"""🔁 **LEVEL {level} - NEXT PULLBACK FOUND** 🔁\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n📊 {'🟢 CALL ⬆️' if d['dir']=='CALL' else '🔴 PUT ⬇️'} | 🎯 {d['conf']:.0f}% - New Pullback Bounce\n📈 {d['reason']} | RSI {d['rsi']:.1f}\n💸 {int(d['payout']*100)}% | ⏱️ {exp_min} Min | 🤖 Bot choose {exp_min} Min - Conf {d['conf']:.0f}%\n\n⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)\n💰 **Level {level}: {entry.strftime('%H:%M:%S')} - {exp_min} Min - ${amt:.2f}**\n\n✅ This na fresh pullback, no be same bad move. Enter now.\n\n👇 After you trade, press result:"""
                bot.send_message(OWNER_ID, msg, parse_mode="Markdown", reply_markup=manual_result_keyboard(pair, d['dir'], d['conf'], amt, level, d['payout']))
                print(f"[V18 MARTI] Level {level} sent {pair} {d['conf']:.0f}%")
                return
            else:
                print(f"[V18 MARTI] Level {level} {pair} waiting... {d['conf'] if d else 0:.0f}%")
        except Exception as e:
            print(f"[V18 MARTI err] {e}")
        time.sleep(20)
    try:
        bot.send_message(OWNER_ID, f"""⏰ **LEVEL {level} CANCELLED - {pair}**\n\nNo good pullback come in 15 min.\n\n✅ Good news - Bot no force you enter bad trade. We save ${amt:.2f}.\nWait for next fresh signal. Reset to Level 1.""")
    except: pass
    OTC_MARTI["loss_streak"] = 0
    print(f"[V18 MARTI] Level {level} {pair} timeout - cancelled, reset")

def real_signal_scanner():
    global LAST_SIGNAL_TIME
    last_signal={}; tz=pytz.timezone("Africa/Lagos")
    last_lock_msg = 0
    while True:
        try:
            if is_real_hours() and IQ_CONNECTED:
                if time.time() - LAST_SIGNAL_TIME < SIGNAL_COOLDOWN:
                    remaining = int(SIGNAL_COOLDOWN - (time.time() - LAST_SIGNAL_TIME))
                    print(f"[COOLDOWN] Paused - {remaining}s left before next scan")
                    time.sleep(20)
                    continue
                signal_sent_this_round = False
                for pair in SAFE_PAIRS:
                    if signal_sent_this_round: break
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
                    news_blocked, news_reason = is_news_time(pair, 30, 30)
                    if news_blocked:
                        print(f"[NEWS BLOCK] {news_reason}")
                        last_signal[pair] = time.time()
                        continue
                    d=analyze_sniper_v12(pair,sniper_mode=True)
                    if d and not d.get('rejected') and d['conf']>=SAFE_MIN_CONF:
                        print(f"[V18 SAFE] First pass {pair} {d['conf']:.0f}% - Waiting 30s to confirm...")
                        time.sleep(30)
                        d2 = analyze_sniper_v12(pair, sniper_mode=True)
                        if not d2 or d2.get('rejected') or d2['conf'] < SAFE_MIN_CONF:
                            print(f"[V18 SAFE] {pair} FAILED 2nd confirm - SKIP, na fake")
                            last_signal[pair] = time.time()
                            continue
                        if d2['dir'] != d['dir']:
                            print(f"[V18 SAFE] {pair} direction flip - SKIP, market confused")
                            continue
                        d = d2
                        print(f"[V18 SAFE] CONFIRMED {pair} {d['conf']:.0f}% x2 - SENDING")
                        now=datetime.now(tz); entry=now+timedelta(seconds=45); exp=d['expiry']; exp_min=int(exp/60); dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]
                        amt_m, mult_m, lvl_m = get_manual_amt_and_level()
                        pnl_today2, _, _, _ = ai_daily_stats()
                        PENDING_MANUAL[pair] = {"rsi": d.get('rsi',0), "adx": d.get('adx',0), "reason": d.get('reason',''), "conf": d.get('conf',0)}
                        sess_txt = d.get('session','')
                        sr_txt = d.get('sr','')
                        msg=f"""📡 **REAL SIGNAL V18 SAFE - AUTO EXPIRY {exp_min} MIN** 📡\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n📊 {dir_e} | 🎯 {d['conf']:.0f}% SNIPER\n📈 {d['reason']} | RSI {d['rsi']:.1f} | ATR {d['atr']:.5f}\n💸 {int(d['payout']*100)}% | ⏱️ {exp_min} Min Each Level | 🤖 Bot choose {exp_min} Min because Conf {d['conf']:.0f}%\n🧠 AI: {pair} NOT blocked - Winrate good\n📍 Session: {sess_txt} | S/R: {sr_txt}\n💰 Today PnL: ${pnl_today2:+.2f} | Max Loss: -${DAILY_MAX_LOSS:.0f}\n\n⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)\n📅 {now.strftime('%A %d %b %H:%M WAT')}\n\n**Level 1:** {entry.strftime('%H:%M:%S')} - {exp_min} Min - ${base:.2f} - ENTER NOW\n**Level 2:** ⏳ WAIT - Bot go send when next pullback come - ${base*2:.2f}\n**Level 3:** ⏳ WAIT - Bot go send when next pullback come - ${base*4:.2f}\n\n⚠️ DO NOT enter Level 2/3 by time. Wait for my next message.\n⛔ STOP after Level 3. No Level 4.\n⚠️ MANUAL - Follow levels only\n\n👇 After you trade manually, press result below:"""
                        try:
                            bot.send_message(OWNER_ID,msg,parse_mode="Markdown", reply_markup=manual_result_keyboard(pair, d['dir'], d['conf'], amt_m, mult_m, d['payout']))
                            last_signal[pair]=time.time()
                            LAST_SIGNAL_TIME = time.time()
                            signal_sent_this_round = True
                            print(f"[V18] Signal sent {pair} - cooldown 10 min - Session {sess_txt} SR {sr_txt}")
                        except: pass
                        break
                    time.sleep(3)
            time.sleep(25)
        except: time.sleep(30)

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
                    msg = f"""🌙 **DAILY REPORT - {now.strftime('%A %d %b')} - 8PM** 🌙\n\n━━━━━━━━━━━━━━━\n💰 **TODAY RESULT**\n💵 PnL Today: ${pnl:+.2f}\n🏆 W:{wins} L:{losses} | Total: {total} trades\n📈 Winrate Today: {wr_today:.0f}%\n🛡️ Status: {'🔒 LOCKED - You hit max loss' if locked else '✅ OPEN'}\n━━━━━━━━━━━━━━━\n\n🧠 **WETIN BOT LEARN TODAY**\n⭐ Best Pair: {best_pair_txt}\n⏰ Best Hour: {best_hour_txt}\n🎯 High Conf (92%+) Winrate (All Time): {high_wr}\n\n⚠️ **TOMORROW ADVICE**\n{avoid_txt}\n💡 Focus on your best pair tomorrow morning, no chase loss.\n\n🛡️ **PROTECTION**\nMax Loss: -${DAILY_MAX_LOSS:.0f} | Tomorrow bot go reset to $0.00 PnL, lock go open again 7AM.\n\n😴 Bot don sleep. See you tomorrow 7AM!\nRest well, no trade for night. OTC na trap.\n"""
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

def nightly_backup_to_telegram():
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

@bot.message_handler(content_types=['document'])
def handle_restore(m):
    if not is_allowed(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Private"); return
    try:
        if not m.document.file_name.endswith('.db'):
            bot.send_message(m.chat.id, "❌ Send only .db file - na zbot_memory.db I need"); return
        bot.send_message(m.chat.id, "📥 Restoring your AI memory... wait 5 sec")
        file_info = bot.get_file(m.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        with open("zbot_memory_restore.db", "wb") as f:
            f.write(downloaded)
        con = sqlite3.connect("zbot_memory_restore.db")
        cur = con.cursor()
        cur.execute("SELECT COUNT(*), SUM(win) FROM trades")
        total, wins = cur.fetchone()
        con.close()
        total = total or 0; wins = wins or 0
        import shutil
        shutil.copyfile("zbot_memory_restore.db", DB_FILE)
        STATS["wins"] = wins
        STATS["loss"] = total - wins
        try: os.remove("zbot_memory_restore.db")
        except: pass
        bot.send_message(m.chat.id, f"✅ **RESTORED!**\n\n📊 Total: {total} trades\n🏆 W:{wins} L:{total-wins}\n🧠 AI memory don come back. No start from zero.\n\nSend /ai to confirm.", parse_mode="Markdown")
        print(f"[RESTORE] Restored {total} trades W:{wins}")
    except Exception as e:
        print(f"[RESTORE err] {e}")
        bot.send_message(m.chat.id, f"❌ Restore fail: {e}\nSend the correct zbot_memory.db file from Saved Messages")

@bot.message_handler(commands=['start','stop','mode','balance','results','ai','today','backtest'])
def start(m):
    if not is_allowed(m.from_user.id): bot.send_message(m.chat.id,"❌ Private"); return
    if m.text.startswith('/backtest'):
        parts = m.text.split()
        pair_to_test = parts[1].upper() if len(parts) > 1 else "EURUSD"
        if pair_to_test not in REAL_PAIRS:
            pair_to_test = "EURUSD"
        bot.send_message(m.chat.id, f"🔙 **BACKTESTING {pair_to_test}...**\n\n⏳ Testing last 100 candles, no real money. Wait 10 sec...")
        res = run_backtest(pair_to_test, 100)
        if not res or res['total'] == 0:
            bot.send_message(m.chat.id, "❌ No enough data for backtest, try again when IQ connected")
            return
        verdict = "✅ GOOD - You fit trade am" if res['winrate'] >= 60 else "⚠️ WEAK - No trade am today, e dey lose" if res['winrate'] < 50 else "🟡 AVERAGE - Trade with care, $1 only"
        bot.send_message(m.chat.id, f"""🔙 **BACKTEST RESULT - {res['pair']}**\n\n📊 Tested: {res['total']} signals (last 100 candles)\n🏆 W:{res['wins']} L:{res['losses']}\n📈 True Winrate: {res['winrate']:.1f}%\n\n{verdict}\n\n💡 If winrate <55%, that pair no good today. Try another pair with /backtest GBPUSD or /backtest USDCHF\n""", parse_mode="Markdown")
        return
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
        txt = f"""🧠 **Z-BOT AI BRAIN REPORT**\n\n📊 Total Learned: {total} trades\n🏆 W:{wins} L:{losses} | Winrate: {wr:.1f}%\n\n🎯 **High Conf (92%+) Winrate:** {high_wr}\n⚠️ **Low Conf (<92%) Winrate:** {low_wr}\n\n💪 **Best Pairs:**\n"""
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
        txt += f"\n🛡️ **PROTECTION (V18):**\n"
        txt += f"• Today PnL: ${pnl_today:+.2f} / Max Loss -${DAILY_MAX_LOSS:.0f}\n"
        txt += f"• Today Trades: {total_today}/{DAILY_MAX_TRADES}\n"
        txt += f"• Status: {'🔒 LOCKED - Rest Till Tomorrow' if locked else '✅ OPEN - You fit trade'}\n"
        txt += f"• Auto-Block: ON - Bad pair/hour go block by itself after 5 losses\n"
        txt += f"• Signal Cooldown: 10 min - 1 signal at a time\n"
        txt += f"• News Filter: ON - Block 30 min before/after High news\n"
        txt += f"• Strategy: Trend + Pullback + Bounce | Auto Expiry 2/3 Min | Pullback Martingale\n"
        txt += f"\n💡 Bot go continue to learn after every trade. After 50 trades, e go sabi which pair/time dey favour you."
        bot.send_message(m.chat.id, txt, parse_mode="Markdown")
        return
    if m.text.startswith('/stop'):
        if m.chat.id in AUTO_STATE: AUTO_STATE[m.chat.id]['running']=False; bot.send_message(m.chat.id,"🛑 Stopping...")
        else: bot.send_message(m.chat.id,"Auto not running"); return
    if m.text.startswith('/results'):
        if not OTC_SESSION_RESULTS: bot.send_message(m.chat.id,"📭 No OTC 85% auto trades yet this session"); return
        wins=sum(1 for x in OTC_SESSION_RESULTS if x['win']); losses=len(OTC_SESSION_RESULTS)-wins; pnl_total=sum(x['pnl'] for x in OTC_SESSION_RESULTS); levels = OTC_MARTI["levels"]; idx = OTC_MARTI["loss_streak"] % len(levels)
        txt=f"📊 **OTC 85% AUTO MARTINGALE RESULTS (1-2-4)**\n\nTotal: {len(OTC_SESSION_RESULTS)} | W:{wins} L:{losses} | PnL: ${pnl_total:.2f}\nCurrent Level: {idx+1} ({levels[idx]}x) | Base: ${OTC_MARTI['base']} | Pullback Martingale\n\n"
        for r in OTC_SESSION_RESULTS[-25:]: txt+=f"{'✅' if r['win'] else '❌'} {r['time']} {r['pair']} {r['dir']} ${r['amt']} L{r['level']} {r['conf']}% {r['pnl']:+.2f}\n"
        bot.send_message(m.chat.id,txt,parse_mode="Markdown"); return
    if m.text.startswith('/mode'):
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz)
        pnl_today, total_today, _, _ = ai_daily_stats()
        locked, _, _ = ai_is_daily_locked()
        sess_name, is_golden, sess_reason = get_session_info()
        txt=f"""📍 **MODE CHECK V18 SAFE**\n\n⏰ Now: {now.strftime('%A %H:%M:%S WAT')}\n📊 Mode: {get_mode_text()}\n📍 Session: {sess_name} - {sess_reason} | {'🟢 GOLDEN - Need 92%' if is_golden else '🟡 WEAK - No trade'}\n💎 IQ: {'✅' if IQ_CONNECTED else '❌ False - Check email/pass or IP blocked'}\n🛡️ Martingale: 1-2-4 (Pullback, No fixed time)\n🧠 AI: {'✅ ON - Learning + Auto-Block'}\n📰 News Filter: ✅ ON\n💰 Today PnL: ${pnl_today:+.2f} / Max -${DAILY_MAX_LOSS:.0f} | Status: {'🔒 LOCKED' if locked else '✅ OPEN'}\n⏳ Cooldown: 10 min between signals\nOTC: {'✅ ON' if ENABLE_OTC else '⛔ DISABLED - REAL only'}\n"""
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
    mk.add(types.InlineKeyboardButton(f"📈 TRADE SAFE (6) - ${bal_demo:.2f}",callback_data="trade_real"))
    mk.add(types.InlineKeyboardButton("🧠 AI BRAIN REPORT",callback_data="ai_report"))
    mk.add(types.InlineKeyboardButton("📅 TODAY REPORT",callback_data="today_report"))
    mk.add(types.InlineKeyboardButton("📊 MY STATS",callback_data="stats"),types.InlineKeyboardButton("⚙️ SETTINGS",callback_data="settings"))
    txt=f"""🤖 **Z-BOT V18 SAFE - REAL ONLY** 🤖\n\n💎 IQ: {'✅' if IQ_CONNECTED else '❌ False - Retrying...'} | 💰 DEMO ${bal_demo:.2f}\n🏆 W:{STATS['wins']} L:{STATS['loss']} | 🔥 {STATS['streak']}\n📍 {get_mode_text()}\n🧠 AI: Learning + Auto-Block + Daily Max Loss -${DAILY_MAX_LOSS:.0f}\n📰 News Filter: ON | ⏳ 1 Signal at a time, 10 min cooldown\n📍 Trend + Pullback + Bounce | Auto Expiry 2/3 Min | Pullback Martingale\n⛔ OTC Disabled - REAL signals start 7AM\n\n👇 **Select:**\n"""
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
        saved = PENDING_MANUAL.get(pair, {"rsi":0, "adx":0, "reason":"Manual Trade EMA RSI MACD"})
        real_rsi = saved.get("rsi", 0)
        real_adx = saved.get("adx", 0)
        real_reason = saved.get("reason", "Manual Trade EMA RSI MACD")
        if is_win:
            profit = round(amt * payout, 2)
            STATS['wins'] += 1; STATS['streak'] += 1; OTC_MARTI["loss_streak"] = 0
            OTC_SESSION_RESULTS.append({"pair":pair,"dir":direction,"conf":conf,"pnl":profit,"win":True,"amt":amt,"level":level,"time":now_str})
            ai_save_trade(pair, direction, conf, real_rsi, real_adx, payout, real_reason, amt, level, True)
            mk = types.InlineKeyboardMarkup(row_width=2)
            mk.add(types.InlineKeyboardButton("📈 TRADE REAL", callback_data="trade_real"), types.InlineKeyboardButton("📊 STATS", callback_data="stats"))
            bot.send_message(cid, f"""✅ **WINNER! ✅ - MANUAL RESULT**\n\n━━━━━━━━━━━━━━━\n💰 **Profit:** +${profit:.2f}\n💱 **Pair:** {PAIR_EMOJI.get(pair,pair)} {direction}\n💵 **Amount:** ${amt:.2f} | Level {level} ({level}x)\n🎯 **Conf:** {conf:.0f}% | Payout {p_int}%\n🏆 **Stats:** W:{STATS['wins']} L:{STATS['loss']} | 🔥 Streak {STATS['streak']}\n━━━━━━━━━━━━━━━\n\n♻️ Reset to Level 1 - ${OTC_MARTI['base']:.2f} next trade\n🧠 AI don save am, e go learn from am\n🎉 Congratulations!""", reply_markup=mk, parse_mode="Markdown")
        else:
            STATS['loss'] += 1; STATS['streak'] = 0
            OTC_SESSION_RESULTS.append({"pair":pair,"dir":direction,"conf":conf,"pnl":-amt,"win":False,"amt":amt,"level":level,"time":now_str})
            ai_save_trade(pair, direction, conf, real_rsi, real_adx, payout, real_reason, amt, level, False)
            if OTC_MARTI["loss_streak"] >= 2:
                OTC_MARTI["loss_streak"] = 0
                mk = types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton("📈 TRADE REAL", callback_data="trade_real"), types.InlineKeyboardButton("📊 STATS", callback_data="stats"))
                bot.send_message(cid, f"""❌ **LOSS - MANUAL RESULT**\n\n━━━━━━━━━━━━━━━\n💸 **Loss:** -${amt:.2f}\n💱 **Pair:** {PAIR_EMOJI.get(pair,pair)} {direction}\n💵 **Amount:** ${amt:.2f} | Level {level} ({level}x)\n🎯 **Conf:** {conf:.0f}%\n📊 **Stats:** W:{STATS['wins']} L:{STATS['loss']}\n━━━━━━━━━━━━━━━\n\n⛔ 1-2-4 done. Reset to Level 1 - ${OTC_MARTI['base']:.2f}\n🧠 AI don save am, e go avoid this pattern next time""", reply_markup=mk, parse_mode="Markdown")
            else:
                OTC_MARTI["loss_streak"] += 1
                levels = OTC_MARTI["levels"]; next_mult = levels[OTC_MARTI["loss_streak"]]; next_amt = round(OTC_MARTI["base"] * next_mult, 2)
                next_level = OTC_MARTI["loss_streak"]+1
                bot.send_message(cid, f"""❌ **LOSS - MANUAL RESULT**\n\n━━━━━━━━━━━━━━━\n💸 **Loss:** -${amt:.2f}\n💱 **Pair:** {PAIR_EMOJI.get(pair,pair)} {direction}\n💵 **Amount:** ${amt:.2f} | Level {level} ({level}x)\n🎯 **Conf:** {conf:.0f}%\n📊 **Stats:** W:{STATS['wins']} L:{STATS['loss']}\n━━━━━━━━━━━━━━━\n\n⏳ **Level {next_level} - ${next_amt:.2f} - WAITING FOR NEXT PULLBACK**\n🧠 AI don save am\n🚫 DO NOT enter now. Bot go scan {pair} every 20 sec, when fresh pullback + bounce come, I go send Level {next_level} signal.\nIf no pullback in 15 min, I go cancel and save your money.""", parse_mode="Markdown")
                threading.Thread(target=wait_for_pullback_level, args=(pair, direction, next_level, next_amt), daemon=True).start()
        return
    if data=="trade_real":
        locked, pnl_today, trades_today = ai_is_daily_locked()
        if locked:
            bot.send_message(cid, f"🔒 **DAILY LOCKED**\n\nToday PnL: ${pnl_today:+.2f}\nYou don reach Max Loss -${DAILY_MAX_LOSS:.0f} or Max Trades. Rest till tomorrow.")
            return
        mk=types.InlineKeyboardMarkup(row_width=1); mk.add(types.InlineKeyboardButton("🔍 📊 SCAN ALL SAFE NOW (6 PAIRS)",callback_data="scan_all_real"))
        for p in SAFE_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}",callback_data=f"real_pair_{p}"))
        bot.send_message(cid,f"📈 **TRADE SAFE V18**\n📍 {get_mode_text()}\n💰 Today PnL: ${pnl_today:+.2f} | Max -${DAILY_MAX_LOSS:.0f}",reply_markup=mk,parse_mode="Markdown"); return
    if data=="scan_all_real":
        bot.answer_callback_query(c.id,"Scanning 6 SAFE pairs V18..."); scan_msg=bot.send_message(cid,"🔍 **SCANNING 6 SAFE PAIRS V18...**\n\n⏳ ~12 sec"); results=[]; datas={}
        for pair in SAFE_PAIRS:
            now_hour = datetime.now(pytz.timezone("Africa/Lagos")).hour
            is_blocked, _ = ai_should_block(pair, now_hour)
            if is_blocked:
                results.append((pair,0,"-","AI Blocked - Bad winrate","🚫 BLOCKED",180)); continue
            d=analyze_sniper_v12(pair,sniper_mode=False)
            if not d: results.append((pair,0,"-","No data","🔴 NO TRADE",180)); continue
            conf=d['conf']; dir_=d['dir']; reason=d['reason']; exp=d['expiry']
            if conf>=92: status="🟢 READY"
            elif conf>=75: status="🟡 READY"
            else: status="🔴 NO TRADE"
            results.append((pair,conf,dir_,reason,status,exp)); datas[pair]=d
            try: bot.edit_message_text(f"🔍 Scanning V18... {pair} {conf:.0f}%",cid,scan_msg.message_id)
            except: pass
            time.sleep(0.3)
        results.sort(key=lambda x: x[1], reverse=True); txt="📊 **SAFE V18 READINESS** 📊\n"; txt+=f"📍 {get_mode_text()}\n⏰ {datetime.now(pytz.timezone('Africa/Lagos')).strftime('%H:%M:%S WAT')}\n\n"
        for pair,conf,dir_,reason,status,exp in results:
            emoji=PAIR_EMOJI.get(pair,pair)
            if conf>=75: txt+=f"{status} {emoji}: {conf:.0f}% {dir_} Safe {int(exp/60)} min - {reason}\n"
            else: txt+=f"{status} {emoji}: {conf:.0f}% - {reason}\n"
        best = results[0] if results else None
        if best and best[1]>=75: txt+=f"\n💡 **BEST NOW:** {PAIR_EMOJI.get(best[0],best[0])} {best[1]:.0f}% Safe {int(best[5]/60)} min"
        mk=types.InlineKeyboardMarkup(row_width=2)
        if best and best[1]>=75: mk.add(types.InlineKeyboardButton(f"✅ TRADE BEST {best[0]}",callback_data=f"real_pair_{best[0]}"))
        mk.add(types.InlineKeyboardButton("🔄 RE-SCAN ALL",callback_data="scan_all_real"))
        bot.send_message(cid,txt,reply_markup=mk,parse_mode="Markdown")
        if best and best[1]>=75 and best[0] in datas:
            time.sleep(0.5); best_data=datas[best[0]]; tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=45); exp=best_data['expiry']; exp_min=int(exp/60); dir_e="🟢 CALL ⬆️" if best_data['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]
            amt_m, mult_m, lvl_m = get_manual_amt_and_level()
            pnl_today2, _, _, _ = ai_daily_stats()
            PENDING_MANUAL[best_data['pair']] = {"rsi": best_data.get('rsi',0), "adx": best_data.get('adx',0), "reason": best_data.get('reason',''), "conf": best_data.get('conf',0)}
            signal_txt=f"""📡 **SAFE TOP SIGNAL V18 - AUTO EXPIRY {exp_min} MIN** 📡\n\n💱 {PAIR_EMOJI.get(best_data['pair'],best_data['pair'])}\n📊 {dir_e} | 🎯 {best_data['conf']:.0f}% SNIPER\n📈 {best_data['reason']} | RSI {best_data['rsi']:.1f}\n💸 {int(best_data['payout']*100)}% | 💰 {best_data['price']:.5f} | ⏱️ {exp_min} Min | 🤖 Bot choose {exp_min} Min - Conf {best_data['conf']:.0f}%\n💰 Today PnL: ${pnl_today2:+.2f} | Max -${DAILY_MAX_LOSS:.0f}\n\n⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)\n\n**Level 1:** {entry.strftime('%H:%M:%S')} - {exp_min} Min - ${base:.2f} - ENTER NOW\n**Level 2:** ⏳ WAIT - Bot go send when next pullback come - ${base*2:.2f}\n**Level 3:** ⏳ WAIT - Bot go send when next pullback come - ${base*4:.2f}\n\n⚠️ DO NOT enter Level 2/3 by time. Wait for next message.\n⛔ STOP after Level 3.\n\n👇 After you trade manually, press result below:"""
            bot.send_message(cid,signal_txt,parse_mode="Markdown", reply_markup=manual_result_keyboard(best_data['pair'], best_data['dir'], best_data['conf'], amt_m, mult_m, best_data['payout']))
        return
    if data.startswith("real_pair_"):
        pair=data.replace("real_pair_","")
        now_hour = datetime.now(pytz.timezone("Africa/Lagos")).hour
        is_blocked, block_reason = ai_should_block(pair, now_hour)
        if is_blocked:
            bot.send_message(cid, f"🚫 **AI BLOCKED {pair}**\n\n{block_reason}\n\nBot dey protect you. Try another pair.")
            return
        news_blocked, news_reason = is_news_time(pair, 30, 30)
        if news_blocked:
            bot.send_message(cid, f"📰 **NEWS BLOCK**\n\n{news_reason}\n\nWait till news pass, bot go allow trade again.")
            return
        bot.answer_callback_query(c.id,f"Scanning {pair} V18..."); scan_msg=bot.send_message(cid,f"🔍 **V18 SAFE SCAN {PAIR_EMOJI.get(pair,pair)}**\n\n0%\n🚀 Sniper..."); legit_live_scan(cid,scan_msg.message_id,pair); d=analyze_sniper_v12(pair,sniper_mode=False)
        if not d or d['conf'] < 75:
            mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🔄 RETRY",callback_data=f"real_pair_{pair}"),types.InlineKeyboardButton("📈 SCAN ALL",callback_data="scan_all_real"))
            bot.send_message(cid,f"⚠️ **No safe trade now for {pair}**\n\n📊 Conf: {d['conf'] if d else 0}% < 75%\n🛡️ {d['reason'] if d else 'No data'}",reply_markup=mk); return
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=45); exp=d['expiry']; exp_min=int(exp/60); dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]
        amt_m, mult_m, lvl_m = get_manual_amt_and_level()
        pnl_today2, _, _, _ = ai_daily_stats()
        PENDING_MANUAL[pair] = {"rsi": d.get('rsi',0), "adx": d.get('adx',0), "reason": d.get('reason',''), "conf": d.get('conf',0)}
        signal_txt=f"""📡 **SAFE SIGNAL V18 - AUTO EXPIRY {exp_min} MIN** 📡\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n📊 {dir_e} | 🎯 {d['conf']:.0f}% SNIPER\n📈 {d['reason']} | RSI {d['rsi']:.1f} | ATR {d['atr']:.5f}\n💸 {int(d['payout']*100)}% | 💰 {d['price']:.5f}\n📍 Session: {d.get('session','')} | S/R: {d.get('sr','')}\n⏱️ {exp_min} Min | 🤖 Bot choose {exp_min} Min - Conf {d['conf']:.0f}%\n💰 Today PnL: ${pnl_today2:+.2f} | Max -${DAILY_MAX_LOSS:.0f}\n\n⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)\n⏱️ EXPIRY: {exp_min} Min Each Level\n\n**Level 1:** {entry.strftime('%H:%M:%S')} - {exp_min} Min - ${base:.2f} - ENTER NOW\n**Level 2:** ⏳ WAIT - Bot go send when next pullback come - ${base*2:.2f}\n**Level 3:** ⏳ WAIT - Bot go send when next pullback come - ${base*4:.2f}\n\n⚠️ DO NOT enter Level 2/3 by time. Wait for next message.\n⛔ STOP after Level 3.\n⚠️ **MANUAL PLACE**\n\n👇 After you trade manually, press result below:"""
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
        bot.send_message(cid,f"📊 **STATS V18 SAFE**\n📍 {get_mode_text()}\n🏆 Wins: {STATS['wins']}\n❌ Loss: {STATS['loss']}\n📈 Winrate: {wr:.1f}%\n🔥 Streak: {STATS['streak']}\n💰 Bal: ${bal:.2f}\n🧠 AI: Learning + Block + Daily Max -${DAILY_MAX_LOSS:.0f} | 📦 OTC: DISABLED | REAL only",reply_markup=mk,parse_mode="Markdown")
    if data=="settings":
        bot.send_message(cid,f"⚙️ **SETTINGS V18 SAFE REAL ONLY**\n\n🛡️ V18: Trend + Pullback + Bounce - No chase\n⏱️ Expiry: AUTO - 94%+ = 2 Min, 92-93% = 3 Min (Bot decide)\n🧠 AI: Auto-adjust weights after every 5 trades\n🚫 Auto-Block: Block pair/hour if winrate <35% after 5 trades\n🔒 Daily Max Loss: -${DAILY_MAX_LOSS:.0f} | Max Trades: {DAILY_MAX_TRADES}\n⏳ Cooldown: 10 min - 1 signal at a time, pause before next scan\n📰 News Filter: ON - Block 30 min before/after High news\n📍 S/R: ON - Block CALL near Resistance, Block PUT near Support\n⏰ Session: Golden 9-11AM & 2:30-4:30PM only - Lunch/Late blocked\n📉 Pullback: ON - Must touch EMA, bounce, then enter\n🔁 Martingale: Pullback Martingale - Level 2/3 wait for next pullback, 15 min timeout\n🔙 Backtest: /backtest EURUSD\n📊 OTC: DISABLED\nREAL: 7AM-8PM auto signals\n")

if __name__ == "__main__":
    threading.Thread(target=background_iq, daemon=True).start()
    threading.Thread(target=real_signal_scanner, daemon=True).start()
    threading.Thread(target=daily_8pm_report, daemon=True).start()
    threading.Thread(target=nightly_backup_to_telegram, daemon=True).start()
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
