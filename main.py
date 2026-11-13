import os, time, threading, warnings, logging, json
from datetime import datetime, timedelta, timezone
from flask import Flask, request
import telebot
from telebot import types
import pandas as pd, requests, pytz
import xml.etree.ElementTree as ET
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt, io
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
REAL_PAIRS = ["EURUSD","GBPUSD","EURGBP","AUDUSD","USDCAD","USDCHF","EURAUD","EURCHF","NZDUSD","GBPAUD","EURCAD","AUDCAD","GBPCAD","AUDNZD","NZDCHF","AUDCHF","CADCHF","EURNZD","GBPNZD"]
OTC_PAIRS = ["EURUSD-OTC","GBPUSD-OTC","AUDUSD-OTC","USDCAD-OTC","EURGBP-OTC","EURAUD-OTC","GBPAUD-OTC","NZDUSD-OTC","GBPCHF-OTC","EURCHF-OTC","USDCHF-OTC","AUDCAD-OTC","EURCAD-OTC"]
PAIR_EMOJI = {"EURUSD":"🇪🇺 EUR/USD REAL","GBPUSD":"🇬🇧 GBP/USD REAL","EURGBP":"🇪🇺 EUR/GBP REAL","AUDUSD":"🇦🇺 AUD/USD REAL","USDCAD":"🇺🇸 USD/CAD REAL","USDCHF":"🇺🇸 USD/CHF REAL","EURAUD":"🇪🇺 EUR/AUD REAL","EURCHF":"🇪🇺 EUR/CHF REAL","NZDUSD":"🇳🇿 NZD/USD REAL","GBPAUD":"🇬🇧 GBP/AUD REAL","EURCAD":"🇪🇺 EUR/CAD REAL","AUDCAD":"🇦🇺 AUD/CAD REAL","GBPCAD":"🇬🇧 GBP/CAD REAL","AUDNZD":"🇦🇺 AUD/NZD REAL","NZDCHF":"🇳🇿 NZD/CHF REAL","AUDCHF":"🇦🇺 AUD/CHF REAL","CADCHF":"🇨🇦 CAD/CHF REAL","EURNZD":"🇪🇺 EUR/NZD REAL","GBPNZD":"🇬🇧 GBP/NZD REAL","EURUSD-OTC":"🇪🇺 EUR/USD OTC","GBPUSD-OTC":"🇬🇧 GBP/USD OTC","EURGBP-OTC":"🇪🇺 EUR/GBP OTC","AUDUSD-OTC":"🇦🇺 AUD/USD OTC","USDCHF-OTC":"🇺🇸 USD/CHF OTC","EURAUD-OTC":"🇪🇺 EUR/AUD OTC","GBPAUD-OTC":"🇬🇧 GBP/AUD OTC","NZDUSD-OTC":"🇳🇿 NZD/USD OTC","GBPCHF-OTC":"🇬🇧 GBP/CHF OTC","EURCHF-OTC":"🇪🇺 EUR/CHF OTC","USDCAD-OTC":"🇺🇸 USD/CAD OTC","AUDCAD-OTC":"🇦🇺 AUD/CAD OTC","EURCAD-OTC":"🇪🇺 EUR/CAD OTC"}
STATS = {"balance":0.0,"real_balance":0.0,"wins":0,"loss":0,"streak":0,"daily_trades":0,"daily_date":""}
user_states = {}; AUTO_STATE = {}; IQ_LOCK = threading.Lock()
IQ_CONNECTED=False; iq=None; PAYOUT_CACHE={}; PAYOUT_TIME=0
OTC_SESSION_RESULTS = []
OTC_MARTI = {"loss_streak":0, "base":1.0, "bal":"PRACTICE", "levels":[1,2,4,8]}
PULLBACK_STATE = {}
ACTIVE_SIGNAL = {"active": False, "pair": None, "dir": None, "conf":0, "rsi":0, "adx":0, "started": 0, "day": ""}
LAST_GLOBAL_SIGNAL = {"time": 0}
GLOBAL_COOLDOWN = 360; SKIP_COOLDOWN = 120; DAILY_SUMMARY_SENT = ""
MARKET_GOOD_SENT = {"date": "", "last_alert": 0}; MORNING_GREET_SENT = ""; NEWS_CACHE = {"data": [], "time": 0}
# ===== V21 CONFIG =====
SR_TIMEFRAMES = [900, 1800, 3600]
SR_ZONE_ATR = 0.8
def generate_chart(pair, df, support, resistance, entry_price, direction, rsi_val):
    try:
        plt.style.use('dark_background')
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), gridspec_kw={'height_ratios': [3, 1]}, sharex=True)
        fig.patch.set_facecolor('#0f0f0f'); ax1.set_facecolor('#0f0f0f'); ax2.set_facecolor('#0f0f0f')
        closes = df['close'].tail(60).reset_index(drop=True); opens = df['open'].tail(60).reset_index(drop=True); highs = df['max'].tail(60).reset_index(drop=True); lows = df['min'].tail(60).reset_index(drop=True)
        for i in range(len(closes)):
            color = '#00ff88' if closes[i] >= opens[i] else '#ff4444'
            ax1.plot([i, i], [lows[i], highs[i]], color=color, linewidth=1); ax1.plot([i, i], [opens[i], closes[i]], color=color, linewidth=4)
        ema9 = closes.ewm(9).mean(); ema21 = closes.ewm(21).mean()
        ax1.plot(ema9, color='#00aaff', linewidth=1.2, label='EMA 9'); ax1.plot(ema21, color='#ffaa00', linewidth=1.2, label='EMA 21')
        ax1.axhline(y=resistance, color='#ff4444', linestyle='--', linewidth=1.5, label=f'Resistance {resistance:.5f}')
        ax1.axhline(y=support, color='#00ff88', linestyle='--', linewidth=1.5, label=f'Support {support:.5f}')
        ecolor = '#00ff88' if direction == "CALL" else '#ff4444'
        ax1.axhline(y=entry_price, color=ecolor, linestyle='-', linewidth=2, label=f'ENTRY {entry_price:.5f} {direction}')
        ax1.fill_between(range(len(closes)), support, resistance, alpha=0.05, color='white')
        ax1.set_title(f'{pair} - {direction} - RSI {rsi_val:.1f} | Sup {support:.5f} Res {resistance:.5f}', color='white', fontsize=12, fontweight='bold')
        ax1.legend(loc='upper left', fontsize=8, facecolor='#1a1a1a'); ax1.tick_params(colors='white'); ax1.grid(True, alpha=0.15)
        rsi_series = calc_rsi(df['close'], 7).tail(60).reset_index(drop=True)
        ax2.plot(rsi_series, color='#ffaa00', linewidth=1.5); ax2.axhline(y=70, color='#ff4444', linestyle='--', linewidth=1); ax2.axhline(y=30, color='#00ff88', linestyle='--', linewidth=1); ax2.axhline(y=50, color='gray', linestyle=':', linewidth=1)
        ax2.fill_between(range(len(rsi_series)), 70, 100, alpha=0.15, color='red'); ax2.fill_between(range(len(rsi_series)), 0, 30, alpha=0.15, color='green')
        ax2.set_ylim(0, 100); ax2.set_ylabel('RSI 7', color='white'); ax2.tick_params(colors='white'); ax2.grid(True, alpha=0.15)
        plt.tight_layout(); buf = io.BytesIO(); plt.savefig(buf, format='png', dpi=130, facecolor='#0f0f0f'); plt.close(fig); buf.seek(0); return buf
    except Exception as e: print(f"Chart err {e}"); return None
def send_signal_with_chart(cid, pair, d, mk=None):
    try:
        df = get_candles(pair)
        support, resistance, dist_sup, dist_res = get_support_resistance(df) if df is not None else (d['price'], d['price'], 0, 0)
        if 'sr_sup' in d and d['sr_sup']: support = d['sr_sup']
        if 'sr_res' in d and d['sr_res']: resistance = d['sr_res']
        if df is None:
            txt = build_brief_text(pair, d, dist_sup, dist_res); bot.send_message(cid, txt, parse_mode="Markdown", reply_markup=mk); return
        chart_buf = generate_chart(pair, df, support, resistance, d['price'], d['dir'], d['rsi']); txt = build_brief_text(pair, d, dist_sup, dist_res)
        if chart_buf: bot.send_photo(cid, chart_buf, caption=txt, parse_mode="Markdown", reply_markup=mk)
        else: bot.send_message(cid, txt, parse_mode="Markdown", reply_markup=mk)
    except Exception as e:
        print(f"send chart err {e}"); txt = build_brief_text(pair, d, 0, 0); bot.send_message(cid, txt, parse_mode="Markdown", reply_markup=mk)
