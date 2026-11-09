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
DAILY_MAX_LOSS = 20.0
DAILY_MAX_TRADES = 30
SIGNAL_COOLDOWN = 300
LAST_SIGNAL_TIME = 0

REAL_PAIRS = ["EURUSD","GBPUSD","USDJPY","EURGBP","AUDUSD","USDCAD","EURJPY","GBPJPY","USDCHF","AUDJPY","EURAUD","GBPCHF","EURCHF","NZDUSD","GBPAUD","EURCAD","AUDCAD","GBPCAD","NZDJPY","AUDNZD","CHFJPY","CADJPY"]
OTC_PAIRS = ["EURUSD-OTC","GBPUSD-OTC","USDJPY-OTC","AUDUSD-OTC","USDCAD-OTC","EURGBP-OTC","EURJPY-OTC","GBPJPY-OTC","AUDJPY-OTC","EURAUD-OTC","GBPAUD-OTC","NZDUSD-OTC","GBPCHF-OTC","EURCHF-OTC","USDCHF-OTC","AUDCAD-OTC","EURCAD-OTC","CADJPY-OTC","NZDJPY-OTC"]
PAIR_EMOJI = {"EURUSD":"🇪🇺 EUR/USD","GBPUSD":"🇬🇧 GBP/USD","USDJPY":"🇺🇸 USD/JPY","EURGBP":"🇪🇺 EUR/GBP","AUDUSD":"🇦🇺 AUD/USD","USDCAD":"🇺🇸 USD/CAD","EURJPY":"🇪🇺 EUR/JPY","GBPJPY":"🇬🇧 GBP/JPY","USDCHF":"🇺🇸 USD/CHF","AUDJPY":"🇦🇺 AUD/JPY","EURAUD":"🇪🇺 EUR/AUD","GBPCHF":"🇬🇧 GBP/CHF","EURCHF":"🇪🇺 EUR/CHF","NZDUSD":"🇳🇿 NZD/USD","GBPAUD":"🇬🇧 GBP/AUD","EURCAD":"🇪🇺 EUR/CAD","AUDCAD":"🇦🇺 AUD/CAD","GBPCAD":"🇬🇧 GBP/CAD","NZDJPY":"🇳🇿 NZD/JPY","AUDNZD":"🇦🇺 AUD/NZD","CHFJPY":"🇨🇭 CHF/JPY","CADJPY":"🇨🇦 CAD/JPY","EURUSD-OTC":"🇪🇺 EUR/USD OTC","GBPUSD-OTC":"🇬🇧 GBP/USD OTC","EURGBP-OTC":"🇪🇺 EUR/GBP OTC","USDJPY-OTC":"🇺🇸 USD/JPY OTC","GBPJPY-OTC":"🇬🇧 GBP/JPY OTC","AUDUSD-OTC":"🇦🇺 AUD/USD OTC","USDCHF-OTC":"🇺🇸 USD/CHF OTC","EURJPY-OTC":"🇪🇺 EUR/JPY OTC","AUDJPY-OTC":"🇦🇺 AUD/JPY OTC","EURAUD-OTC":"🇪🇺 EUR/AUD OTC","GBPAUD-OTC":"🇬🇧 GBP/AUD OTC","NZDUSD-OTC":"🇳🇿 NZD/USD OTC","GBPCHF-OTC":"🇬🇧 GBP/CHF OTC","EURCHF-OTC":"🇪🇺 EUR/CHF OTC","USDCAD-OTC":"🇺🇸 USD/CAD OTC","AUDCAD-OTC":"🇦🇺 AUD/CAD OTC","EURCAD-OTC":"🇪🇺 EUR/CAD OTC","CADJPY-OTC":"🇨🇦 CAD/JPY OTC","NZDJPY-OTC":"🇳🇿 NZD/JPY OTC"}