def build_brief_text(pair, d, dist_sup, dist_res):
    dir_e = "🟢 CALL ⬆️" if d['dir'] == "CALL" else "🔴 PUT ⬇️"; ti = d.get('trend_info', {}); trend_txt = ti.get('trend_type', '➡️ NORMAL TREND'); expiry_min = ti.get('expiry', 120)//60; base = OTC_MARTI["base"]
    rsi_extra = ""
    if 'rsi_mtf' in d:
        m = d['rsi_mtf']; rsi_extra = f"\n**RSI MTF:** 15m {m.get('15m',0):.0f} | 30m {m.get('30m',0):.0f} | 60m {m.get('60m',0):.0f}"
    sr_tfs = d.get('sr_tfs', ''); sr_txt = f"**S/R:** {dist_sup:.1f} ATR to Sup | {dist_res:.1f} ATR to Res"
    if sr_tfs: sr_txt += f" | TFs {sr_tfs}"
    return f"""📡 **REAL SIGNAL V21**
💱 {PAIR_EMOJI.get(pair,pair)}
📊 {dir_e} | 🎯 {d['conf']:.0f}%

**Entry:** {d['price']:.5f}
**RSI:** {d['rsi']:.1f}{rsi_extra}
**Trend:** {trend_txt}
{sr_txt}

💸 {int(d['payout']*100)}% | ⏱️ {expiry_min} Min | 📅 {STATS['daily_trades']}/30

**Entry:** ${base:.2f} | Marti: ${base*2:.2f} / ${base*4:.2f} / ${base*8:.2f}
"""
def get_lagos_day(): return datetime.now(pytz.timezone("Africa/Lagos")).strftime("%Y-%m-%d")
def check_and_reset_new_day():
    today = get_lagos_day()
    if STATS["daily_date"] != today:
        STATS["daily_date"] = today; STATS["daily_trades"] = 0; ACTIVE_SIGNAL.update({"active": False, "pair": None, "dir": None, "conf": 0, "rsi": 0, "adx": 0, "started": 0, "day": ""}); PULLBACK_STATE.clear(); OTC_MARTI["loss_streak"] = 0; return True
    if ACTIVE_SIGNAL["active"] and ACTIVE_SIGNAL.get("day") and ACTIVE_SIGNAL["day"] != today:
        ACTIVE_SIGNAL.update({"active": False, "pair": None, "dir": None, "conf": 0, "rsi": 0, "adx": 0, "started": 0, "day": ""}); PULLBACK_STATE.clear(); OTC_MARTI["loss_streak"] = 0; return True
    return False
def get_greeting():
    tz = pytz.timezone("Africa/Lagos"); hour = datetime.now(tz).hour
    if 5 <= hour < 12: return "🌅 GOOD MORNING TRAILBLAZER ☀️"
    elif 12 <= hour < 17: return "☀️ GOOD AFTERNOON TRAILBLAZER 🔥"
    elif 17 <= hour < 21: return "🌇 GOOD EVENING TRAILBLAZER 🌙"
    else: return "🌙 GOOD NIGHT TRAILBLAZER 💤"
def get_greeting_msg():
    tz = pytz.timezone("Africa/Lagos"); hour = datetime.now(tz).hour
    if 5 <= hour < 12: return "🌅 Rise and shine! New day, new money to stack 💰"
    elif 12 <= hour < 17: return "☀️ Afternoon grind time! Market is hot 🔥"
    elif 17 <= hour < 21: return "🌇 Evening session! Last chance to stack 🌙"
    else: return "🌙 Market is sleeping. Rest, tomorrow we stack again 💤"
def get_session_boost(pair):
    tz = pytz.timezone("Africa/Lagos"); now = datetime.now(tz); hour = now.hour + now.minute / 60
    if 8 <= hour < 11:
        if pair[:3] in ["EUR","GBP","CHF"] or pair[3:6] in ["EUR","GBP","CHF"]: return 8, "🇬🇧 LONDON OPEN"
        return 6, "🇬🇧 LONDON OPEN"
    elif 14.5 <= hour < 17: return 10, "🇬🇧🇺🇸 LONDON + NY OVERLAP 🔥"
    elif 14 <= hour < 14.5: return 4, "🇺🇸 NY PRE-OPEN"
    elif 12 <= hour < 13.5: return -10, "😴 LUNCH DEAD ZONE"
    elif 18 <= hour < 20: return -5, "🌙 EVENING SLOW"
    elif 11 <= hour < 12: return 3, "🇬🇧 LONDON MORNING"
    elif 17 <= hour < 18: return 2, "🇺🇸 NY AFTERNOON"
    else: return 0, "🌍 NORMAL"
def get_upcoming_news():
    try:
        if time.time() - NEWS_CACHE["time"] < 300: return NEWS_CACHE["data"]
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"; r = requests.get(url, timeout=10)
        if r.status_code != 200: return []
        root = ET.fromstring(r.content); now = datetime.now(pytz.timezone("UTC")).replace(tzinfo=None); upcoming = []
        for event in root.findall("event"):
            try:
                title = event.find("title").text; country = event.find("country").text; impact = event.find("impact").text; date_str = event.find("date").text; time_str = event.find("time").text
                if impact != "High": continue
                if country not in ["USD","EUR","GBP","AUD","CAD","NZD","CHF"]: continue
                dt = datetime.strptime(f"{date_str} {time_str}", "%m-%d-%Y %I:%M%p"); dt_utc = dt + timedelta(hours=5); diff_min = (dt_utc - now).total_seconds() / 60
                if -15 <= diff_min <= 120: upcoming.append({"title":title,"country":country,"time_utc":dt_utc,"in_min":int(diff_min),"impact":impact})
            except: continue
        NEWS_CACHE["data"] = upcoming; NEWS_CACHE["time"] = time.time(); return upcoming
    except Exception as e: print(f"News err {e}"); return []
def is_news_blocking_pair(pair, minutes=30):
    news = get_upcoming_news()
    if not news: return None
    base = pair[:3]; quote = pair[3:6] if len(pair) >= 6 else ""
    for n in news:
        if n["country"] in [base, quote] and n["in_min"] <= minutes and n["in_min"] >= -15: return n
    return None
def format_news_alert(news_list):
    if not news_list: return ""
    txt = "📰 **UPCOMING HIGH IMPACT NEWS** 📰\n\n"
    for n in news_list:
        flag = {"USD":"🇺🇸","EUR":"🇪🇺","GBP":"🇬🇧","AUD":"🇦🇺","CAD":"🇨🇦","NZD":"🇳🇿","CHF":"🇨🇭"}.get(n["country"], "🌍")
        if n["in_min"] < 0: when = f"Started {-n['in_min']} min ago"
        elif n["in_min"] == 0: when = "⚡ RIGHT NOW!"
        else: when = f"In {n['in_min']} min"
        txt += f"🔴 {flag} {n['country']} - {n['title']}\n⏰ {when}\n\n"
    return txt
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
    if pair not in PAIR_BRAIN: PAIR_BRAIN[pair] = {"wins":0,"loss":0,"history":[],"blocked_until":0,"score_boost":0,"hour_stats":{},"rsi_wins":[],"rsi_loss":[],"best_hour":None,"worst_hour":None,"best_rsi_range":None}
    s = PAIR_BRAIN[pair]
    if "hour_stats" not in s: s["hour_stats"] = {}
    if "rsi_wins" not in s: s["rsi_wins"] = []
    if "rsi_loss" not in s: s["rsi_loss"] = []
    return s
def get_pair_winrate(pair):
    s = get_pair_stats(pair); total = s["wins"] + s["loss"]
    if total < 3: return None
    return s["wins"] / total * 100
def is_pair_blocked(pair):
    s = get_pair_stats(pair); return time.time() < s["blocked_until"]
def record_brain(pair, won, conf, rsi, adx):
    s = get_pair_stats(pair); tz = pytz.timezone("Africa/Lagos"); hour = str(datetime.now(tz).hour)
    if won: s["wins"] += 1
    else: s["loss"] += 1
    if hour not in s["hour_stats"]: s["hour_stats"][hour] = {"wins":0,"loss":0}
    if won: s["hour_stats"][hour]["wins"] += 1
    else: s["hour_stats"][hour]["loss"] += 1
    if won: s["rsi_wins"].append(rsi)
    else: s["rsi_loss"].append(rsi)
    s["rsi_wins"] = s["rsi_wins"][-30:]; s["rsi_loss"] = s["rsi_loss"][-30:]
    s["history"].append({"win":won,"conf":conf,"rsi":rsi,"adx":adx,"time":time.time(),"hour":hour}); s["history"] = s["history"][-30:]
    best_h = None; best_wr = 0; worst_h = None; worst_wr = 100
    for h, st in s["hour_stats"].items():
        total = st["wins"] + st["loss"]
        if total >= 3:
            wr = st["wins"]/total*100
            if wr > best_wr: best_wr = wr; best_h = h
            if wr < worst_wr: worst_wr = wr; worst_h = h
    s["best_hour"] = best_h; s["worst_hour"] = worst_h
    if len(s["rsi_wins"]) >= 5:
        avg_win_rsi = sum(s["rsi_wins"]) / len(s["rsi_wins"]); s["best_rsi_range"] = [avg_win_rsi - 7, avg_win_rsi + 7]
    wr = get_pair_winrate(pair); total = s["wins"] + s["loss"]
    if total >= 5:
        if wr < 40: s["blocked_until"] = time.time() + 7200; s["score_boost"] = -15
        elif wr < 50: s["score_boost"] = -8
        elif wr >= 65: s["score_boost"] = +8; s["blocked_until"] = 0
        elif wr >= 55: s["score_boost"] = +3
        else: s["score_boost"] = 0
    save_brain()
def get_hour_boost(pair):
    s = get_pair_stats(pair); tz = pytz.timezone("Africa/Lagos"); hour = str(datetime.now(tz).hour)
    if hour not in s.get("hour_stats", {}): return 0, ""
    st = s["hour_stats"][hour]; total = st["wins"] + st["loss"]
    if total < 3: return 0, ""
    wr = st["wins"]/total*100
    if wr >= 70: return 8, f"🧠 Best Hour {hour}:00 {wr:.0f}%"
    elif wr >= 60: return 4, f"🧠 Good Hour {hour}:00 {wr:.0f}%"
    elif wr < 40: return -10, f"🧠 Bad Hour {hour}:00 {wr:.0f}%"
    elif wr < 50: return -5, f"🧠 Weak Hour {hour}:00 {wr:.0f}%"
    return 0, ""
def get_pair_rsi_boost(pair, current_rsi, is_call):
    s = get_pair_stats(pair); rng = s.get("best_rsi_range")
    if not rng or len(s.get("rsi_wins", [])) < 5: return 0, ""
    low, high = rng
    if low <= current_rsi <= high: return 6, f"🧠 Pair RSI Sweet Spot {current_rsi:.0f} in [{low:.0f}-{high:.0f}]"
    dist = min(abs(current_rsi - low), abs(current_rsi - high))
    if dist > 15: return -6, f"🧠 Pair RSI Off {current_rsi:.0f} vs Sweet [{low:.0f}-{high:.0f}]"
    return 0, ""
load_brain()
def is_signal_active(): check_and_reset_new_day(); return ACTIVE_SIGNAL["active"]
def start_signal(pair, dir_, conf=0, rsi=0, adx=0): check_and_reset_new_day(); ACTIVE_SIGNAL.update({"active":True,"pair":pair,"dir":dir_,"conf":conf,"rsi":rsi,"adx":adx,"started":time.time(),"day":get_lagos_day()})
def clear_signal(): ACTIVE_SIGNAL.update({"active":False,"pair":None,"dir":None,"conf":0,"rsi":0,"adx":0,"started":0,"day":""})
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
def can_trade_today(): check_and_reset_new_day(); return STATS["daily_trades"] < 30
def count_trade(): STATS["daily_trades"] += 1
@app.route("/")
def home(): return f"V21 S/R 15-30-60 + RSI MTF RUNNING IQ:{IQ_CONNECTED} {datetime.now(pytz.timezone('Africa/Lagos')).strftime('%H:%M:%S')}"
@app.route(f"/{BOT_TOKEN}",methods=['POST'])
def wh(): bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode("utf-8"))]); return "ok"
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
                    if "@" in pc: up, hp = pc.split("@"); pu, pp = up.split(":"); ph, pt = hp.split(":"); iq.set_proxy(proxy_type="http", host=ph, port=int(pt), user=pu, password=pp)
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
                if "@" in pc: up, hp = pc.split("@"); pu, pp = up.split(":"); ph, pt = hp.split(":"); iq.set_proxy(proxy_type="http", host=ph, port=int(pt), user=pu, password=pp)
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
def get_candles_tf(pair, tf_seconds, count=80):
    try:
        if not IQ_CONNECTED: return None
        logging.disable(logging.CRITICAL); c = iq.get_candles(pair, tf_seconds, count, time.time())
        if c and len(c) > 30: return pd.DataFrame(sorted(c, key=lambda x: x['from']))
    except Exception as e: print(f"TF {tf_seconds} err {e}")
    return None
def calc_rsi(closes, period=7):
    delta=closes.diff(); gain=delta.where(delta>0,0); loss=-delta.where(delta<0,0); avg_gain=gain.ewm(alpha=1/period, adjust=False).mean(); avg_loss=loss.ewm(alpha=1/period, adjust=False).mean(); rs=avg_gain/avg_loss; return 100-(100/(1+rs))
def calc_atr(df, period=14):
    try:
        high=df['max']; low=df['min']; close=df['close']; tr1=high-low; tr2=(high-close.shift()).abs(); tr3=(low-close.shift()).abs(); tr=pd.concat([tr1,tr2,tr3],axis=1).max(axis=1); return tr.rolling(period).mean().iloc[-1]
    except: return 0.0005