DB_FILE = "zbot_memory.db"
def ai_init_db():
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY AUTOINCREMENT, pair TEXT, direction TEXT, conf REAL, rsi REAL, adx REAL, payout REAL, reason TEXT, amt REAL, level INTEGER, win INTEGER, hour INTEGER, weekday INTEGER, created_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS ai_weights (key TEXT PRIMARY KEY, weight REAL)""")
    defaults = {"EMA":18, "RSI":15, "MOM":12, "MACD":10, "ADX":12, "VOL":8, "STOCH":5}
    for k,v in defaults.items():
        cur.execute("INSERT OR IGNORE INTO ai_weights VALUES (?,?)", (k,v))
    con.commit(); con.close()
def ai_save_trade(pair, direction, conf, rsi, adx, payout, reason, amt, level, win):
    try:
        tz = pytz.timezone("Africa/Lagos"); now = datetime.now(tz)
        con = sqlite3.connect(DB_FILE); cur = con.cursor()
        cur.execute("INSERT INTO trades (pair,direction,conf,rsi,adx,payout,reason,amt,level,win,hour,weekday,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (pair, direction, conf, rsi, adx, payout, reason, amt, level, 1 if win else 0, now.hour, now.weekday(), now.strftime('%Y-%m-%d %H:%M:%S')))
        con.commit(); con.close(); ai_learn()
    except Exception as e: print(f"[AI] Save err {e}")
def ai_get_weights():
    try:
        con = sqlite3.connect(DB_FILE); cur = con.cursor(); cur.execute("SELECT key, weight FROM ai_weights"); d = dict(cur.fetchall()); con.close(); return d
    except: return {"EMA":18, "RSI":15, "MOM":12, "MACD":10, "ADX":12, "VOL":8, "STOCH":5}
def ai_learn():
    try:
        con = sqlite3.connect(DB_FILE); cur = con.cursor()
        cur.execute("SELECT reason, win FROM trades ORDER BY id DESC LIMIT 100"); rows = cur.fetchall()
        if len(rows) < 5: con.close(); return
        from collections import defaultdict
        stats = defaultdict(lambda: [0,0])
        for reason, win in rows:
            if not reason: continue
            for key in ["EMA", "RSI", "Mom", "MACD", "ADX", "Vol", "BB", "Pin", "Engulf"]:
                if key.lower() in reason.lower() or key in reason: stats[key][0] += 1; stats[key][1] += win
        weights = ai_get_weights()
        for key, (total, wins) in stats.items():
            if total >= 3:
                wr = wins / total; map_key = {"Mom":"MOM", "Vol":"VOL"}.get(key, key.upper())
                if map_key not in weights: continue
                old = weights[map_key]
                if wr < 0.40:
                    new = max(2, old - 3); cur.execute("UPDATE ai_weights SET weight=? WHERE key=?", (new, map_key))
                elif wr > 0.70:
                    new = min(25, old + 1); cur.execute("UPDATE ai_weights SET weight=? WHERE key=?", (new, map_key))
        con.commit(); con.close()
    except Exception as e: print(f"[AI Learn err] {e}")
def ai_get_insight():
    try:
        con = sqlite3.connect(DB_FILE); cur = con.cursor()
        cur.execute("SELECT COUNT(*), SUM(win) FROM trades"); total, wins = cur.fetchone(); total = total or 0; wins = wins or 0
        cur.execute("SELECT pair, COUNT(*), SUM(win) FROM trades GROUP BY pair ORDER BY COUNT(*) DESC LIMIT 3"); best_pairs = cur.fetchall()
        cur.execute("SELECT hour, COUNT(*), SUM(win) FROM trades GROUP BY hour ORDER BY COUNT(*) DESC LIMIT 3"); best_hours = cur.fetchall()
        cur.execute("SELECT conf, win FROM trades ORDER BY id DESC LIMIT 50"); rows = cur.fetchall()
        high = [w for c,w in rows if c >= 88]; low = [w for c,w in rows if c < 88]
        high_wr = f"{sum(high)/len(high)*100:.0f}%" if high else "No data"; low_wr = f"{sum(low)/len(low)*100:.0f}%" if low else "No data"
        weights = ai_get_weights(); con.close()
        return total, wins, best_pairs, best_hours, high_wr, low_wr, weights
    except Exception as e: return 0,0,[],[],"0%","0%",{}
def ai_should_block(pair, hour):
    try:
        con = sqlite3.connect(DB_FILE); cur = con.cursor()
        cur.execute("SELECT COUNT(*), SUM(win) FROM trades WHERE pair=? AND hour=?", (pair, hour)); total, wins = cur.fetchone(); con.close(); total = total or 0; wins = wins or 0
        if total >= 5:
            wr = wins / total if total else 1
            if wr < 0.35: return True, f"AI Blocked {pair} {hour}:00 - Winrate {wr:.0%} ({wins}/{total})"
        con = sqlite3.connect(DB_FILE); cur = con.cursor()
        cur.execute("SELECT COUNT(*), SUM(win) FROM trades WHERE pair=?", (pair,)); total2, wins2 = cur.fetchone(); con.close(); total2 = total2 or 0; wins2 = wins2 or 0
        if total2 >= 10:
            wr2 = wins2 / total2 if total2 else 1
            if wr2 < 0.30: return True, f"AI Blocked {pair} - Overall Winrate {wr2:.0%} ({wins2}/{total2})"
        return False, ""
    except Exception as e: print(f"[Block err] {e}"); return False, ""
def ai_daily_stats():
    try:
        tz = pytz.timezone("Africa/Lagos"); today = datetime.now(tz).strftime('%Y-%m-%d')
        con = sqlite3.connect(DB_FILE); cur = con.cursor()
        cur.execute("SELECT amt, win, payout FROM trades WHERE created_at LIKE ?", (today + "%",)); rows = cur.fetchall(); con.close()
        total_pnl = 0; total_trades = len(rows); wins = sum(1 for _, w, _ in rows if w == 1)
        for amt, win, payout in rows:
            p = payout if payout else 0.85
            if win: total_pnl += amt * p
            else: total_pnl -= amt
        return total_pnl, total_trades, wins, total_trades - wins
    except Exception as e: print(f"[Daily stats err] {e}"); return 0, 0, 0, 0
def ai_is_daily_locked():
    pnl, total, wins, losses = ai_daily_stats()
    if pnl <= -DAILY_MAX_LOSS: return True, pnl, total
    if total >= DAILY_MAX_TRADES: return True, pnl, total
    return False, pnl, total
ai_init_db()

STATS = {"balance":0.0,"real_balance":0.0,"wins":0,"loss":0,"streak":0}
try:
    _t, _w, _, _, _, _, _ = ai_get_insight(); STATS["wins"] = _w; STATS["loss"] = _t - _w
    _con = sqlite3.connect(DB_FILE); _cur = _con.cursor(); _cur.execute("SELECT win FROM trades ORDER BY id DESC LIMIT 20"); _streak = 0
    for (_win,) in _cur.fetchall():
        if _win == 1: _streak += 1
        else: break
    _con.close(); STATS["streak"] = _streak
    print(f"[V20] Loaded W:{STATS['wins']} L:{STATS['loss']} Streak:{_streak}")
except Exception as e: print(f"[V20] Load err {e}")

user_states = {}; AUTO_STATE = {}; IQ_LOCK = threading.Lock()
IQ_CONNECTED=False; iq=None; PAYOUT_CACHE={}; PAYOUT_TIME=0
OTC_SESSION_RESULTS = []
OTC_MARTI = {"loss_streak":0, "base":1.0, "bal":"PRACTICE", "levels":[1,2,4]}
PENDING_MANUAL = {}

def get_expiry_by_conf(conf):
    if conf >= 95: return 120
    elif conf >= 92: return 180
    elif conf >= 88: return 300
    else: return 180
def get_expiry_text(sec): return f"{int(sec//60)} Min"
PENDING_RECOVERY = {}; RECOVERY_TIMEOUT = 900
def start_recovery_scan(pair, direction, next_level, next_amt, payout, orig_conf):
    PENDING_RECOVERY[pair] = {"direction": direction, "level": next_level, "amt": next_amt, "payout": payout, "orig_conf": orig_conf, "start": time.time()}
    print(f"[RECOVERY] Started {pair} L{next_level} ${next_amt} - MAIN SCANNER LOCKED")

NEWS_CACHE = {"time": 0, "events": []}
def fetch_news_events():
    global NEWS_CACHE
    if time.time() - NEWS_CACHE["time"] < 3600 and NEWS_CACHE["events"]: return NEWS_CACHE["events"]
    try:
        r = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json", timeout=10); events = r.json(); NEWS_CACHE = {"time": time.time(), "events": events}; return events
    except Exception as e: print(f"[NEWS] {e}"); return []
def is_news_time(pair="EURUSD", minutes_before=30, minutes_after=30):
    try:
        tz = pytz.timezone("Africa/Lagos"); now = datetime.now(tz); base = pair[:3]; quote = pair[3:6] if len(pair) >= 6 else "USD"; pair_currencies = set([base, quote]); events = fetch_news_events()
        for ev in events:
            try:
                if ev.get("impact", "") != "High": continue
                if ev.get("currency", "") not in pair_currencies: continue
                ev_time = datetime.fromisoformat(ev.get("date", "").replace("Z","+00:00")); ev_time_lagos = ev_time.astimezone(tz); diff_min = (ev_time_lagos - now).total_seconds() / 60
                if -minutes_after <= diff_min <= minutes_before: return True, f"📰 NEWS BLOCK: {ev.get('currency')} {ev.get('title')} {ev_time_lagos.strftime('%H:%M')} - {int(diff_min)} min away."
            except: continue
        return False, ""
    except Exception as e: print(f"[NEWS check] {e}"); return False, ""
def run_backtest(pair="EURUSD", candles_to_test=100):
    try:
        df = get_candles(pair)
        if df is None or len(df) < 50: return None
        wins = 0; losses = 0
        for i in range(max(30, len(df)-candles_to_test), len(df)-2):
            row = df.iloc[i]; closes = df['close'].iloc[:i+1]; ema9 = closes.ewm(9).mean().iloc[-1]; ema21 = closes.ewm(21).mean().iloc[-1]; rsi_vals = calc_rsi(closes, 7); r7 = float(rsi_vals.iloc[-1]) if len(rsi_vals) > 0 else 50; is_green = float(row['close']) > float(row['open'])
            if is_green and ema9 > ema21 and 45 <= r7 <= 70: pred = "CALL"
            elif not is_green and ema9 < ema21 and 30 <= r7 <= 55: pred = "PUT"
            else: continue
            next_candle = df.iloc[i+1]; actual = "CALL" if float(next_candle['close']) > float(next_candle['open']) else "PUT"
            if pred == actual: wins += 1
            else: losses += 1
        total = wins + losses; wr = (wins/total*100) if total else 0; return {"pair": pair, "total": total, "wins": wins, "losses": losses, "winrate": wr}
    except Exception as e: print(f"[BACKTEST] {e}"); return None

def get_support_resistance(df):
    try:
        last = df.tail(50); highs = last['max'].tolist(); lows = last['min'].tolist(); resistances = []; supports = []
        for i in range(2, len(last)-2):
            h = float(last['max'].iloc[i]); l = float(last['min'].iloc[i])
            if h > float(last['max'].iloc[i-1]) and h > float(last['max'].iloc[i-2]) and h > float(last['max'].iloc[i+1]) and h > float(last['max'].iloc[i+2]): resistances.append(h)
            if l < float(last['min'].iloc[i-1]) and l < float(last['min'].iloc[i-2]) and l < float(last['min'].iloc[i+1]) and l < float(last['min'].iloc[i+2]): supports.append(l)
        c_now = float(df['close'].iloc[-1]); res_above = [r for r in resistances if r > c_now]; sup_below = [s for s in supports if s < c_now]
        nearest_res = min(res_above, key=lambda x: abs(x - c_now)) if res_above else float(max(highs)); nearest_sup = max(sup_below, key=lambda x: abs(x - c_now)) if sup_below else float(min(lows)); return nearest_sup, nearest_res
    except: return None, None
def get_session_info():
    try:
        tz = pytz.timezone("Africa/Lagos"); now = datetime.now(tz); time_float = now.hour + now.minute/60
        if 9 <= time_float < 11: return "LONDON", True, "London Open"
        elif 14.5 <= time_float < 16.5: return "NEWYORK", True, "New York Open"
        elif 7 <= time_float < 9: return "EARLY", False, "Early - Slow"
        elif 11 <= time_float < 14.5: return "LUNCH", False, "Lunch - Dead"
        elif 16.5 <= time_float < 20: return "LATE", False, "Late - Tired"
        else: return "OFF", False, "Off Hours"
    except: return "UNKNOWN", False, ""
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
def get_mode_text(): return "REAL 7AM-8PM" if is_real_hours() else "Waiting 7AM"
def manual_result_keyboard(pair, direction, conf, amt, level, payout):
    mk = types.InlineKeyboardMarkup(row_width=2); p_int = int(round(float(payout)*100))
    mk.add(types.InlineKeyboardButton("✅ I WON", callback_data=f"manual_win_{pair}_{direction}_{int(conf)}_{amt}_{level}_{p_int}"), types.InlineKeyboardButton("❌ I LOST", callback_data=f"manual_loss_{pair}_{direction}_{int(conf)}_{amt}_{level}_{p_int}"))
    return mk
def get_manual_amt_and_level():
    levels = OTC_MARTI["levels"]; idx = OTC_MARTI["loss_streak"] % len(levels); mult = levels[idx]; amt = round(OTC_MARTI["base"] * mult, 2); return amt, mult, idx+1

@app.route("/")
def home(): return f"V20 RUNNING IQ:{IQ_CONNECTED} {datetime.now(pytz.timezone('Africa/Lagos')).strftime('%H:%M:%S')}"
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
                except Exception as pe: print(f"[IQ] Proxy {pe}")
            logging.disable(logging.CRITICAL); iq.connect(); IQ_CONNECTED=iq.check_connect()
            if IQ_CONNECTED:
                try: iq.change_balance("PRACTICE"); time.sleep(1); bal = iq.get_balance(); STATS["real_balance"]=bal; print(f"[IQ] BAL ${bal}")
                except: pass
                return
            time.sleep(8)
        except Exception as e: print(f"[IQ] Fail {attempt+1}: {e}"); time.sleep(10)
    IQ_CONNECTED=False; print("[IQ] FAILED")
def iq_reconnect():
    global iq, IQ_CONNECTED
    try:
        from iqoptionapi.stable_api import IQ_Option; logging.disable(logging.CRITICAL); iq=IQ_Option(os.getenv("IQ_EMAIL"),os.getenv("IQ_PASS")); PROXY=os.getenv("PROXY_URL")
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
        with IQ_LOCK:
            logging.disable(logging.CRITICAL); all_p=iq.get_all_profit()
            if pair in all_p:
                for k in ['blitz','turbo','binary']:
                    if k in all_p[pair]: PAYOUT_CACHE[pair]=float(all_p[pair][k]); PAYOUT_TIME=time.time(); return float(all_p[pair][k])
        return 0.85
    except: return PAYOUT_CACHE.get(pair,0.85)
def get_candles(pair):
    if not IQ_CONNECTED and not iq_reconnect(): return None
    if pair not in REAL_PAIRS and pair not in OTC_PAIRS: return None
    for _ in range(2):
        try:
            with IQ_LOCK: logging.disable(logging.CRITICAL); c=iq.get_candles(pair,60,50,time.time())
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
    steps = [(0,"🚀 Init...",0.15),(50,"📊 Scanning...",0.2),(100,"🔒 LOCKED!",0.3)]
    for pct, text, delay in steps:
        filled=int(pct//5); bar="█"*filled+"░"*(20-filled)
        txt=f"**Z-BOT V20**\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n\n{bar} {pct}%\n🔍 {text}"
        try: bot.edit_message_text(txt,cid,mid,parse_mode="Markdown")
        except: pass
        time.sleep(delay)
def calc_adx_v12(df, period=14):
    try:
        high=df['max']; low=df['min']; close=df['close']; tr1=high-low; tr2=(high-close.shift()).abs(); tr3=(low-close.shift()).abs(); tr=pd.concat([tr1,tr2,tr3],axis=1).max(axis=1); atr=tr.rolling(period).mean(); up=high-high.shift(); down=low.shift()-low; plus_dm=((up>down)&(up>0))*up; minus_dm=((down>up)&(down>0))*down; plus_di=100*(plus_dm.rolling(period).mean()/atr); minus_di=100*(minus_dm.rolling(period).mean()/atr); dx=100*((plus_di-minus_di).abs()/(plus_di+minus_di)); adx=dx.rolling(period).mean().iloc[-1]; return float(adx), float(plus_di.iloc[-1]), float(minus_di.iloc[-1])
    except: return 0, 0, 0
def analyze_sniper_v12(pair, sniper_mode=False):
    df = get_candles(pair)
    if df is None: return None
    try:
        df5 = None
        try:
            with IQ_LOCK: logging.disable(logging.CRITICAL); c5 = iq.get_candles(pair, 300, 30, time.time())
            if c5 and len(c5) > 20: df5 = pd.DataFrame(sorted(c5, key=lambda x: x['from']))
        except: df5 = None
        close=df['close']; open_=df['open']; high=df['max']; low=df['min']; vol = df['volume'] if 'volume' in df else pd.Series([1]*len(df))
        ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean(); ema50=close.ewm(50).mean(); rsi7=calc_rsi(close,7); rsi14=calc_rsi(close,14); atr=calc_atr(df,14); adx, pdi, mdi = calc_adx_v12(df)
        ema12=close.ewm(12).mean(); ema26=close.ewm(26).mean(); macd=ema12-ema26; signal=macd.ewm(9).mean(); macd_val=float(macd.iloc[-1]); sig_val=float(signal.iloc[-1])
        sma20=close.rolling(20).mean(); std20=close.rolling(20).std(); upper=float((sma20+2*std20).iloc[-1]); lower=float((sma20-2*std20).iloc[-1])
        low14=low.rolling(14).min(); high14=high.rolling(14).max(); stoch=100*(close-low14)/(high14-low14); stoch_val=float(stoch.iloc[-1])
        c_now=float(close.iloc[-1]); o_now=float(open_.iloc[-1]); c_prev=float(close.iloc[-2]); o_prev=float(open_.iloc[-2]); h_now=float(high.iloc[-1]); l_now=float(low.iloc[-1]); e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1]); e50=float(ema50.iloc[-1]); r7=float(rsi7.iloc[-1]); r14=float(rsi14.iloc[-1]); mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100; mom3=(close.iloc[-1]-close.iloc[-4])/close.iloc[-4]*100
        body=abs(c_now-o_now); upper_wick=h_now-max(c_now,o_now); lower_wick=min(c_now,o_now)-l_now; is_green=c_now>o_now; payout=get_payout(pair); sig="CALL" if is_green else "PUT"
        if adx < 18: return {"pair":pair,"dir":sig,"conf":42,"price":c_now,"rsi":r7,"adx":adx,"reason":"Choppy","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if body < atr*0.30: return {"pair":pair,"dir":sig,"conf":48,"price":c_now,"rsi":r7,"adx":adx,"reason":"Doji","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if payout < 0.70: return {"pair":pair,"dir":sig,"conf":52,"price":c_now,"rsi":r7,"adx":adx,"reason":f"Low Payout {int(payout*100)}%","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        score=30; reasons=[]; w = ai_get_weights()
        if df5 is not None:
            c5=df5['close']; e9_5=c5.ewm(9).mean(); e21_5=c5.ewm(21).mean(); trend_5m = 1 if float(e9_5.iloc[-1]) > float(e21_5.iloc[-1]) else -1
            if (is_green and trend_5m==-1) or (not is_green and trend_5m==1): score-=18; reasons.append("Against 5M")
            else: score+=12; reasons.append("5M Align")
        if is_green:
            if e9>e21>e50: score+=w.get("EMA",18); reasons.append("EMA Bull")
            elif e9>e21: score+=10
            else: score-=8
        else:
            if e9<e21<e50: score+=w.get("EMA",18); reasons.append("EMA Bear")
            elif e9<e21: score+=10
            else: score-=8
        if adx >= 28: score+=w.get("ADX",12); reasons.append(f"ADX {adx:.0f}")
        elif adx >= 22: score+=7
        if is_green and pdi > mdi: score+=8
        elif not is_green and mdi > pdi: score+=8
        else: score-=10
        if is_green:
            if 52 <= r7 <= 65 and 48 <= r14 <= 62: score+=w.get("RSI",15); reasons.append(f"RSI {r7:.0f}")
            elif r7 > 75 or r7 < 45: score-=12
            else: score+=6
        else:
            if 35 <= r7 <= 48 and 38 <= r14 <= 52: score+=w.get("RSI",15); reasons.append(f"RSI {r7:.0f}")
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
        bull_eng = c_now > o_prev and o_now < c_prev and is_green and c_prev < o_prev; bear_eng = c_now < o_prev and o_now > c_prev and not is_green and c_prev > o_prev; pin_bull = lower_wick > body*1.8 and lower_wick > upper_wick*1.5 and is_green; pin_bear = upper_wick > body*1.8 and upper_wick > lower_wick*1.5 and not is_green
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
        if is_green and c_now > upper: score+=5; reasons.append("BB Break")
        if not is_green and c_now < lower: score+=5; reasons.append("BB Break")
        avg_vol=float(vol.rolling(20).mean().iloc[-1]) if len(vol)>20 else 1; curr_vol=float(vol.iloc[-1]) if len(vol)>0 else 1
        if curr_vol > avg_vol*1.2: score+=w.get("VOL",8); reasons.append("Vol Spike")
        elif curr_vol > avg_vol: score+=4
        sup, res = get_support_resistance(df); sr_info = ""
        if sup is not None and res is not None:
            dist_to_res = abs(c_now - res) / atr if atr > 0 else 999; dist_to_sup = abs(c_now - sup) / atr if atr > 0 else 999
            if is_green:
                if dist_to_res < 0.8: score -= 15; reasons.append("Near Res"); sr_info = "Near Res"
                elif dist_to_sup < 1.0: score += 10; reasons.append("Bounce Sup"); sr_info = "Sup Bounce"
                else: score += 3; sr_info = "Clear"
            else:
                if dist_to_sup < 0.8: score -= 15; reasons.append("Near Sup"); sr_info = "Near Sup"
                elif dist_to_res < 1.0: score += 10; reasons.append("Reject Res"); sr_info = "Res Reject"
                else: score += 3; sr_info = "Clear"
        sess_name, is_golden, sess_reason = get_session_info()
        if is_golden: score += 6; reasons.append(f"{sess_name}")
        else:
            if sess_name in ["LUNCH", "LATE"]: score -= 8; reasons.append(sess_name)
            elif sess_name == "EARLY": score -= 4; reasons.append(sess_name)
        dist_ema9_pct = abs(c_now - e9) / c_now * 100 if c_now else 0
        if dist_ema9_pct > 0.08: score -= 12; reasons.append("Chasing")
        elif dist_ema9_pct < 0.03: score += 8; reasons.append("Pullback")
        else: score += 2
        score = max(40, min(96, score)); reason = " + ".join(reasons) if reasons else "Weak"
        if is_green and r7 < 45: score = min(score, 88)
        if not is_green and r7 > 55: score = min(score, 88)
        threshold = 88 if is_golden else 92
        if sniper_mode and score < threshold: return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"adx":adx,"reason":reason,"payout":payout,"expiry":get_expiry_by_conf(score),"atr":atr,"rejected":True, "session":sess_name, "sr":sr_info}
        return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"adx":adx,"reason":reason,"payout":payout,"expiry":get_expiry_by_conf(score),"atr":atr,"rejected":False, "session":sess_name, "sr":sr_info}
    except Exception as e: print(f"V12 err {pair} {e}"); return None
def iq_trade(pair,direction,amount,bal,expiry_sec=120):
    if not IQ_CONNECTED and not iq_reconnect(): return False,None,0
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL); iq.change_balance(bal); mins=max(1,int(expiry_sec/60))
            try:
                check,oid=iq.buy(amount,pair,direction.lower(),mins)
                if check: return True,oid,expiry_sec
            except: pass
            if expiry_sec<=90:
                try: _,oid=iq.buy_blitz(pair,amount,direction.lower(),expiry_sec); return True,oid,expiry_sec
                except: pass
            return False,None,0
    except: iq_reconnect(); return False,None,0

def recovery_scanner():
    global LAST_SIGNAL_TIME
    tz=pytz.timezone("Africa/Lagos")
    while True:
        try:
            for pair in list(PENDING_RECOVERY.keys()):
                info = PENDING_RECOVERY[pair]
                if time.time() - info["start"] > RECOVERY_TIMEOUT:
                    del PENDING_RECOVERY[pair]
                    LAST_SIGNAL_TIME = time.time()
                    OTC_MARTI["loss_streak"] = 0
                    try: bot.send_message(OWNER_ID, f"⏰ **L{info['level']} Cancelled - {PAIR_EMOJI.get(pair,pair)}**\nNo pullback in 15 min. Saved ${info['amt']:.2f}. Reset to L1.\nBot go resume after 5 min.", parse_mode="Markdown")
                    except: pass
                    continue
                d = analyze_sniper_v12(pair, sniper_mode=False)
                if not d: continue
                same_dir = (d['dir'] == info['direction']); good_conf = d['conf'] >= 88; is_pullback = ("Pullback" in d['reason'] or "Bounce" in d['reason'] or "Support" in d['reason'] or "Resistance" in d['reason'] or "EMA" in d['reason'])
                if same_dir and good_conf and is_pullback:
                    exp_sec = get_expiry_by_conf(d['conf']); exp_txt = get_expiry_text(exp_sec); now = datetime.now(tz); entry = now + timedelta(seconds=45); dir_e = "🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"
                    PENDING_MANUAL[pair] = {"rsi": d.get('rsi',0), "adx": d.get('adx',0), "reason": d.get('reason',''), "conf": d.get('conf',0)}
                    msg = f"""🔁 **L{info['level']} PULLBACK - {PAIR_EMOJI.get(pair,pair)}**