def legit_live_scan(cid, mid, pair):
    steps = [(0,"🚀 V21 Init...",0.15),(20,f"🔌 Checking {pair}...",0.2),(40,"📊 ADX + ATR + Brain + News + Session...",0.25),(60,"📈 EMA + MACD + 5M Trend + S/R 15/30/60...",0.2),(80,"💹 RSI MTF 15/30/60 + Rejection...",0.2),(100,"🔒 SNIPER LOCKED!",0.3)]
    last_pct=-1
    for pct, text, delay in steps:
        if pct==last_pct: time.sleep(delay); continue
        last_pct=pct; filled=int(pct//5); bar="█"*filled+"░"*(20-filled); color="🟥" if pct<40 else "🟨" if pct<80 else "🟩" if pct<100 else "💎"
        txt=f"""{color} **Z-BOT V21** {color}\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n💎 IQ: {'✅' if IQ_CONNECTED else '❌'}\n\n{bar} {pct}%\n\n🔍 {text}\n⏳ V21"""
        try: bot.edit_message_text(txt,cid,mid,parse_mode="Markdown")
        except: pass
        time.sleep(delay)
def calc_adx_v12(df, period=14):
    try:
        high=df['max']; low=df['min']; close=df['close']; tr1=high-low; tr2=(high-close.shift()).abs(); tr3=(low-close.shift()).abs(); tr=pd.concat([tr1,tr2,tr3],axis=1).max(axis=1); atr=tr.rolling(period).mean(); up=high-high.shift(); down=low.shift()-low; plus_dm=((up>down)&(up>0))*up; minus_dm=((down>up)&(down>0))*down; plus_di=100*(plus_dm.rolling(period).mean()/atr); minus_di=100*(minus_dm.rolling(period).mean()/atr); dx=100*((plus_di-minus_di).abs()/(plus_di+minus_di)); adx=dx.rolling(period).mean().iloc[-1]; return float(adx), float(plus_di.iloc[-1]), float(minus_di.iloc[-1])
    except: return 0, 0, 0
# ===== V21 S/R 15/30/60 0.8 ATR =====
def find_sr_levels_for_df(df):
    levels = []
    if df is None or len(df) < 30: return levels
    highs = df['max'].values; lows = df['min'].values
    for i in range(2, len(df)-2):
        if highs[i] == max(highs[i-2:i+3]): levels.append({"price": float(highs[i]), "type": "RES"})
        if lows[i] == min(lows[i-2:i+3]): levels.append({"price": float(lows[i]), "type": "SUP"})
    merged = []
    for lvl in levels:
        found = False
        for m in merged:
            if m["type"] == lvl["type"] and abs(m["price"] - lvl["price"]) < 0.0004: m["touches"] += 1; found = True; break
        if not found: merged.append({"price": lvl["price"], "type": lvl["type"], "touches": 1})
    return [m for m in merged if m["touches"] >= 2]
def get_support_resistance_multi(pair, current_price, atr_val):
    if not atr_val or atr_val == 0: atr_val = 0.0005
    zone = SR_ZONE_ATR * atr_val; sup_candidates = []; res_candidates = []; tf_map = {900: "15m", 1800: "30m", 3600: "60m"}
    for tf_sec in SR_TIMEFRAMES:
        df_tf = get_candles_tf(pair, tf_sec, 80)
        if df_tf is None: continue
        levels = find_sr_levels_for_df(df_tf); tf_name = tf_map[tf_sec]
        for lvl in levels:
            if lvl["type"] == "SUP": sup_candidates.append((lvl["price"], tf_name))
            else: res_candidates.append((lvl["price"], tf_name))
    nearest_sup = None; sup_tfs = []
    for price, tf_name in sup_candidates:
        if abs(current_price - price) <= zone:
            if nearest_sup is None or abs(current_price - price) < abs(current_price - nearest_sup): nearest_sup = price
            if tf_name not in sup_tfs: sup_tfs.append(tf_name)
    nearest_res = None; res_tfs = []
    for price, tf_name in res_candidates:
        if abs(current_price - price) <= zone:
            if nearest_res is None or abs(current_price - price) < abs(current_price - nearest_res): nearest_res = price
            if tf_name not in res_tfs: res_tfs.append(tf_name)
    disp_sup = nearest_sup; disp_res = nearest_res
    if disp_sup is None and sup_candidates: disp_sup = min(sup_candidates, key=lambda x: abs(x[0]-current_price))[0]
    if disp_res is None and res_candidates: disp_res = min(res_candidates, key=lambda x: abs(x[0]-current_price))[0]
    if disp_sup is None: disp_sup = current_price - atr_val*2
    if disp_res is None: disp_res = current_price + atr_val*2
    dist_sup = abs(current_price - disp_sup)/atr_val if atr_val else 99; dist_res = abs(disp_res - current_price)/atr_val if atr_val else 99
    if nearest_sup is None: dist_sup = 99
    if nearest_res is None: dist_res = 99
    return {"sup": nearest_sup, "res": nearest_res, "disp_sup": disp_sup, "disp_res": disp_res, "dist_sup": dist_sup, "dist_res": dist_res, "sup_tfs": sup_tfs, "res_tfs": res_tfs, "sup_confluence": len(sup_tfs), "res_confluence": len(res_tfs), "zone": zone}
def get_support_resistance(df, lookback=30):
    try:
        recent = df.tail(lookback); resistance = float(recent['max'].max()); support = float(recent['min'].min()); price = float(df['close'].iloc[-1]); atr = calc_atr(df, 14)
        if not atr or atr == 0: atr = 0.0005
        dist_to_res = abs(resistance - price) / atr; dist_to_sup = abs(price - support) / atr; return support, resistance, dist_to_sup, dist_to_res
    except: return 0, 999999, 999, 999
# ===== V21 RSI 15/30/60 + 1m =====
def get_rsi_multitimeframe(pair, df_1m):
    out = {}
    try:
        r7_1m = calc_rsi(df_1m['close'], 7); out["1m"] = {"rsi": float(r7_1m.iloc[-1]), "prev": float(r7_1m.iloc[-2])}
    except: pass
    tf_map = {900: "15m", 1800: "30m", 3600: "60m"}
    for tf_sec, tf_name in tf_map.items():
        df_tf = get_candles_tf(pair, tf_sec, 80)
        if df_tf is None: continue
        try: r = calc_rsi(df_tf['close'], 7); out[tf_name] = {"rsi": float(r.iloc[-1]), "prev": float(r.iloc[-2])}
        except: pass
    return out
def check_rsi_call_mtf(m):
    try:
        if "60m" not in m or "30m" not in m or "15m" not in m or "1m" not in m: return False, "Missing RSI TF"
        if not (40 <= m["60m"]["rsi"] <= 60): return False, f"60m RSI {m['60m']['rsi']:.0f} not 40-60"
        if not (35 <= m["30m"]["rsi"] <= 55): return False, f"30m RSI {m['30m']['rsi']:.0f} not 35-55"
        if m["30m"]["rsi"] <= m["30m"]["prev"]: return False, "30m RSI not turning UP"
        if not (35 <= m["15m"]["rsi"] <= 55): return False, f"15m RSI {m['15m']['rsi']:.0f} not 35-55"
        if m["15m"]["rsi"] <= m["15m"]["prev"]: return False, "15m RSI not turning UP"
        if not (40 <= m["1m"]["rsi"] <= 55): return False, f"1m RSI {m['1m']['rsi']:.0f} not 40-55"
        if m["1m"]["rsi"] <= m["1m"]["prev"]: return False, "1m RSI not turning UP"
        return True, "RSI CALL OK"
    except Exception as e: return False, f"RSI err {e}"
def check_rsi_put_mtf(m):
    try:
        if "60m" not in m or "30m" not in m or "15m" not in m or "1m" not in m: return False, "Missing RSI TF"
        if not (40 <= m["60m"]["rsi"] <= 60): return False, f"60m RSI {m['60m']['rsi']:.0f} not 40-60"
        if not (45 <= m["30m"]["rsi"] <= 65): return False, f"30m RSI {m['30m']['rsi']:.0f} not 45-65"
        if m["30m"]["rsi"] >= m["30m"]["prev"]: return False, "30m RSI not turning DOWN"
        if not (45 <= m["15m"]["rsi"] <= 65): return False, f"15m RSI {m['15m']['rsi']:.0f} not 45-65"
        if m["15m"]["rsi"] >= m["15m"]["prev"]: return False, "15m RSI not turning DOWN"
        if not (45 <= m["1m"]["rsi"] <= 60): return False, f"1m RSI {m['1m']['rsi']:.0f} not 45-60"
        if m["1m"]["rsi"] >= m["1m"]["prev"]: return False, "1m RSI not turning DOWN"
        return True, "RSI PUT OK"
    except Exception as e: return False, f"RSI err {e}"
def check_rejection_candle(df, direction):
    try:
        if len(df) < 3: return False
        last = df.iloc[-1]; o = float(last['open']); c = float(last['close']); h = float(last['max']); l = float(last['min']); body = abs(c - o)
        if body == 0: return False
        lower_wick = min(o, c) - l; upper_wick = h - max(o, c)
        if direction == "CALL": return lower_wick > body * 0.8 and c > o
        else: return upper_wick > body * 0.8 and c < o
    except: return False
def get_trend_and_expiry(df, df5, close, r7, r14, adx, macd_val, sig_val, mom1, mom3, stoch_val, c_now, upper, lower, is_green):
    trends = []; trend_score = 0; e9 = float(close.ewm(9).mean().iloc[-1]); e21 = float(close.ewm(21).mean().iloc[-1]); e50 = float(close.ewm(50).mean().iloc[-1])
    if e9 > e21 > e50: trends.append("📈 EMA Strong Uptrend"); trend_score += 2
    elif e9 < e21 < e50: trends.append("📉 EMA Strong Downtrend"); trend_score += 2
    elif e9 > e21: trends.append("↗️ EMA Weak Uptrend"); trend_score += 1
    elif e9 < e21: trends.append("↘️ EMA Weak Downtrend"); trend_score += 1
    else: trends.append("➡️ EMA Flat / Ranging")
    if df5 is not None:
        c5 = df5['close']; e9_5 = float(c5.ewm(9).mean().iloc[-1]); e21_5 = float(c5.ewm(21).mean().iloc[-1])
        if e9_5 > e21_5: trends.append("📈 5M Uptrend")
        else: trends.append("📉 5M Downtrend")
        if (is_green and e9_5 > e21_5) or (not is_green and e9_5 < e21_5): trends.append("✅ 1M + 5M AGREE"); trend_score += 3
        else: trends.append("⚠️ 1M vs 5M CONFLICT"); trend_score -= 2
    if adx >= 35: trends.append(f"💪 ADX Very Strong {adx:.0f}"); trend_score += 3
    elif adx >= 28: trends.append(f"🔥 ADX Strong {adx:.0f}"); trend_score += 2
    elif adx >= 25: trends.append(f"👍 ADX OK {adx:.0f}"); trend_score += 1
    else: trends.append(f"😴 ADX Weak {adx:.0f}")
    if macd_val > sig_val: trends.append("📈 MACD Bullish"); trend_score += 1
    else: trends.append("📉 MACD Bearish"); trend_score += 1
    if trend_score >= 7: expiry = 300; expiry_txt = "5 Min - STRONG TREND"; trend_type = "🔥 STRONG TREND"
    elif trend_score >= 5: expiry = 180; expiry_txt = "3 Min - GOOD TREND"; trend_type = "📈 GOOD TREND"
    elif trend_score >= 3: expiry = 120; expiry_txt = "2 Min - NORMAL TREND"; trend_type = "➡️ NORMAL TREND"
    elif trend_score >= 1: expiry = 60; expiry_txt = "1 Min - WEAK / RANGING"; trend_type = "😴 WEAK / RANGING"
    else: expiry = 60; expiry_txt = "1 Min - CONFLICT"; trend_type = "⚠️ CONFLICT TREND"
    return {"trends": trends, "trend_score": trend_score, "expiry": expiry, "expiry_txt": expiry_txt, "trend_type": trend_type}
def analyze_sniper_v12(pair, sniper_mode=False):
    df = get_candles(pair)
    if df is None: return None
    try:
        df5 = None
        try:
            logging.disable(logging.CRITICAL); c5 = iq.get_candles(pair, 300, 50, time.time())
            if c5 and len(c5) > 20: df5 = pd.DataFrame(sorted(c5, key=lambda x: x['from']))
        except: df5 = None
        close=df['close']; open_=df['open']; high=df['max']; low=df['min']; ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean(); ema50=close.ewm(50).mean(); rsi7=calc_rsi(close,7); rsi14=calc_rsi(close,14); atr=calc_atr(df,14); adx, pdi, mdi = calc_adx_v12(df); ema12=close.ewm(12).mean(); ema26=close.ewm(26).mean(); macd=ema12-ema26; signal=macd.ewm(9).mean(); macd_val=float(macd.iloc[-1]); sig_val=float(signal.iloc[-1]); sma20=close.rolling(20).mean(); std20=close.rolling(20).std(); upper=float((sma20+2*std20).iloc[-1]); lower=float((sma20-2*std20).iloc[-1]); low14=low.rolling(14).min(); high14=high.rolling(14).max(); stoch=100*(close-low14)/(high14-low14); stoch_val=float(stoch.iloc[-1]); c_now=float(close.iloc[-1]); o_now=float(open_.iloc[-1]); c_prev=float(close.iloc[-2]); o_prev=float(open_.iloc[-2]); h_now=float(high.iloc[-1]); l_now=float(low.iloc[-1]); e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1]); e50=float(ema50.iloc[-1]); r7=float(rsi7.iloc[-1]); r14=float(rsi14.iloc[-1]); mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100; mom3=(close.iloc[-1]-close.iloc[-4])/close.iloc[-4]*100; body=abs(c_now-o_now); upper_wick=h_now-max(c_now,o_now); lower_wick=min(c_now,o_now)-l_now; is_green=c_now>o_now; payout=get_payout(pair); sig="CALL" if is_green else "PUT"
        if is_pair_blocked(pair): return {"pair":pair,"dir":sig,"conf":40,"price":c_now,"rsi":r7,"reason":f"🧠 Brain Blocked","payout":payout,"expiry":120,"atr":atr,"rejected":True}
        news_block = is_news_blocking_pair(pair, minutes=30)
        if news_block: return {"pair":pair,"dir":sig,"conf":40,"price":c_now,"rsi":r7,"reason":f"📰 NEWS BLOCK","payout":payout,"expiry":120,"atr":atr,"rejected":True}
        if adx < 25: return {"pair":pair,"dir":sig,"conf":42,"price":c_now,"rsi":r7,"reason":"Choppy - ADX Low","payout":payout,"expiry":120,"atr":atr,"rejected":True}
        if body < atr*0.30: return {"pair":pair,"dir":sig,"conf":48,"price":c_now,"rsi":r7,"reason":"Doji","payout":payout,"expiry":120,"atr":atr,"rejected":True}
        if payout < 0.80: return {"pair":pair,"dir":sig,"conf":52,"price":c_now,"rsi":r7,"reason":f"Low Payout {int(payout*100)}%","payout":payout,"expiry":120,"atr":atr,"rejected":True}
        sr = get_support_resistance_multi(pair, c_now, atr)
        if sr["sup"] is None and sr["res"] is None: return {"pair":pair,"dir":sig,"conf":45,"price":c_now,"rsi":r7,"reason":f"No safe entry - Mid-range, no S/R within 0.8 ATR","payout":payout,"expiry":120,"atr":atr,"rejected":True}
        rsi_mtf = get_rsi_multitimeframe(pair, df); rsi_mtf_simple = {k: v["rsi"] for k,v in rsi_mtf.items()}
        on_support = sr["sup"] is not None; on_resistance = sr["res"] is not None
        if is_green:
            if not on_support: return {"pair":pair,"dir":sig,"conf":45,"price":c_now,"rsi":r7,"reason":f"CALL blocked - Not at Support","payout":payout,"expiry":120,"atr":atr,"rejected":True}
            if sr["sup_confluence"] < 2: return {"pair":pair,"dir":sig,"conf":45,"price":c_now,"rsi":r7,"reason":f"Weak Support - Only {sr['sup_tfs']} need 2+ TFs","payout":payout,"expiry":120,"atr":atr,"rejected":True}
            ok_rsi, msg_rsi = check_rsi_call_mtf(rsi_mtf)
            if not ok_rsi: return {"pair":pair,"dir":sig,"conf":48,"price":c_now,"rsi":r7,"reason":f"RSI MTF BLOCK CALL - {msg_rsi}","payout":payout,"expiry":120,"atr":atr,"rejected":True}
            if not check_rejection_candle(df, "CALL"): return {"pair":pair,"dir":sig,"conf":48,"price":c_now,"rsi":r7,"reason":"No rejection at Support","payout":payout,"expiry":120,"atr":atr,"rejected":True}
        else:
            if not on_resistance: return {"pair":pair,"dir":sig,"conf":45,"price":c_now,"rsi":r7,"reason":f"PUT blocked - Not at Resistance","payout":payout,"expiry":120,"atr":atr,"rejected":True}
            if sr["res_confluence"] < 2: return {"pair":pair,"dir":sig,"conf":45,"price":c_now,"rsi":r7,"reason":f"Weak Resistance - Only {sr['res_tfs']} need 2+ TFs","payout":payout,"expiry":120,"atr":atr,"rejected":True}
            ok_rsi, msg_rsi = check_rsi_put_mtf(rsi_mtf)
            if not ok_rsi: return {"pair":pair,"dir":sig,"conf":48,"price":c_now,"rsi":r7,"reason":f"RSI MTF BLOCK PUT - {msg_rsi}","payout":payout,"expiry":120,"atr":atr,"rejected":True}
            if not check_rejection_candle(df, "PUT"): return {"pair":pair,"dir":sig,"conf":48,"price":c_now,"rsi":r7,"reason":"No rejection at Resistance","payout":payout,"expiry":120,"atr":atr,"rejected":True}
        dist_sup = abs(c_now - sr["sup"])/atr if sr["sup"] else 99; dist_res = abs(sr["res"] - c_now)/atr if sr["res"] else 99
        prev_green = c_prev > o_prev
        if is_green and not prev_green: return {"pair":pair,"dir":sig,"conf":48,"price":c_now,"rsi":r7,"reason":"Prev RED - No confirm","payout":payout,"expiry":120,"atr":atr,"rejected":True}
        if not is_green and prev_green: return {"pair":pair,"dir":sig,"conf":48,"price":c_now,"rsi":r7,"reason":"Prev GREEN - No confirm","payout":payout,"expiry":120,"atr":atr,"rejected":True}
        if is_green and upper_wick > body * 1.5 and body > 0: return {"pair":pair,"dir":sig,"conf":48,"price":c_now,"rsi":r7,"reason":"Big upper wick","payout":payout,"expiry":120,"atr":atr,"rejected":True}
        if not is_green and lower_wick > body * 1.5 and body > 0: return {"pair":pair,"dir":sig,"conf":48,"price":c_now,"rsi":r7,"reason":"Big lower wick","payout":payout,"expiry":120,"atr":atr,"rejected":True}
        try:
            avg_body = float(abs(close - open_).tail(20).mean())
            if body < avg_body * 0.5: return {"pair":pair,"dir":sig,"conf":48,"price":c_now,"rsi":r7,"reason":"Low Volatility","payout":payout,"expiry":120,"atr":atr,"rejected":True}
        except: pass
        score=30; reasons=[]
        if df5 is not None:
            c5=df5['close']; e9_5=c5.ewm(9).mean(); e21_5=c5.ewm(21).mean(); trend_5m = 1 if float(e9_5.iloc[-1]) > float(e21_5.iloc[-1]) else -1
            if (is_green and trend_5m==-1) or (not is_green and trend_5m==1): return {"pair":pair,"dir":sig,"conf":45,"price":c_now,"rsi":r7,"reason":"Against 5M","payout":payout,"expiry":120,"atr":atr,"rejected":True}
            else: score+=12; reasons.append("5M Align")
        else: return {"pair":pair,"dir":sig,"conf":45,"price":c_now,"rsi":r7,"reason":"No 5M","payout":payout,"expiry":120,"atr":atr,"rejected":True}
        if is_green:
            if e9>e21>e50: score+=18; reasons.append("EMA Bull")
            elif e9>e21: score+=10
            else: score-=8
        else:
            if e9<e21<e50: score+=18; reasons.append("EMA Bear")
            elif e9<e21: score+=10
            else: score-=8
        if adx >= 28: score+=12; reasons.append(f"ADX {adx:.0f}")
        elif adx >= 22: score+=7
        if is_green and pdi > mdi: score+=8
        elif not is_green and mdi > pdi: score+=8
        else: score-=10
        if is_green:
            if 52 <= r7 <= 65 and 48 <= r14 <= 62: score+=15; reasons.append(f"RSI {r7:.0f}")
            elif r7 > 75 or r7 < 45: score-=12
            else: score+=6
        else:
            if 35 <= r7 <= 48 and 38 <= r14 <= 52: score+=15; reasons.append(f"RSI {r7:.0f}")
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
        bull_eng = c_now > o_prev and o_now < c_prev and is_green and c_prev < o_prev; bear_eng = c_now < o_prev and o_now > c_prev and not is_green and c_prev > o_prev; pin_bull = lower_wick > body*1.8 and lower_wick > upper_wick*1.5 and is_green; pin_bear = upper_wick > body*1.8 and upper_wick > lower_wick*1.5 and not is_green; has_pattern = False
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
        if not has_pattern and score < 88: return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":"No Pattern","payout":payout,"expiry":120,"atr":atr,"rejected":True}
        session_boost, session_name = get_session_boost(pair); score += session_boost
        if session_boost != 0: reasons.append(f"{session_name} {session_boost:+d}")
        if is_green and sr["sup_confluence"] == 3: score += 5; reasons.append(f"S/R 15/30/60 {sr['sup_tfs']}")
        elif is_green and sr["sup_confluence"] == 2: score += 3; reasons.append(f"S/R {sr['sup_tfs']}")
        if not is_green and sr["res_confluence"] == 3: score += 5; reasons.append(f"S/R 15/30/60 {sr['res_tfs']}")
        elif not is_green and sr["res_confluence"] == 2: score += 3; reasons.append(f"S/R {sr['res_tfs']}")
        reasons.append(f"RSI MTF 15m {rsi_mtf_simple.get('15m',0):.0f} 30m {rsi_mtf_simple.get('30m',0):.0f} 60m {rsi_mtf_simple.get('60m',0):.0f}")
        required_score = 93 if session_boost <= -5 else 88
        if sniper_mode and score < required_score: return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":f"{session_name} - Needs {required_score}%","payout":payout,"expiry":120,"atr":atr,"rejected":True}
        hour_boost, hour_txt = get_hour_boost(pair)
        if hour_boost != 0: score += hour_boost; reasons.append(f"{hour_txt} {hour_boost:+d}")
        rsi_boost, rsi_txt = get_pair_rsi_boost(pair, r7, is_green)
        if rsi_boost != 0: score += rsi_boost; reasons.append(f"{rsi_txt} {rsi_boost:+d}")
        brain = get_pair_stats(pair); boost = brain.get("score_boost", 0); score += boost
        if boost != 0: reasons.append(f"🧠 {boost:+d}")
        score = max(40, min(96, score)); reason = " + ".join(reasons) if reasons else "Weak PA"; reason += f" | S/R {dist_sup:.1f} / {dist_res:.1f}"
        if sniper_mode and score < 88: return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":reason,"payout":payout,"expiry":120,"atr":atr,"rejected":True}
        trend_info = get_trend_and_expiry(df, df5, close, r7, r14, adx, macd_val, sig_val, mom1, mom3, stoch_val, c_now, upper, lower, is_green); reason = reason + f" | {trend_info['trend_type']} | {trend_info['expiry_txt']}"; sr_tfs_txt = ",".join(sr["sup_tfs"]) if is_green else ",".join(sr["res_tfs"])
        return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":reason,"payout":payout,"expiry":trend_info['expiry'],"atr":atr,"rejected":False,"adx":adx,"trend_info":trend_info,"sr_sup":sr["disp_sup"],"sr_res":sr["disp_res"],"sr_tfs":sr_tfs_txt,"rsi_mtf":rsi_mtf_simple}
    except Exception as e: print(f"V21 err {pair} {e}"); return None
def check_pullback_entry(pair, original_dir):
    if is_news_blocking_pair(pair, minutes=30): return None
    df = get_candles(pair)
    if df is None: return None
    try:
        close = df['close']; ema9 = close.ewm(9).mean(); ema21 = close.ewm(21).mean(); rsi7 = calc_rsi(close, 7); rsi14 = calc_rsi(close, 14); r7 = float(rsi7.iloc[-1]); r7_prev = float(rsi7.iloc[-2]); r14 = float(rsi14.iloc[-1]); c_now = float(close.iloc[-1]); e9 = float(ema9.iloc[-1]); e21 = float(ema21.iloc[-1]); payout = get_payout(pair); near_ema = abs(c_now - e9) / c_now * 100 < 0.05 or abs(c_now - e21) / c_now * 100 < 0.05
        if not near_ema or payout < 0.80: return None
        if original_dir == "CALL":
            if 40 <= r7 <= 55 and 42 <= r14 <= 58 and r7 > r7_prev and c_now > e21: return {"pair":pair,"dir":"CALL","conf":88,"price":c_now,"rsi":r7,"reason":f"Pullback CALL","payout":payout,"expiry":120,"atr":0,"rejected":False}
        else:
            if 45 <= r7 <= 60 and 42 <= r14 <= 58 and r7 < r7_prev and c_now < e21: return {"pair":pair,"dir":"PUT","conf":88,"price":c_now,"rsi":r7,"reason":f"Pullback PUT","payout":payout,"expiry":120,"atr":0,"rejected":False}
        return None
    except: return None