📊 {dir_e} | {d['conf']:.0f}%
⏰ {entry.strftime('%H:%M:%S')} | ⏱️ {exp_txt} | 💰 ${info['amt']:.2f}
RSI {d['rsi']:.0f} | ADX {d['adx']:.0f}"""
                    try: bot.send_message(OWNER_ID, msg, parse_mode="Markdown", reply_markup=manual_result_keyboard(pair, d['dir'], d['conf'], info['amt'], info['level'], d['payout']))
                    except: pass
                    del PENDING_RECOVERY[pair]
                    # V20: After pullback sent, wait for user to complete trade. Main scanner stays locked via PENDING_MANUAL? No - we use a flag: keep recovery lock until result pressed.
                    # So re-add a lock entry that only clears on WIN/LOSS
                    PENDING_RECOVERY[pair] = {"direction": d['dir'], "level": info['level'], "amt": info['amt'], "payout": info['payout'], "orig_conf": d['conf'], "start": time.time(), "waiting_result": True}
                    print(f"[RECOVERY] Sent L{info['level']} - waiting for result, main locked")
            time.sleep(20)
        except Exception as e: print(f"[Recovery] {e}"); time.sleep(20)

def real_signal_scanner():
    global LAST_SIGNAL_TIME
    last_signal={}; tz=pytz.timezone("Africa/Lagos"); last_lock_msg = 0
    while True:
        try:
            # ===== V20 LOCK: WAIT FOR PULLBACK TO FINISH =====
            if PENDING_RECOVERY:
                # Check if waiting_result - still locked until user press WIN/LOSS or 15 min
                # If waiting_result and 15 min don pass, unlock
                for _p, _info in list(PENDING_RECOVERY.items()):
                    if _info.get("waiting_result") and time.time() - _info["start"] > RECOVERY_TIMEOUT:
                        del PENDING_RECOVERY[_p]
                        LAST_SIGNAL_TIME = time.time()
                        OTC_MARTI["loss_streak"] = 0
                        try: bot.send_message(OWNER_ID, f"⏰ **L{_info['level']} Timeout - {PAIR_EMOJI.get(_p,_p)}**\nYou no press result in 15 min. Reset to L1. Bot resume after 5 min.", parse_mode="Markdown")
                        except: pass
                if PENDING_RECOVERY:
                    print(f"[V20 LOCK] Main paused - waiting pullback/result: {list(PENDING_RECOVERY.keys())}")
                    time.sleep(20)
                    continue
            # ===== END LOCK =====
            if is_real_hours() and IQ_CONNECTED:
                if time.time() - LAST_SIGNAL_TIME < SIGNAL_COOLDOWN:
                    time.sleep(20); continue
                signal_sent_this_round = False
                for pair in REAL_PAIRS:
                    if signal_sent_this_round: break
                    if pair in last_signal and time.time()-last_signal[pair]<600: continue
                    locked, pnl_today, trades_today = ai_is_daily_locked()
                    if locked:
                        if time.time() - last_lock_msg > 3600:
                            try: bot.send_message(OWNER_ID, f"🔒 **LOCKED**\nPnL ${pnl_today:+.2f} | Trades {trades_today}\nRest till tomorrow 7AM.")
                            except: pass
                            last_lock_msg = time.time()
                        time.sleep(300); break
                    now_hour = datetime.now(tz).hour; is_blocked, block_reason = ai_should_block(pair, now_hour)
                    if is_blocked: last_signal[pair] = time.time(); continue
                    news_blocked, news_reason = is_news_time(pair, 30, 30)
                    if news_blocked: last_signal[pair] = time.time(); continue
                    d=analyze_sniper_v12(pair,sniper_mode=True)
                    if d and not d.get('rejected') and d['conf']>=88:
                        now=datetime.now(tz); entry=now+timedelta(seconds=45); exp_sec=get_expiry_by_conf(d['conf']); exp_txt=get_expiry_text(exp_sec); dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]; amt_m, mult_m, lvl_m = get_manual_amt_and_level()
                        PENDING_MANUAL[pair] = {"rsi": d.get('rsi',0), "adx": d.get('adx',0), "reason": d.get('reason',''), "conf": d.get('conf',0)}
                        msg=f"""📡 **{PAIR_EMOJI.get(pair,pair)}**