def pullback_scanner_loop(cid, pair, original_dir):
    start = time.time(); PULLBACK_STATE[cid] = {"pair":pair,"dir":original_dir,"active":True}; bot.send_message(cid, f"🔍 **Pullback Scan ON**\n💱 {pair} {original_dir}\n⏳ 5 min - Scanning every 10s")
    while PULLBACK_STATE.get(cid, {}).get("active") and time.time() - start < 300:
        if check_and_reset_new_day(): PULLBACK_STATE[cid]["active"] = False; return
        if not can_trade_today(): PULLBACK_STATE[cid]["active"] = False; return
        d = check_pullback_entry(pair, original_dir)
        if d:
            levels = OTC_MARTI["levels"]; idx = OTC_MARTI["loss_streak"]; mult = levels[idx]; amt = OTC_MARTI["base"] * mult; names = ["Real Entry","Martingale 1","Martingale 2","Martingale 3"]; dir_e = "🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"
            mk = types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("✅ WIN", callback_data=f"manual_win_{pair}"), types.InlineKeyboardButton("❌ LOSS", callback_data=f"manual_loss_{pair}_{d['dir']}")); mk.add(types.InlineKeyboardButton("⏭️ SKIP", callback_data=f"skip_{pair}"))
            try:
                df = get_candles(pair); sup, res, ds, dr = get_support_resistance(df) if df is not None else (d['price'], d['price'], 0, 0); buf = generate_chart(pair, df, sup, res, d['price'], d['dir'], d['rsi']) if df is not None else None; txt = f"""🎯 **PULLBACK ENTRY**\n💱 {pair}\n📊 {dir_e} | {d['conf']:.0f}%\n\n**Entry:** {d['price']:.5f}\n**RSI:** {d['rsi']:.1f}\n**Trend:** Pullback to EMA\n**S/R:** {ds:.1f} ATR to Sup | {dr:.1f} to Res\n\n💸 {int(d['payout']*100)}% | ⏱️ 2 Min\n**Next:** {names[idx]} - ${amt:.2f} Level {idx+1}/4\n"""
                if buf: bot.send_photo(cid, buf, caption=txt, parse_mode="Markdown", reply_markup=mk)
                else: bot.send_message(cid, txt, parse_mode="Markdown", reply_markup=mk)
            except: bot.send_message(cid, f"🎯 PULLBACK {pair} {dir_e} Entry {d['price']:.5f} RSI {d['rsi']:.1f}", reply_markup=mk, parse_mode="Markdown")
            PULLBACK_STATE[cid]["active"] = False; return
        time.sleep(10)
    PULLBACK_STATE[cid] = {"active":False}; bot.send_message(cid, "⏱️ Pullback timeout (5 min) - No entry.")
def daily_summary_loop():
    global DAILY_SUMMARY_SENT; tz = pytz.timezone("Africa/Lagos")
    while True:
        try:
            now = datetime.now(tz); today_str = now.strftime("%Y-%m-%d")
            if now.hour == 20 and now.minute < 5 and DAILY_SUMMARY_SENT != today_str:
                DAILY_SUMMARY_SENT = today_str; total = STATS['wins'] + STATS['loss']; wr = (STATS['wins']/total*100) if total else 0; msg = f"📊 **DAILY SUMMARY - {today_str}**\n🏆 Wins: {STATS['wins']} | ❌ Losses: {STATS['loss']} | 📈 WR: {wr:.1f}%\n📅 Trades: {STATS['daily_trades']}/30\n🌙 Rest well Trailblazer, tomorrow we stack again! 💰"
                try: bot.send_message(OWNER_ID, msg, parse_mode="Markdown")
                except: pass
            time.sleep(60)
        except: time.sleep(60)
def trailblazer_market_scanner():
    tz = pytz.timezone("Africa/Lagos"); last_news_alert = 0
    while True:
        try:
            if not is_real_hours() or not IQ_CONNECTED: time.sleep(60); continue
            news = get_upcoming_news(); urgent_news = [n for n in news if 0 <= n["in_min"] <= 30]
            if urgent_news and time.time() - last_news_alert > 3600:
                last_news_alert = time.time(); news_txt = format_news_alert(urgent_news)
                try: bot.send_message(OWNER_ID, f"📰 **NEWS ALERT**\n\n{news_txt}🚨 Don't trade those currencies now!", parse_mode="Markdown")
                except: pass
            if time.time() - MARKET_GOOD_SENT["last_alert"] < 2700: time.sleep(60); continue
            if is_signal_active(): time.sleep(60); continue
            good_pairs = 0; strong_pairs = []
            for pair in ["EURUSD","GBPUSD","EURGBP","AUDUSD","USDCAD"]:
                if is_pair_blocked(pair): continue
                if is_news_blocking_pair(pair, minutes=30): continue
                try:
                    df = get_candles(pair)
                    if df is None: continue
                    adx, _, _ = calc_adx_v12(df); payout = get_payout(pair)
                    if adx >= 25 and payout >= 0.80: good_pairs += 1; strong_pairs.append(pair)
                except: pass
                time.sleep(1)
            if urgent_news and good_pairs < 5: time.sleep(300); continue
            if good_pairs >= 5:
                MARKET_GOOD_SENT["last_alert"] = time.time(); greet = get_greeting(); pairs_txt = " • ".join(strong_pairs[:5]); session_boost, session_name = get_session_boost("EURUSD"); msg = f"🔥 **MARKET IS GOOD** 🔥\n\n{greet}\n✅ {good_pairs}/5 Strong | ⏰ {session_name}\n💱 Hot: {pairs_txt}\n🎯 Bot scanning now... 88%+ only!\n💰 STACKING TIME! 🚀"
                try: bot.send_message(OWNER_ID, msg, parse_mode="Markdown")
                except: pass
            time.sleep(300)
        except: time.sleep(60)
def morning_greet_loop():
    global MORNING_GREET_SENT; tz = pytz.timezone("Africa/Lagos")
    while True:
        try:
            now = datetime.now(tz); today = now.strftime("%Y-%m-%d")
            if now.hour == 7 and now.minute < 5 and MORNING_GREET_SENT != today:
                MORNING_GREET_SENT = today; msg = "🌅 **GOOD MORNING TRAILBLAZER** 🌅\n\n☀️ 7AM - Market opened!\n✅ Bot scanning 19 REAL pairs\n✅ 88%+ only | Max 30 trades\n🧠 Brain ready | 📰 News ON\n🔥 LET'S STACK! 🚀💰"
                try: bot.send_message(OWNER_ID, msg, parse_mode="Markdown")
                except: pass
            time.sleep(60)
        except: time.sleep(60)
def real_signal_scanner():
    last_signal = {}; tz = pytz.timezone("Africa/Lagos")
    while True:
        try:
            check_and_reset_new_day()
            if is_signal_active(): time.sleep(15); continue
            if time.time() - LAST_GLOBAL_SIGNAL["time"] < GLOBAL_COOLDOWN: time.sleep(30); continue
            if is_real_hours() and IQ_CONNECTED:
                if not can_trade_today(): time.sleep(60); continue
                candidates = []
                for pair in REAL_PAIRS:
                    if is_pair_blocked(pair): continue
                    if pair in last_signal and time.time() - last_signal[pair] < 600: continue
                    d = analyze_sniper_v12(pair, sniper_mode=True)
                    if d and not d.get('rejected') and d['conf'] >= 88: candidates.append((pair, d))
                    time.sleep(3)
                if candidates:
                    candidates.sort(key=lambda x: x[1]['conf'], reverse=True); pair, d = candidates[0]; mk = types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("✅ WIN", callback_data=f"manual_win_{pair}"), types.InlineKeyboardButton("❌ LOSS", callback_data=f"manual_loss_{pair}_{d['dir']}")); mk.add(types.InlineKeyboardButton("⏭️ SKIP", callback_data=f"skip_{pair}"))
                    try: send_signal_with_chart(OWNER_ID, pair, d, mk); last_signal[pair] = time.time(); LAST_GLOBAL_SIGNAL["time"] = time.time(); start_signal(pair, d['dir'], d['conf'], d['rsi'], d.get('adx', 30))
                    except Exception as e: print(f"Send err {e}")
            time.sleep(25)
        except: time.sleep(30)
@bot.message_handler(commands=['start','stop','mode','balance','results','brain','news'])
def start(m):
    if not is_allowed(m.from_user.id): bot.send_message(m.chat.id,"❌ Private"); return
    if m.text.startswith('/news'):
        news = get_upcoming_news()
        if not news: bot.send_message(m.chat.id, "📰 **NEWS**\n✅ No high impact news in next 2h - Clean!", parse_mode="Markdown"); return
        txt = "📰 **UPCOMING NEWS**\n\n" + format_news_alert(news); bot.send_message(m.chat.id, txt, parse_mode="Markdown"); return
    if m.text.startswith('/brain'):
        txt="🧠 **BRAIN V21**\n\n"; best=[]; bad=[]
        for pair, s in PAIR_BRAIN.items():
            total=s["wins"]+s["loss"]
            if total>=3:
                wr=s["wins"]/total*100; line=f"{PAIR_EMOJI.get(pair,pair)}: W{s['wins']} L{s['loss']} = {wr:.0f}% {'🚫' if is_pair_blocked(pair) else ''}\n"
                if wr>=60: best.append(line)
                elif wr<50: bad.append(line)
        txt+="🏆 BEST:\n"+("".join(best) if best else "No data yet\n")+"\n💀 BAD:\n"+("".join(bad) if bad else "None\n"); bot.send_message(m.chat.id,txt,parse_mode="Markdown"); return
    if m.text.startswith('/stop'):
        if m.chat.id in AUTO_STATE: AUTO_STATE[m.chat.id]['running']=False; bot.send_message(m.chat.id,"🛑 Stopping...")
        else: bot.send_message(m.chat.id,"Auto not running"); return
    if m.text.startswith('/results'):
        if not OTC_SESSION_RESULTS: bot.send_message(m.chat.id,"📭 No trades yet"); return
        wins=sum(1 for x in OTC_SESSION_RESULTS if x['win']); losses=len(OTC_SESSION_RESULTS)-wins; pnl_total=sum(x['pnl'] for x in OTC_SESSION_RESULTS); idx=OTC_MARTI["loss_streak"]; txt=f"📊 **RESULTS**\nTotal: {len(OTC_SESSION_RESULTS)} | W:{wins} L:{losses} | PnL: ${pnl_total:.2f}\nToday: {STATS['daily_trades']}/30 | Level {idx+1}/4\n\n"
        for r in OTC_SESSION_RESULTS[-25:]: txt+=f"{'✅' if r['win'] else '❌'} {r['time']} {r['pair']} {r['dir']} ${r['amt']} L{r['level']} {r['conf']}% {r['pnl']:+.2f}\n"
        bot.send_message(m.chat.id,txt,parse_mode="Markdown"); return
    if m.text.startswith('/mode'):
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); sb, sn = get_session_boost("EURUSD"); txt=f"📍 **MODE V21**\n{get_greeting()}\n⏰ {now.strftime('%A %H:%M:%S WAT')} | {sn}\n📊 {get_mode_text()}\n💎 IQ: {'✅' if IQ_CONNECTED else '❌'}\n📅 Today: {STATS['daily_trades']}/30\n⏳ Active: {ACTIVE_SIGNAL['pair'] if is_signal_active() else 'None'}"; bot.send_message(m.chat.id,txt,parse_mode="Markdown"); return
    if m.text.startswith('/balance'):
        try:
            if not IQ_CONNECTED: bot.send_message(m.chat.id,f"💰 **BALANCES**\nIQ: ❌ Not connected"); return
            demo=get_real_balance("PRACTICE"); real=get_real_balance("REAL"); bot.send_message(m.chat.id,f"💰 **BALANCES**\n🟢 DEMO: ${demo:.2f}\n🔴 REAL: ${real:.2f}")
        except Exception as e: bot.send_message(m.chat.id,f"Balance error {e}")
        return
    try: bal_demo=get_real_balance("PRACTICE") if IQ_CONNECTED else STATS.get("real_balance",0.0)
    except: bal_demo=0.0
    mk=types.InlineKeyboardMarkup(row_width=1); mk.add(types.InlineKeyboardButton(f"📈 TRADE REAL (19) - ${bal_demo:.2f}",callback_data="trade_real")); mk.add(types.InlineKeyboardButton("📊 MY STATS",callback_data="stats"),types.InlineKeyboardButton("🧠 BRAIN",callback_data="brain_btn"),types.InlineKeyboardButton("📰 NEWS",callback_data="news_btn"),types.InlineKeyboardButton("⚙️ SETTINGS",callback_data="settings"))
    greet = get_greeting(); greet_msg = get_greeting_msg(); sb, sn = get_session_boost("EURUSD"); txt=f"""{greet}\n{greet_msg}\n\n🤖 **Z-BOT V21 - S/R 15/30/60 + RSI MTF** 🤖\n💎 IQ: {'✅' if IQ_CONNECTED else '❌'} | 💰 DEMO ${bal_demo:.2f}\n🏆 W:{STATS['wins']} L:{STATS['loss']} | 📅 Today: {STATS['daily_trades']}/30\n⏰ Session: {sn}\n📍 {get_mode_text()}\n\n👇 **Select:**"""; bot.send_message(m.chat.id,txt,reply_markup=mk,parse_mode="Markdown")