📊 {dir_e} | {d['conf']:.0f}%
⏰ {entry.strftime('%H:%M:%S')} | ⏱️ {exp_txt} | 💰 L1 ${base:.2f}
RSI {d['rsi']:.0f} | ADX {d['adx']:.0f}
L2 $2 - Wait pullback | L3 $4 - Wait pullback"""
                        try:
                            bot.send_message(OWNER_ID,msg,parse_mode="Markdown", reply_markup=manual_result_keyboard(pair, d['dir'], d['conf'], amt_m, mult_m, d['payout'])); last_signal[pair]=time.time(); LAST_SIGNAL_TIME = time.time(); signal_sent_this_round = True
                        except: pass
                        break
                    time.sleep(3)
            time.sleep(25)
        except: time.sleep(30)

def daily_8pm_report():
    tz = pytz.timezone("Africa/Lagos"); last_sent_date = ""
    while True:
        try:
            now = datetime.now(tz); today_str = now.strftime('%Y-%m-%d')
            if now.hour == 20 and now.minute < 5 and last_sent_date != today_str:
                pnl, total, wins, losses = ai_daily_stats()
                if total > 0:
                    total_all, wins_all, best_pairs, best_hours, high_wr, low_wr, weights = ai_get_insight(); wr_today = (wins/total*100) if total else 0
                    msg = f"🌙 **DAILY - {now.strftime('%A %d %b')}**\nPnL ${pnl:+.2f} | W:{wins} L:{losses} | {wr_today:.0f}%\nHigh Conf WR: {high_wr}\nSee you tomorrow 7AM 😴"
                    try: bot.send_message(OWNER_ID, msg, parse_mode="Markdown")
                    except: pass
                    last_sent_date = today_str
                else:
                    try: bot.send_message(OWNER_ID, f"🌙 **DAILY - {now.strftime('%A %d %b')}**\nNo trade today. See you tomorrow 7AM 😴")
                    except: pass
                    last_sent_date = today_str
            time.sleep(60)
        except Exception as e: print(f"[Report] {e}"); time.sleep(60)
def nightly_backup_to_telegram():
    tz = pytz.timezone("Africa/Lagos"); last_backup = ""
    while True:
        try:
            now = datetime.now(tz); today_str = now.strftime('%Y-%m-%d')
            if now.hour == 20 and now.minute == 5 and last_backup != today_str:
                try:
                    with open(DB_FILE, 'rb') as f: bot.send_document(OWNER_ID, f, caption=f"💾 BACKUP - {today_str}")
                except Exception as e: print(f"[BACKUP] {e}")
                last_backup = today_str
            time.sleep(60)
        except Exception as e: print(f"[Backup] {e}"); time.sleep(60)

@bot.message_handler(content_types=['document'])
def handle_restore(m):
    if not is_allowed(m.from_user.id): bot.send_message(m.chat.id, "❌ Private"); return
    try:
        if not m.document.file_name.endswith('.db'): bot.send_message(m.chat.id, "❌ Send only .db file"); return
        bot.send_message(m.chat.id, "📥 Restoring... wait 5 sec"); file_info = bot.get_file(m.document.file_id); downloaded = bot.download_file(file_info.file_path)
        with open("zbot_memory_restore.db", "wb") as f: f.write(downloaded)
        con = sqlite3.connect("zbot_memory_restore.db"); cur = con.cursor(); cur.execute("SELECT COUNT(*), SUM(win) FROM trades"); total, wins = cur.fetchone(); con.close(); total = total or 0; wins = wins or 0
        import shutil; shutil.copyfile("zbot_memory_restore.db", DB_FILE); STATS["wins"] = wins; STATS["loss"] = total - wins
        try: os.remove("zbot_memory_restore.db")
        except: pass
        bot.send_message(m.chat.id, f"✅ **RESTORED!**\nTotal: {total} | W:{wins} L:{total-wins}", parse_mode="Markdown")
    except Exception as e: bot.send_message(m.chat.id, f"❌ Restore fail: {e}")

@bot.message_handler(commands=['start','stop','mode','balance','results','ai','today','backtest'])
def start(m):
    if not is_allowed(m.from_user.id): bot.send_message(m.chat.id,"❌ Private"); return
    if m.text.startswith('/backtest'):
        parts = m.text.split(); pair_to_test = parts[1].upper() if len(parts) > 1 else "EURUSD"
        if pair_to_test not in REAL_PAIRS: pair_to_test = "EURUSD"
        bot.send_message(m.chat.id, f"🔙 **BACKTESTING {pair_to_test}...** Wait 10 sec...")
        res = run_backtest(pair_to_test, 100)
        if not res or res['total'] == 0: bot.send_message(m.chat.id, "❌ No data, try again"); return
        verdict = "✅ GOOD" if res['winrate'] >= 60 else "⚠️ WEAK" if res['winrate'] < 50 else "🟡 AVERAGE"
        bot.send_message(m.chat.id, f"🔙 **{res['pair']}**\nTested: {res['total']} | W:{res['wins']} L:{res['losses']} | {res['winrate']:.1f}%\n{verdict}", parse_mode="Markdown"); return
    if m.text.startswith('/today'):
        pnl, total, wins, losses = ai_daily_stats(); locked, _, _ = ai_is_daily_locked()
        bot.send_message(m.chat.id, f"📅 **TODAY**\nPnL ${pnl:+.2f} | W:{wins} L:{losses} | {total}\nMax -${DAILY_MAX_LOSS:.0f} | {'🔒 LOCKED' if locked else '✅ OPEN'}", parse_mode="Markdown"); return
    if m.text.startswith('/ai'):
        total, wins, best_pairs, best_hours, high_wr, low_wr, weights = ai_get_insight(); losses = total - wins; wr = (wins/total*100) if total else 0; pnl_today, total_today, _, _ = ai_daily_stats(); locked, _, _ = ai_is_daily_locked()
        txt = f"🧠 **AI**\nTotal {total} | W:{wins} L:{losses} | {wr:.1f}%\nHigh Conf: {high_wr} | Low: {low_wr}\nToday ${pnl_today:+.2f} | {'🔒 LOCKED' if locked else '✅ OPEN'}\n\nBest Pairs:\n"
        for p, t, w in best_pairs: txt += f"• {p}: {w}/{t}\n"
        txt += f"\nWeights: {weights}"
        bot.send_message(m.chat.id, txt, parse_mode="Markdown"); return
    if m.text.startswith('/stop'):
        if m.chat.id in AUTO_STATE: AUTO_STATE[m.chat.id]['running']=False; bot.send_message(m.chat.id,"🛑 Stopping...")
        else: bot.send_message(m.chat.id,"Auto not running"); return
    if m.text.startswith('/results'):
        if not OTC_SESSION_RESULTS: bot.send_message(m.chat.id,"📭 No trades yet"); return
        wins=sum(1 for x in OTC_SESSION_RESULTS if x['win']); losses=len(OTC_SESSION_RESULTS)-wins; pnl_total=sum(x['pnl'] for x in OTC_SESSION_RESULTS)
        txt=f"📊 **RESULTS**\nTotal {len(OTC_SESSION_RESULTS)} | W:{wins} L:{losses} | ${pnl_total:.2f}\n\n"
        for r in OTC_SESSION_RESULTS[-25:]: txt+=f"{'✅' if r['win'] else '❌'} {r['time']} {r['pair']} {r['dir']} ${r['amt']} L{r['level']} {r['conf']}% {r['pnl']:+.2f}\n"
        bot.send_message(m.chat.id,txt,parse_mode="Markdown"); return
    if m.text.startswith('/mode'):
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); pnl_today, total_today, _, _ = ai_daily_stats(); locked, _, _ = ai_is_daily_locked(); sess_name, is_golden, sess_reason = get_session_info()
        bot.send_message(m.chat.id,f"📍 **MODE V20**\n⏰ {now.strftime('%A %H:%M WAT')} | {sess_name} - {sess_reason}\n💎 IQ {'✅' if IQ_CONNECTED else '❌'}\n💰 Today ${pnl_today:+.2f} | {'🔒 LOCKED' if locked else '✅ OPEN'}\n🔒 Pullback Lock: {'ON - Waiting ' + str(list(PENDING_RECOVERY.keys())) if PENDING_RECOVERY else 'OFF - Free'}",parse_mode="Markdown"); return
    if m.text.startswith('/balance'):
        try:
            if not IQ_CONNECTED: bot.send_message(m.chat.id,f"💰 IQ ❌ Not connected"); return
            demo=get_real_balance("PRACTICE"); real=get_real_balance("REAL"); bot.send_message(m.chat.id,f"💰 **BAL**\n🟢 DEMO ${demo:.2f}\n🔴 REAL ${real:.2f}")
        except Exception as e: bot.send_message(m.chat.id,f"Balance error {e}")
        return
    try: bal_demo = get_real_balance("PRACTICE") if IQ_CONNECTED else STATS.get("real_balance",0.0)
    except: bal_demo = 0.0
    mk=types.InlineKeyboardMarkup(row_width=1); mk.add(types.InlineKeyboardButton(f"📈 TRADE REAL - ${bal_demo:.2f}",callback_data="trade_real")); mk.add(types.InlineKeyboardButton("🧠 AI",callback_data="ai_report")); mk.add(types.InlineKeyboardButton("📅 TODAY",callback_data="today_report")); mk.add(types.InlineKeyboardButton("📊 STATS",callback_data="stats"),types.InlineKeyboardButton("⚙️ SETTINGS",callback_data="settings"))
    txt=f"🤖 **Z-BOT V20 LOCK**\n\n💎 IQ {'✅' if IQ_CONNECTED else '❌'} | 💰 ${bal_demo:.2f}\n🏆 W:{STATS['wins']} L:{STATS['loss']} | 🔥 {STATS['streak']}\n📍 {get_mode_text()}"
    bot.send_message(m.chat.id,txt,reply_markup=mk,parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    global LAST_SIGNAL_TIME
    if not is_allowed(c.from_user.id): bot.answer_callback_query(c.id,"❌ Private"); return
    data=c.data; cid=c.message.chat.id
    if data=="today_report":
        pnl, total, wins, losses = ai_daily_stats(); locked, _, _ = ai_is_daily_locked(); bot.send_message(cid, f"📅 **TODAY**\nPnL ${pnl:+.2f} | W:{wins} L:{losses}", parse_mode="Markdown"); return
    if data=="ai_report":
        total, wins, best_pairs, best_hours, high_wr, low_wr, weights = ai_get_insight(); losses = total - wins; wr = (wins/total*100) if total else 0; pnl_today, _, _, _ = ai_daily_stats(); locked, _, _ = ai_is_daily_locked()
        txt = f"🧠 **AI**\nTotal {total} | W:{wins} L:{losses} | {wr:.1f}%\nHigh {high_wr} | Low {low_wr}\nToday ${pnl_today:+.2f}"
        bot.send_message(cid, txt, parse_mode="Markdown"); return
    if data.startswith("manual_win_") or data.startswith("manual_loss_"):
        try: bot.answer_callback_query(c.id, "Recorded ✅")
        except: pass
        is_win = data.startswith("manual_win_"); parts = data.split("_")
        try: pair = parts[2]; direction = parts[3]; conf = float(parts[4]); amt = float(parts[5]); level = int(parts[6]); p_int = int(parts[7]); payout = p_int / 100.0
        except: bot.send_message(cid, "❌ Could not read"); return
        tz = pytz.timezone("Africa/Lagos"); now_str = datetime.now(tz).strftime('%H:%M:%S'); saved = PENDING_MANUAL.get(pair, {"rsi":0, "adx":0, "reason":"Manual"}); real_rsi = saved.get("rsi", 0); real_adx = saved.get("adx", 0); real_reason = saved.get("reason", "Manual")
        # V20: Clear waiting_result lock first - this unlocks main scanner after 5 min cooldown
        if pair in PENDING_RECOVERY:
            del PENDING_RECOVERY[pair]
            LAST_SIGNAL_TIME = time.time()
        if is_win:
            profit = round(amt * payout, 2); STATS['wins'] += 1; STATS['streak'] += 1; OTC_MARTI["loss_streak"] = 0
            OTC_SESSION_RESULTS.append({"pair":pair,"dir":direction,"conf":conf,"pnl":profit,"win":True,"amt":amt,"level":level,"time":now_str}); ai_save_trade(pair, direction, conf, real_rsi, real_adx, payout, real_reason, amt, level, True)
            mk = types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("📈 TRADE", callback_data="trade_real"), types.InlineKeyboardButton("📊 STATS", callback_data="stats"))
            bot.send_message(cid, f"✅ **WIN +${profit:.2f}**\n{PAIR_EMOJI.get(pair,pair)} {direction} | ${amt:.2f} L{level}\nW:{STATS['wins']} L:{STATS['loss']} | 🔥 {STATS['streak']}\nNext L1 ${OTC_MARTI['base']:.2f}\n⏳ Next signal in 5 min", reply_markup=mk, parse_mode="Markdown")
        else:
            STATS['loss'] += 1; STATS['streak'] = 0; OTC_SESSION_RESULTS.append({"pair":pair,"dir":direction,"conf":conf,"pnl":-amt,"win":False,"amt":amt,"level":level,"time":now_str}); ai_save_trade(pair, direction, conf, real_rsi, real_adx, payout, real_reason, amt, level, False)
            if OTC_MARTI["loss_streak"] >= 2:
                OTC_MARTI["loss_streak"] = 0; LAST_SIGNAL_TIME = time.time()
                mk = types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("📈 TRADE", callback_data="trade_real"), types.InlineKeyboardButton("📊 STATS", callback_data="stats"))
                bot.send_message(cid, f"❌ **LOSS -${amt:.2f}**\n{PAIR_EMOJI.get(pair,pair)} {direction} | ${amt:.2f} L{level}\n1-2-4 done. Reset L1 ${OTC_MARTI['base']:.2f}\n⏳ Next signal in 5 min", reply_markup=mk, parse_mode="Markdown")
            else:
                OTC_MARTI["loss_streak"] += 1; levels = OTC_MARTI["levels"]; next_mult = levels[OTC_MARTI["loss_streak"]]; next_amt = round(OTC_MARTI["base"] * next_mult, 2); next_level = OTC_MARTI["loss_streak"]+1; start_recovery_scan(pair, direction, next_level, next_amt, payout, conf)
                mk = types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("📈 TRADE", callback_data="trade_real"), types.InlineKeyboardButton("📊 STATS", callback_data="stats"))
                bot.send_message(cid, f"❌ **LOSS -${amt:.2f}**\n{PAIR_EMOJI.get(pair,pair)} {direction} | ${amt:.2f} L{level}\n⏳ **L{next_level} ${next_amt:.2f} - Waiting pullback**\nBot go send when pullback come. No enter now.\n🔒 Main scanner PAUSED till you finish L{next_level} or 15 min timeout.", reply_markup=mk, parse_mode="Markdown")
        return
    if data=="trade_real":
        locked, pnl_today, trades_today = ai_is_daily_locked()
        if locked: bot.send_message(cid, f"🔒 **LOCKED**\nPnL ${pnl_today:+.2f} - Rest till tomorrow."); return
        if PENDING_RECOVERY:
            _p = list(PENDING_RECOVERY.keys())[0]; _info = PENDING_RECOVERY[_p]; bot.send_message(cid, f"⏳ **WAIT - Finish L{_info['level']} First**\nPending: {PAIR_EMOJI.get(_p,_p)} L{_info['level']} ${_info['amt']:.2f}\nFinish am first (✅/❌) or wait 15 min timeout."); return
        mk=types.InlineKeyboardMarkup(row_width=1); mk.add(types.InlineKeyboardButton("🔍 SCAN ALL (22)",callback_data="scan_all_real"))
        for p in REAL_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}",callback_data=f"real_pair_{p}"))
        bot.send_message(cid,f"📈 **TRADE REAL V20**\n📍 {get_mode_text()} | Today ${pnl_today:+.2f}",reply_markup=mk,parse_mode="Markdown"); return
    if data=="scan_all_real":
        if PENDING_RECOVERY:
            _p = list(PENDING_RECOVERY.keys())[0]; _info = PENDING_RECOVERY[_p]; bot.send_message(cid, f"⏳ **WAIT - Finish L{_info['level']} First**\nPending: {PAIR_EMOJI.get(_p,_p)} L{_info['level']} ${_info['amt']:.2f}\nFinish that trade first, or wait 15 min timeout."); return
        bot.answer_callback_query(c.id,"Scanning..."); scan_msg=bot.send_message(cid,"🔍 **SCANNING 22 PAIRS...**"); results=[]; datas={}
        for pair in REAL_PAIRS:
            now_hour = datetime.now(pytz.timezone("Africa/Lagos")).hour; is_blocked, _ = ai_should_block(pair, now_hour)
            if is_blocked: results.append((pair,0,"-","Blocked","🚫",180)); continue
            d=analyze_sniper_v12(pair,sniper_mode=False)
            if not d: results.append((pair,0,"-","No data","🔴",180)); continue
            conf=d['conf']; dir_=d['dir']; reason=d['reason']; exp=d['expiry']; status="🟢" if conf>=88 else "🟡" if conf>=65 else "🔴"; results.append((pair,conf,dir_,reason,status,exp)); datas[pair]=d; time.sleep(0.3)
        results.sort(key=lambda x: x[1], reverse=True); txt="📊 **READINESS**\n"
        for pair,conf,dir_,reason,status,exp in results: txt+=f"{status} {PAIR_EMOJI.get(pair,pair)}: {conf:.0f}% {dir_} {get_expiry_text(exp)}\n"
        best = results[0] if results else None
        if best and best[1]>=65: txt+=f"\n💡 **BEST:** {PAIR_EMOJI.get(best[0],best[0])} {best[1]:.0f}%"
        mk=types.InlineKeyboardMarkup(row_width=2)
        if best and best[1]>=65: mk.add(types.InlineKeyboardButton(f"✅ TRADE {best[0]}",callback_data=f"real_pair_{best[0]}"))
        mk.add(types.InlineKeyboardButton("🔄 RE-SCAN",callback_data="scan_all_real")); bot.send_message(cid,txt,reply_markup=mk,parse_mode="Markdown")
        if best and best[1]>=65 and best[0] in datas:
            time.sleep(0.5); best_data=datas[best[0]]; tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=45); exp_txt=get_expiry_text(best_data['expiry']); dir_e="🟢 CALL ⬆️" if best_data['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]; amt_m, mult_m, lvl_m = get_manual_amt_and_level(); PENDING_MANUAL[best_data['pair']] = {"rsi": best_data.get('rsi',0), "adx": best_data.get('adx',0), "reason": best_data.get('reason',''), "conf": best_data.get('conf',0)}
            signal_txt=f"📡 **{PAIR_EMOJI.get(best_data['pair'],best_data['pair'])}**\n\n📊 {dir_e} | {best_data['conf']:.0f}%\n⏰ {entry.strftime('%H:%M:%S')} | ⏱️ {exp_txt} | 💰 L1 ${base:.2f}\nRSI {best_data['rsi']:.0f} | ADX {best_data['adx']:.0f}\nL2 $2 - Wait | L3 $4 - Wait"
            bot.send_message(cid,signal_txt,parse_mode="Markdown", reply_markup=manual_result_keyboard(best_data['pair'], best_data['dir'], best_data['conf'], amt_m, mult_m, best_data['payout']))
        return
    if data.startswith("real_pair_"):
        if PENDING_RECOVERY:
            _p = list(PENDING_RECOVERY.keys())[0]; _info = PENDING_RECOVERY[_p]; bot.send_message(cid, f"⏳ **WAIT - Finish L{_info['level']} First**\nPending: {PAIR_EMOJI.get(_p,_p)} L{_info['level']} ${_info['amt']:.2f}"); return
        pair=data.replace("real_pair_",""); now_hour = datetime.now(pytz.timezone("Africa/Lagos")).hour; is_blocked, block_reason = ai_should_block(pair, now_hour)
        if is_blocked: bot.send_message(cid, f"🚫 **BLOCKED {pair}**\n{block_reason}"); return
        news_blocked, news_reason = is_news_time(pair, 30, 30)
        if news_blocked: bot.send_message(cid, f"📰 **NEWS BLOCK**\n{news_reason}"); return
        bot.answer_callback_query(c.id,f"Scanning {pair}..."); scan_msg=bot.send_message(cid,f"🔍 **SCAN {PAIR_EMOJI.get(pair,pair)}**"); legit_live_scan(cid,scan_msg.message_id,pair); d=analyze_sniper_v12(pair,sniper_mode=False)
        if not d or d['conf'] < 65:
            mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🔄 RETRY",callback_data=f"real_pair_{pair}"),types.InlineKeyboardButton("📈 SCAN ALL",callback_data="scan_all_real")); bot.send_message(cid,f"⚠️ **No trade {pair}**\nConf {d['conf'] if d else 0}%",reply_markup=mk); return
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=45); exp_txt=get_expiry_text(d['expiry']); dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]; amt_m, mult_m, lvl_m = get_manual_amt_and_level(); PENDING_MANUAL[pair] = {"rsi": d.get('rsi',0), "adx": d.get('adx',0), "reason": d.get('reason',''), "conf": d.get('conf',0)}
        signal_txt=f"📡 **{PAIR_EMOJI.get(pair,pair)}**\n\n📊 {dir_e} | {d['conf']:.0f}%\n⏰ {entry.strftime('%H:%M:%S')} | ⏱️ {exp_txt} | 💰 L1 ${base:.2f}\nRSI {d['rsi']:.0f} | ADX {d['adx']:.0f}\nL2 $2 - Wait | L3 $4 - Wait"
        mk=manual_result_keyboard(pair, d['dir'], d['conf'], amt_m, mult_m, d['payout']); mk.add(types.InlineKeyboardButton("🔁 SAME",callback_data=f"real_pair_{pair}"),types.InlineKeyboardButton("📈 SCAN ALL",callback_data="scan_all_real")); bot.send_message(cid,signal_txt,reply_markup=mk,parse_mode="Markdown"); return
    if data=="trade" or data=="scan_all_otc" or data=="auto_setup" or data.startswith("auto_pair_") or data.startswith("auto_bal_") or data.startswith("auto_amt_") or data.startswith("pair_"):
        bot.answer_callback_query(c.id,"OTC Disabled"); bot.send_message(cid,"⛔ **OTC DISABLED**\nUse TRADE REAL."); return
    if data=="stop_auto":
        if cid in AUTO_STATE: AUTO_STATE[cid]['running']=False; bot.send_message(cid,"🛑 Stopping..."); return
    if data=="stats":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0; bal=get_real_balance("PRACTICE"); mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("💹 NEW TRADE",callback_data="trade"),types.InlineKeyboardButton("🤖 AUTO",callback_data="auto_setup")); bot.send_message(cid,f"📊 **STATS V20**\nW:{STATS['wins']} L:{STATS['loss']} | {wr:.1f}% | 🔥 {STATS['streak']} | 💰 ${bal:.2f}",reply_markup=mk,parse_mode="Markdown")
    if data=="settings":
        bot.send_message(cid,f"⚙️ **SETTINGS V20**\n⏱️ Auto Expiry: 95%+=2M, 92%+=3M, 88%+=5M\n🔁 Recovery: Wait pullback 15 min\n🔒 V20 LOCK: Main paused till pullback finish\n🔒 Max Loss -${DAILY_MAX_LOSS:.0f} | Max {DAILY_MAX_TRADES}\n📰 News ON | ⏳ Cooldown 5 min\n🔙 /backtest EURUSD")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id,{}).get("step")=="await_amt")
def handle_custom_amt(m):
    cid=m.chat.id; st=user_states.get(cid,{})
    if not is_allowed(m.from_user.id): return
    try:
        amt=float(m.text.strip()); pair=st.get("pair"); bal=st.get("bal"); expiry=st.get("expiry",120)
        if not pair: return
        bot.send_message(cid,f"✅ Custom ${amt}..."); d=analyze_sniper_v12(pair,sniper_mode=False)
        if not d: return
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal,expiry)
        if not ok: bot.send_message(cid,"❌ Failed"); return
        bot.send_message(cid,f"✅ Placed {oid} Waiting {exp}s..."); time.sleep(exp+6)
        with IQ_LOCK: logging.disable(logging.CRITICAL); pnl=iq.check_win_v4(oid)
        bal_now=get_real_balance(bal)
        if pnl>0: STATS['wins']+=1; STATS['streak']+=1; bot.send_message(cid,f"✅ WIN +${pnl:.2f} Bal ${bal_now:.2f}")
        else: STATS['loss']+=1; STATS['streak']=0; bot.send_message(cid,f"❌ LOSS Bal ${bal_now:.2f}")
    except: bot.send_message(cid,"❌ Send number only")

threading.Thread(target=background_iq, daemon=True).start()
threading.Thread(target=real_signal_scanner,daemon=True).start()
threading.Thread(target=recovery_scanner,daemon=True).start()
threading.Thread(target=daily_8pm_report,daemon=True).start()
threading.Thread(target=nightly_backup_to_telegram,daemon=True).start()

if __name__ == "__main__":
    try:
        url=os.getenv("RENDER_EXTERNAL_URL")
        if url and BOT_TOKEN: requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={url}/{BOT_TOKEN}", timeout=5); print(f"Webhook set {url}")
    except: pass
    port=int(os.getenv("PORT",10000)); print(f"Starting V20 LOCK on {port}"); app.run(host="0.0.0.0", port=port, threaded=True)