@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_allowed(c.from_user.id): bot.answer_callback_query(c.id,"❌ Private"); return
    data=c.data; cid=c.message.chat.id
    if data=="news_btn":
        news = get_upcoming_news()
        if not news: bot.send_message(cid, "📰 **NEWS**\n✅ No high impact news in next 2h", parse_mode="Markdown"); return
        txt = "📰 **UPCOMING NEWS**\n\n" + format_news_alert(news); bot.send_message(cid, txt, parse_mode="Markdown"); return
    if data.startswith("skip_"):
        pair=data.replace("skip_","")
        if cid in PULLBACK_STATE: PULLBACK_STATE[cid]["active"]=False
        clear_signal(); LAST_GLOBAL_SIGNAL["time"] = time.time() - (GLOBAL_COOLDOWN - SKIP_COOLDOWN); bot.answer_callback_query(c.id,"Skipped - Next in 5 min"); bot.send_message(cid,f"⏭️ **SKIPPED** {pair}\n⏳ Next in 5 mins"); return
    if data.startswith("manual_win_"):
        pair=data.replace("manual_win_",""); record_brain(pair, True, ACTIVE_SIGNAL.get("conf",88), ACTIVE_SIGNAL.get("rsi",50), ACTIVE_SIGNAL.get("adx",30)); OTC_MARTI["loss_streak"]=0
        if cid in PULLBACK_STATE: PULLBACK_STATE[cid]["active"]=False
        clear_signal(); STATS['wins']+=1; count_trade(); bot.answer_callback_query(c.id,"WIN - Reset"); bot.send_message(cid,f"✅ **WIN!** {pair}\n♻️ RESET to $1\n📅 Today: {STATS['daily_trades']}/30\n💰 Keep stacking! 🚀"); return
    if data.startswith("manual_loss_"):
        parts=data.replace("manual_loss_","").rsplit("_",1); pair=parts[0]; orig_dir=parts[1] if len(parts)>1 else "CALL"; record_brain(pair, False, ACTIVE_SIGNAL.get("conf",88), ACTIVE_SIGNAL.get("rsi",50), ACTIVE_SIGNAL.get("adx",30)); OTC_MARTI["loss_streak"]+=1; STATS['loss']+=1; count_trade()
        if OTC_MARTI["loss_streak"]>=4:
            OTC_MARTI["loss_streak"]=0
            if cid in PULLBACK_STATE: PULLBACK_STATE[cid]["active"]=False
            clear_signal(); bot.answer_callback_query(c.id,"Chain finished"); bot.send_message(cid,f"⛔ **CHAIN FINISHED** {pair}\n❌ Lost: $1 + $2 + $4 + $8 = -$15\n♻️ RESET to $1\n📅 Today: {STATS['daily_trades']}/30"); return
        levels=OTC_MARTI["levels"]; idx=OTC_MARTI["loss_streak"]; mult=levels[idx]; next_amt=OTC_MARTI["base"]*mult; names=["","Martingale 1","Martingale 2","Martingale 3"]; bot.answer_callback_query(c.id,f"LOSS - Next {names[idx]} ${next_amt}"); bot.send_message(cid,f"❌ **LOSS** {pair}\n👉 Next: **{names[idx]} - ${next_amt:.2f} Level {idx+1}/4**\n🔍 Scanning pullback..."); threading.Thread(target=pullback_scanner_loop, args=(cid, pair, orig_dir), daemon=True).start(); return
    if data=="brain_btn":
        txt="🧠 **BRAIN V21**\n\n"; best=[]; bad=[]
        for pair,s in PAIR_BRAIN.items():
            total=s["wins"]+s["loss"]
            if total>=3:
                wr=s["wins"]/total*100; line=f"{PAIR_EMOJI.get(pair,pair)}: W{s['wins']} L{s['loss']} = {wr:.0f}% {'🚫' if is_pair_blocked(pair) else ''}\n"
                if wr>=60: best.append(line)
                elif wr<50: bad.append(line)
        txt+="🏆 BEST:\n"+("".join(best) if best else "No data yet\n")+"\n💀 BAD:\n"+("".join(bad) if bad else "None\n"); bot.send_message(cid,txt,parse_mode="Markdown"); return
    if data=="trade_real":
        mk=types.InlineKeyboardMarkup(row_width=1); mk.add(types.InlineKeyboardButton("🔍 SCAN ALL REAL NOW (19)",callback_data="scan_all_real"))
        for p in REAL_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}",callback_data=f"real_pair_{p}"))
        bot.send_message(cid,f"📈 **TRADE REAL V21**\n📍 {get_mode_text()}\n📅 Today: {STATS['daily_trades']}/30",reply_markup=mk,parse_mode="Markdown"); return
    if data=="scan_all_real":
        if is_signal_active(): bot.send_message(cid,f"⏳ **One signal active**\n💱 {ACTIVE_SIGNAL['pair']} {ACTIVE_SIGNAL['dir']}\nFinish it first."); return
        if not can_trade_today(): bot.send_message(cid,"⛔ Max 30 reached today."); return
        bot.answer_callback_query(c.id,"Scanning 19 pairs..."); scan_msg=bot.send_message(cid,"🔍 **SCANNING 19 REAL PAIRS...**\n⏳ ~12 sec"); results=[]; datas={}
        for pair in REAL_PAIRS:
            if is_pair_blocked(pair): results.append((pair,0,"-","🧠 Blocked","🔴 BLOCKED",120)); continue
            nb = is_news_blocking_pair(pair, minutes=30)
            if nb: results.append((pair,0,"-","📰 News","🔴 NEWS",120)); continue
            d=analyze_sniper_v12(pair,sniper_mode=False)
            if not d: results.append((pair,0,"-","No data","🔴 NO TRADE",120)); continue
            conf=d['conf']; dir_=d['dir']; reason=d['reason']; exp=d['expiry']
            if conf>=88: status="🟢 READY"
            elif conf>=65: status="🟡 WAIT"
            else: status="🔴 NO TRADE"
            results.append((pair,conf,dir_,reason,status,exp)); datas[pair]=d
            try: bot.edit_message_text(f"🔍 Scanning... {pair} {conf:.0f}%",cid,scan_msg.message_id)
            except: pass
            time.sleep(0.3)
        results.sort(key=lambda x: x[1], reverse=True); txt="📊 **REAL V21 READINESS**\n"; txt+=f"📍 {get_mode_text()}\n⏰ {datetime.now(pytz.timezone('Africa/Lagos')).strftime('%H:%M:%S WAT')} | 📅 {STATS['daily_trades']}/30\n\n"
        for pair,conf,dir_,reason,status,exp in results: emoji=PAIR_EMOJI.get(pair,pair); txt+=f"{status} {emoji}: {conf:.0f}% {dir_}\n"
        best=results[0] if results else None
        if best and best[1]>=88: txt+=f"\n💡 **BEST:** {PAIR_EMOJI.get(best[0],best[0])} {best[1]:.0f}%"
        mk=types.InlineKeyboardMarkup(row_width=2)
        if best and best[1]>=88: mk.add(types.InlineKeyboardButton(f"✅ TRADE BEST {best[0]}",callback_data=f"real_pair_{best[0]}"))
        mk.add(types.InlineKeyboardButton("🔄 RE-SCAN",callback_data="scan_all_real")); bot.send_message(cid,txt,reply_markup=mk,parse_mode="Markdown")
        if best and best[1]>=88 and best[0] in datas:
            time.sleep(0.5); best_data=datas[best[0]]; mk2=types.InlineKeyboardMarkup(row_width=2); mk2.add(types.InlineKeyboardButton("✅ WIN",callback_data=f"manual_win_{best_data['pair']}"),types.InlineKeyboardButton("❌ LOSS",callback_data=f"manual_loss_{best_data['pair']}_{best_data['dir']}")); mk2.add(types.InlineKeyboardButton("⏭️ SKIP",callback_data=f"skip_{best_data['pair']}")); send_signal_with_chart(cid, best_data['pair'], best_data, mk2); start_signal(best_data['pair'], best_data['dir'], best_data['conf'], best_data['rsi'], best_data.get('adx',30))
        return
    if data.startswith("real_pair_"):
        pair=data.replace("real_pair_","")
        if is_signal_active() and ACTIVE_SIGNAL['pair']!=pair: bot.send_message(cid,f"⏳ **One signal active** {ACTIVE_SIGNAL['pair']}"); return
        if is_pair_blocked(pair): bot.send_message(cid,f"🧠 **{pair} Blocked** - Losing pair, 2h block"); return
        nb = is_news_blocking_pair(pair, minutes=30)
        if nb: bot.send_message(cid,f"📰 **{pair} Blocked by NEWS**\n🔴 {nb['country']} - {nb['title']}\n⏰ In {nb['in_min']} min"); return
        bot.answer_callback_query(c.id,f"Scanning {pair}..."); scan_msg=bot.send_message(cid,f"🔍 **SCAN {PAIR_EMOJI.get(pair,pair)}**\n0%\n🚀 Sniper..."); legit_live_scan(cid,scan_msg.message_id,pair); d=analyze_sniper_v12(pair,sniper_mode=False)
        if not d or d['conf']<88:
            mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🔄 RETRY",callback_data=f"real_pair_{pair}"),types.InlineKeyboardButton("📈 SCAN ALL",callback_data="scan_all_real")); bot.send_message(cid,f"⚠️ **No safe trade for {pair}**\n📊 {d['conf'] if d else 0}% < 88%\n🛡️ {d['reason'] if d else 'No data'}",reply_markup=mk); return
        mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("✅ WIN",callback_data=f"manual_win_{pair}"),types.InlineKeyboardButton("❌ LOSS",callback_data=f"manual_loss_{pair}_{d['dir']}")); mk.add(types.InlineKeyboardButton("⏭️ SKIP",callback_data=f"skip_{pair}")); mk.add(types.InlineKeyboardButton("🔁 SAME PAIR",callback_data=f"real_pair_{pair}"),types.InlineKeyboardButton("📈 SCAN ALL",callback_data="scan_all_real")); send_signal_with_chart(cid, pair, d, mk); start_signal(pair, d['dir'], d['conf'], d['rsi'], d.get('adx',30)); return
    if data=="trade" or data=="scan_all_otc" or data=="auto_setup" or data.startswith("auto_pair_") or data.startswith("auto_bal_") or data.startswith("auto_amt_") or data.startswith("pair_"): bot.answer_callback_query(c.id,"OTC Disabled"); bot.send_message(cid,"⛔ **OTC DISABLED**\nREAL only from 7AM."); return
    if data=="stop_auto":
        if cid in AUTO_STATE: AUTO_STATE[cid]['running']=False; bot.send_message(cid,"🛑 Stopping..."); return
    if data=="stats":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0; bal=get_real_balance("PRACTICE"); sb,sn=get_session_boost("EURUSD"); bot.send_message(cid,f"📊 **STATS V21**\n📍 {get_mode_text()}\n{get_greeting()}\n⏰ {sn}\n🏆 W:{STATS['wins']} L:{STATS['loss']} WR:{wr:.1f}%\n💰 Bal: ${bal:.2f}\n📅 Today: {STATS['daily_trades']}/30\n🧠 Brain: {len(PAIR_BRAIN)} pairs",parse_mode="Markdown")
    if data=="settings": bot.send_message(cid,f"⚙️ **SETTINGS V21**\n\n📊 Chart + Brief Signal\nEntry / RSI / Trend / S/R only\n🛡️ S/R 15/30/60 0.8 ATR + RSI MTF + Rejection\n⏱️ Expiry SMART 1/2/3/5 Min\nREAL 7AM-8PM 88%+ | Max 30/day\n💰 Marti 1-2-4-8 MANUAL\n🧠 Brain ON\n⏭️ Skip - Next in 5 mins")
threading.Thread(target=background_iq, daemon=True).start()
threading.Thread(target=real_signal_scanner,daemon=True).start()
threading.Thread(target=daily_summary_loop,daemon=True).start()
threading.Thread(target=trailblazer_market_scanner,daemon=True).start()
threading.Thread(target=morning_greet_loop,daemon=True).start()
if __name__ == "__main__":
    try:
        url=os.getenv("RENDER_EXTERNAL_URL")
        if url and BOT_TOKEN: requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={url}/{BOT_TOKEN}", timeout=5); print(f"Webhook set {url}")
    except: pass
    port=int(os.getenv("PORT",10000)); print(f"Starting Flask on 0.0.0.0:{port} - V21 S/R 15/30/60 + RSI MTF"); app.run(host="0.0.0.0", port=port, threaded=True)
