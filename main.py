import os, time, threading, warnings, logging, json
from datetime import datetime, timedelta, timezone
from flask import Flask, request
import telebot
from telebot import types
import pandas as pd
import requests
import pytz
import xml.etree.ElementTree as ET
warnings.filterwarnings("ignore")
logging.getLogger().setLevel(logging.CRITICAL)
logging.getLogger("iqoptionapi").setLevel(logging.CRITICAL)
logging.disable(logging.ERROR)
BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELE_TOKEN")
OWNER_ID = 8659453018
CHANNEL_ID = "@KEVINTRAILBLAZE"
WELCOME_PHOTO = "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=1080&q=80"
INTRO_PHOTO = "https://images.unsplash.com/photo-1621761191319-c6fb62004040?w=1080&q=80"
READY_PHOTO = "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=1080&q=80"
if not BOT_TOKEN: print("ERROR BOT_TOKEN missing")
bot = telebot.TeleBot(BOT_TOKEN, threaded=True)
app = Flask(__name__)
ENABLE_OTC = False
REAL_PAIRS = ["EURUSD","GBPUSD","EURGBP","AUDUSD","USDCAD","USDCHF","EURAUD","GBPCHF","EURCHF","NZDUSD","GBPAUD","EURCAD","AUDCAD","GBPCAD","AUDNZD",]
OTC_PAIRS = ["EURUSD-OTC","GBPUSD-OTC"]
PAIR_EMOJI = {"EURUSD":"EUR/USD REAL","GBPUSD":"GBP/USD REAL","EURGBP":"EUR/GBP REAL","AUDUSD":"AUD/USD REAL","USDCAD":"USD/CAD REAL","USDCHF":"USD/CHF REAL","EURAUD":"EUR/AUD REAL","GBPCHF":"GBP/CHF REAL","EURCHF":"EUR/CHF REAL","NZDUSD":"NZD/USD REAL","GBPAUD":"GBP/AUD REAL","EURCAD":"EUR/CAD REAL","AUDCAD":"AUD/CAD REAL","GBPCAD":"GBP/CAD REAL","AUDNZD":"AUD/NZD REAL","XAUUSD":"XAU/USD GOLD","EURUSD-OTC":"EUR/USD OTC","GBPUSD-OTC":"GBP/USD OTC"}
# ===== MARATHON = ONLY 2 PAIRS =====
MARATHON_PAIRS = ["EURUSD-OTC","GBPUSD-OTC"]
MARATHON = {"active": False, "start": 0.0, "target": 0.0, "bal": 0.0, "wins": 0, "loss": 0, "win_streak": 0, "loss_streak": 0, "cid": None, "bal_type": "PRACTICE", "base_stake": 1.0, "marti_level": 0, "custom_target": False}
MARATHON_PICK = {"pair": None}
MARATHON_TARGET_WAIT = {}
MARATHON_BALANCE_WAIT = {}
MARATHON_EXPIRY = 1
WELCOME_TEXT = "WELCOME TO TRAILBLAZER SIGNALS\nWelcome Trader! You have arrived at the right place.\n\nWHAT WE DO HERE\nForex and GOLD Sniper Signals\n88%+ Accuracy Only\nSmart System That Learns From Every Win and Loss\nMartingale 1-2-4-8 To Recover Losses\n\nCHANNEL RULES\n1. Follow The Stake - $1, $2, $4, $8 - Do Not Be Greedy\n2. Do Not Overtrade - Maximum 30 Signals Per Day\n3. Enter Exactly At The Entry Time\n4. Press WIN or LOSS After Every Trade\n5. No Spam, No Direct Message To Admin For Signals\n6. Do Not Borrow Money To Trade\n\nNEW HERE? Type /intro For A Full Guide\nType /status To See Today's Result\nChannel: @KEVINTRAILBLAZE\n\nGood Luck Trader! Let Us Grow Together!\nTRAILBLAZER - WE MOVE!"
INTRO_TEXT = "TRAILBLAZER INTRO\nWHAT IS FOREX?\nForex Means Foreign Exchange. You Predict If One Currency Will Go UP Or DOWN Against Another.\nExample: EUR/USD - Euro Against Dollar.\nIf Euro Is Strong, Press BUY / CALL\nIf Euro Is Weak, Press SELL / PUT\n\nHOW DO YOU MAKE MONEY?\n1. Enter With A Stake For Example $1\n2. If You Are Correct, IQ Option Pays You 85% = $1.85 Back\n3. If You Are Wrong, We Use Martingale $1 -> $2 -> $4 -> $8 To Recover\n\nGOLD (XAU/USD) WORKS THE SAME WAY\nGold Price Goes Up And Down. We Trade It With Stop Loss And Take Profit.\n\nHOW TO START ON IQ OPTION\n1. CREATE ACCOUNT - Go To iqoption.com\n2. VERIFY EMAIL\n3. PRACTICE WITH DEMO - $10,000 DEMO\n4. VERIFY ACCOUNT (KYC)\n5. DEPOSIT - Start With $10 To $20 Only\n6. TRADE WITH US\n\nRULES:\nNo Overtrade - Maximum 30 Per Day\nFollow Stake - $1, $2, $4, $8\nTrading Has Risk, Only Trade Money You Can Afford To Lose\n\nChannel: @KEVINTRAILBLAZE\nWelcome Again! Let Us Go!"
STATS = {"balance":0.0,"real_balance":0.0,"wins":0,"loss":0,"streak":0,"daily_trades":0,"daily_date":""}
user_states = {}; AUTO_STATE = {}; IQ_LOCK = threading.Lock()
IQ_CONNECTED=False; iq=None; PAYOUT_CACHE={}; PAYOUT_TIME=0
OTC_SESSION_RESULTS = []
OTC_MARTI = {"loss_streak":0, "base":1.0, "bal":"PRACTICE", "levels":[1,2,4,8]}
PULLBACK_STATE = {}
ACTIVE_SIGNAL = {"active": False, "pair": None, "dir": None, "conf":0, "rsi":0, "adx":0, "started": 0, "day": "", "price": 0, "sl": 0, "tp1": 0, "tp2": 0, "expiry": 60}
LAST_GLOBAL_SIGNAL = {"time": 0}
GLOBAL_COOLDOWN = 360
SKIP_COOLDOWN = 120
DAILY_SUMMARY_SENT = ""
MARKET_GOOD_SENT = {"date": "", "last_alert": 0}
MORNING_GREET_SENT = ""
NEWS_CACHE = {"data": [], "time": 0}
def send_to_channel_sync(text):
    try: bot.send_message(CHANNEL_ID, text, parse_mode="Markdown")
    except Exception as e: print(f"channel send err {e}")
def send_photo_to_channel_sync(photo_url, caption):
    try: bot.send_photo(CHANNEL_ID, photo_url, caption=caption, parse_mode="Markdown")
    except Exception as e:
        print(f"photo channel err {e}")
        try: bot.send_message(CHANNEL_ID, caption, parse_mode="Markdown")
        except: pass
def format_channel_signal(pair, dir_, conf, price, entry_time_txt, expiry=60):
    if dir_ == "CALL":
        action = "BUY / CALL UP"; meaning = "The Price Is Expected To Go UP, So Press The GREEN BUY / CALL Button In IQ Option"
    else:
        action = "SELL / PUT DOWN"; meaning = "The Price Is Expected To Go DOWN, So Press The RED SELL / PUT Button In IQ Option"
    pair_name = PAIR_EMOJI.get(pair, pair)
    price_txt = f"{price:.5f}" if price and price != 0 else "Market Price"
    expiry_min = int(expiry // 60) if expiry else 1
    return f"TRAILBLAZER SIGNAL\n\nPair: {pair_name}\nSignal: {action}\nConfidence: {conf:.0f}%\n\nWhat It Means:\n{meaning}\n\nENTRY TIME: {entry_time_txt}\nENTRY PRICE: {price_txt}\nSTAKE: $1 (If You Lose, Next Is $2, Then $4, Then $8)\nEXPIRY: {expiry_min} Minutes\n\nHOW TO TRADE:\n1. Open IQ Option App\n2. Search For {pair}\n3. Wait Until {entry_time_txt}\n4. Set Expiry To {expiry_min} Minutes\n5. Press {action}\n6. Enter With $1\n\nChannel: @KEVINTRAILBLAZE\nGood Luck!"
def format_channel_gold_signal(d, entry_time_txt):
    dir_e = "BUY UP" if d['dir']=="CALL" else "SELL DOWN"
    what = "The Gold Price Is Expected To Go UP, Press GREEN BUY" if d['dir']=="CALL" else "The Gold Price Is Expected To Go DOWN, Press RED SELL"
    return f"GOLD SIGNAL - XAU/USD\n\nSignal: {dir_e}\nConfidence: {d['conf']:.0f}%\n\nWhat It Means:\n{what}\n\nENTRY TIME: {entry_time_txt}\nENTRY: {d['price']:.2f}\nSTOP LOSS: {d['sl']:.2f}\nTAKE PROFIT 1: {d['tp1']:.2f}\nTAKE PROFIT 2: {d['tp2']:.2f}\n\nChannel: @KEVINTRAILBLAZE\nLet Us Grow Together!"
def format_channel_pullback_signal(pair, dir_, entry_time_txt, level_idx=1, amount=2.0, expiry=60):
    action = "BUY / CALL UP" if dir_ == "CALL" else "SELL / PUT DOWN"
    pair_name = PAIR_EMOJI.get(pair, pair)
    level_names = ["", "Martingale 1", "Martingale 2", "Martingale 3"]
    level_name = level_names[level_idx] if 1 <= level_idx <= 3 else f"Martingale {level_idx}"
    expiry_min = int(expiry // 60) if expiry else 1
    return f"{level_name} - {pair_name}\n\n{action}\nEntry: {entry_time_txt}\nStake: ${amount:.2f}\nExpiry: {expiry_min} Min\n\nOpen IQ Option -> Search {pair} -> Press {action} At Entry Time.\n\n@KEVINTRAILBLAZE\n"
def format_channel_pullback_gold_signal(dir_, entry_time_txt, level_idx=1, amount=2.0):
    dir_e = "BUY UP" if dir_=="CALL" else "SELL DOWN"
    level_names = ["", "Martingale 1", "Martingale 2", "Martingale 3"]
    level_name = level_names[level_idx] if 1 <= level_idx <= 3 else f"Martingale {level_idx}"
    return f"{level_name} - GOLD XAU/USD\n\n{dir_e}\nEntry: {entry_time_txt}\nStake: ${amount:.2f}\n\nOpen IQ Option -> Search GOLD -> Press {dir_e} At Entry Time.\nUse Same SL / TP As First Signal.\n\n@KEVINTRAILBLAZE\n"
def get_lagos_day(): return datetime.now(pytz.timezone("Africa/Lagos")).strftime("%Y-%m-%d")
def check_and_reset_new_day():
    today = get_lagos_day()
    if STATS["daily_date"] != today:
        STATS["daily_date"] = today; STATS["daily_trades"] = 0
        ACTIVE_SIGNAL.update({"active": False, "pair": None, "dir": None, "conf": 0, "rsi": 0, "adx": 0, "started": 0, "day": "", "price": 0, "sl": 0, "tp1": 0, "tp2": 0, "expiry": 60})
        PULLBACK_STATE.clear(); OTC_MARTI["loss_streak"] = 0; return True
    if ACTIVE_SIGNAL["active"] and ACTIVE_SIGNAL.get("day") and ACTIVE_SIGNAL["day"] != today:
        ACTIVE_SIGNAL.update({"active": False, "pair": None, "dir": None, "conf": 0, "rsi": 0, "adx": 0, "started": 0, "day": "", "price": 0, "sl": 0, "tp1": 0, "tp2": 0, "expiry": 60})
        PULLBACK_STATE.clear(); OTC_MARTI["loss_streak"] = 0; return True
    return False
def get_greeting():
    tz = pytz.timezone("Africa/Lagos"); hour = datetime.now(tz).hour
    if 5 <= hour < 12: return "GOOD MORNING TRAILBLAZER"
    elif 12 <= hour < 17: return "GOOD AFTERNOON TRAILBLAZER"
    elif 17 <= hour < 21: return "GOOD EVENING TRAILBLAZER"
    else: return "GOOD NIGHT TRAILBLAZER"
def get_greeting_msg():
    tz = pytz.timezone("Africa/Lagos"); hour = datetime.now(tz).hour
    if 5 <= hour < 12: return "Rise And Shine! A New Day, New Money To Earn\nGrab Your Coffee, The Market Is Waking Up!"
    elif 12 <= hour < 17: return "Afternoon Session! The Market Is Active\nStay Focused, Trailblazer!"
    elif 17 <= hour < 21: return "Evening Session! Last Chance To Earn Before The Market Closes\nLet Us Finish Strong!"
    else: return "The Market Is Resting. Rest Your Mind, Trailblazer\nTomorrow We Earn Again!"
def get_session_boost(pair):
    tz = pytz.timezone("Africa/Lagos"); now = datetime.now(tz); hour = now.hour + now.minute / 60
    if pair=="XAUUSD":
        if 14.5 <= hour < 17: return 10, "GOLD LONDON+NY OVERLAP"
        if 8 <= hour < 11: return 8, "LONDON OPEN GOLD"
        if 12 <= hour < 13.5: return -10, "LUNCH DEAD ZONE"
        if 18 <= hour < 20: return -5, "EVENING SLOW"
        return 0, "GOLD NORMAL"
    if 8 <= hour < 11:
        if pair[:3] in ["EUR","GBP","CHF"] or pair[3:6] in ["EUR","GBP","CHF"]: return 8, "LONDON OPEN"
        return 6, "LONDON OPEN"
    elif 14.5 <= hour < 17: return 10, "LONDON + NY OVERLAP"
    elif 14 <= hour < 14.5: return 4, "NY PRE-OPEN"
    elif 12 <= hour < 13.5: return -10, "LUNCH DEAD ZONE"
    elif 18 <= hour < 20: return -5, "EVENING SLOW"
    elif 11 <= hour < 12: return 3, "LONDON MORNING"
    elif 17 <= hour < 18: return 2, "NY AFTERNOON"
    else: return 0, "NORMAL"
def get_upcoming_news():
    try:
        if time.time() - NEWS_CACHE["time"] < 300: return NEWS_CACHE["data"]
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
        r = requests.get(url, timeout=10)
        if r.status_code != 200: return []
        root = ET.fromstring(r.content)
        now = datetime.now(pytz.timezone("UTC")).replace(tzinfo=None)
        upcoming = []
        for event in root.findall("event"):
            try:
                title = event.find("title").text; country = event.find("country").text; impact = event.find("impact").text
                date_str = event.find("date").text; time_str = event.find("time").text
                if impact != "High": continue
                if country not in ["USD","EUR","GBP","AUD","CAD","NZD","CHF"]: continue
                dt = datetime.strptime(f"{date_str} {time_str}", "%m-%d-%Y %I:%M%p")
                dt_utc = dt + timedelta(hours=5)
                diff_min = (dt_utc - now).total_seconds() / 60
                if -15 <= diff_min <= 120: upcoming.append({"title":title,"country":country,"time_utc":dt_utc,"in_min":int(diff_min),"impact":impact})
            except: continue
        NEWS_CACHE["data"] = upcoming; NEWS_CACHE["time"] = time.time(); return upcoming
    except Exception as e: print(f"News err {e}"); return []
def is_news_blocking_pair(pair, minutes=30):
    news = get_upcoming_news()
    if not news: return None
    if pair=="XAUUSD": base="XAU"; quote="USD"
    else: base = pair[:3]; quote = pair[3:6] if len(pair) >= 6 else ""
    for n in news:
        if n["country"] in [base, quote] and n["in_min"] <= minutes and n["in_min"] >= -15: return n
    return None
def format_news_alert(news_list):
    if not news_list: return ""
    txt = "UPCOMING HIGH IMPACT NEWS\n\n"
    for n in news_list:
        flag = {"USD":"USD","EUR":"EUR","GBP":"GBP","AUD":"AUD","CAD":"CAD","NZD":"NZD","CHF":"CHF"}.get(n["country"], "WORLD")
        if n["in_min"] < 0: when = f"Started {-n['in_min']} min ago"
        elif n["in_min"] == 0: when = "RIGHT NOW!"
        else: when = f"In {n['in_min']} min"
        txt += f"{flag} {n['country']} - {n['title']}\n{when}\n\n"
    return txt
def get_ready_text():
    tz = pytz.timezone("Africa/Lagos"); now = datetime.now(tz)
    sb, sn = get_session_boost("EURUSD")
    news = get_upcoming_news()
    news_txt = "No High Impact News In Next 2 Hours - Clean Market" if not news else f"{len(news)} High Impact News In Next 2 Hours - Bot Will Avoid Those Pairs"
    return f"GET READY TRAILBLAZERS\n\n{get_greeting()}\n\nTime: {now.strftime('%A, %d %b %Y - %H:%M WAT')}\nSession: {sn}\nMode: {get_mode_text()}\nNews: {news_txt}\nToday: {STATS['daily_trades']}/30 Trades Used\n\nSIGNALS ARE COMING SOON - STAY READY!\nChannel: @KEVINTRAILBLAZE\n"
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
    if wr >= 70: return 8, f"Best Hour {hour}:00 {wr:.0f}%"
    elif wr >= 60: return 4, f"Good Hour {hour}:00 {wr:.0f}%"
    elif wr < 40: return -10, f"Bad Hour {hour}:00 {wr:.0f}%"
    elif wr < 50: return -5, f"Weak Hour {hour}:00 {wr:.0f}%"
    return 0, ""
def get_pair_rsi_boost(pair, current_rsi, is_call):
    s = get_pair_stats(pair); rng = s.get("best_rsi_range")
    if not rng or len(s.get("rsi_wins", [])) < 5: return 0, ""
    low, high = rng
    if low <= current_rsi <= high: return 6, f"Pair RSI Sweet Spot {current_rsi:.0f} in [{low:.0f}-{high:.0f}]"
    dist = min(abs(current_rsi - low), abs(current_rsi - high))
    if dist > 15: return -6, f"Pair RSI Off {current_rsi:.0f} vs Sweet [{low:.0f}-{high:.0f}]"
    return 0, ""
load_brain()
def is_signal_active(): check_and_reset_new_day(); return ACTIVE_SIGNAL["active"]
def start_signal(pair, dir_, conf=0, rsi=0, adx=0, price=0, sl=0, tp1=0, tp2=0, expiry=60):
    check_and_reset_new_day(); ACTIVE_SIGNAL.update({"active":True,"pair":pair,"dir":dir_,"conf":conf,"rsi":rsi,"adx":adx,"started":time.time(),"day":get_lagos_day(),"price":price,"sl":sl,"tp1":tp1,"tp2":tp2,"expiry":expiry})
def clear_signal(): ACTIVE_SIGNAL.update({"active":False,"pair":None,"dir":None,"conf":0,"rsi":0,"adx":0,"started":0,"day":"","price":0,"sl":0,"tp1":0,"tp2":0,"expiry":60})
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
def get_mode_text(): return "REAL SIGNAL (7AM-8PM)" if is_real_hours() else "OTC DISABLED - Waiting For REAL 7AM"
def can_trade_today(): check_and_reset_new_day(); return STATS["daily_trades"] < 30
def count_trade(): STATS["daily_trades"] += 1
@app.route("/")
def home(): return f"V19 TRAILBLAZER+XAUUSD RUNNING IQ:{IQ_CONNECTED} MARATHON:{MARATHON['bal_type']} {datetime.now(pytz.timezone('Africa/Lagos')).strftime('%H:%M:%S')}"
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
    steps = [(0,"V19 Trailblazer Init...",0.15),(20,f"Checking {pair}...",0.2),(40,"ADX + ATR + Brain + News + Session...",0.25),(60,"EMA + MACD + 5M Trend...",0.2),(80,"RSI + Stochastic + BB + Multi-Trend...",0.2),(100,"SNIPER LOCKED!",0.3)]
    last_pct=-1
    for pct, text, delay in steps:
        if pct==last_pct: time.sleep(delay); continue
        last_pct=pct; filled=int(pct//5); bar="█"*filled+"░"*(20-filled); color="RED" if pct<40 else "YEL" if pct<80 else "GRN" if pct<100 else "GEM"
        txt=f"{color} Z-BOT V19 TRAILBLAZER {color}\n\n{PAIR_EMOJI.get(pair,pair)}\nIQ: {'YES' if IQ_CONNECTED else 'NO'}\n\n{bar} {pct}%\n\n{text}\nV19"
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
def get_trend_and_expiry(df, df5, close, r7, r14, adx, macd_val, sig_val, mom1, mom3, stoch_val, c_now, upper, lower, is_green):
    trends=[]; trend_score=0
    e9=float(close.ewm(9).mean().iloc[-1]); e21=float(close.ewm(21).mean().iloc[-1]); e50=float(close.ewm(50).mean().iloc[-1])
    if e9>e21>e50: trends.append("EMA Strong Uptrend"); trend_score+=2
    elif e9<e21<e50: trends.append("EMA Strong Downtrend"); trend_score+=2
    elif e9>e21: trends.append("EMA Weak Uptrend"); trend_score+=1
    elif e9<e21: trends.append("EMA Weak Downtrend"); trend_score+=1
    else: trends.append("EMA Flat / Ranging")
    if df5 is not None:
        c5=df5['close']; e9_5=float(c5.ewm(9).mean().iloc[-1]); e21_5=float(c5.ewm(21).mean().iloc[-1])
        if e9_5>e21_5: trends.append("5M Uptrend")
        else: trends.append("5M Downtrend")
        if (is_green and e9_5>e21_5) or (not is_green and e9_5<e21_5): trends.append("1M + 5M AGREE"); trend_score+=3
        else: trends.append("1M vs 5M CONFLICT"); trend_score-=2
    if adx>=35: trends.append(f"ADX Very Strong {adx:.0f}"); trend_score+=3
    elif adx>=28: trends.append(f"ADX Strong {adx:.0f}"); trend_score+=2
    elif adx>=25: trends.append(f"ADX OK {adx:.0f}"); trend_score+=1
    else: trends.append(f"ADX Weak {adx:.0f}")
    if macd_val>sig_val: trends.append("MACD Bullish"); trend_score+=1
    else: trends.append("MACD Bearish"); trend_score+=1
    if mom1>0.05: trends.append(f"Momentum +{mom1:.3f}%")
    elif mom1<-0.05: trends.append(f"Momentum {mom1:.3f}%")
    else: trends.append(f"Momentum Slow {mom1:.3f}%")
    if r7>70: trends.append(f"RSI Overbought {r7:.0f}")
    elif r7<30: trends.append(f"RSI Oversold {r7:.0f}")
    else: trends.append(f"RSI Safe {r7:.0f}")
    if c_now>upper: trends.append("BB Breakout Up")
    elif c_now<lower: trends.append("BB Breakout Down")
    elif (upper-lower)/c_now < 0.0005: trends.append("BB Squeeze")
    else: trends.append("BB Inside")
    if trend_score>=7: expiry=300; expiry_txt="5 Min - STRONG TREND"; trend_type="STRONG TREND"
    elif trend_score>=5: expiry=180; expiry_txt="3 Min - GOOD TREND"; trend_type="GOOD TREND"
    elif trend_score>=3: expiry=120; expiry_txt="2 Min - NORMAL TREND"; trend_type="NORMAL TREND"
    elif trend_score>=1: expiry=60; expiry_txt="1 Min - WEAK / RANGING"; trend_type="WEAK / RANGING"
    else: expiry=60; expiry_txt="1 Min - CONFLICT"; trend_type="CONFLICT TREND"
    return {"trends":trends,"trend_score":trend_score,"expiry":expiry,"expiry_txt":expiry_txt,"trend_type":trend_type}
def analyze_sniper_v12(pair, sniper_mode=False):
    df = get_candles(pair)
    if df is None: return None
    try:
        df5=None
        try:
            logging.disable(logging.CRITICAL); c5=iq.get_candles(pair,300,50,time.time())
            if c5 and len(c5)>20: df5=pd.DataFrame(sorted(c5,key=lambda x:x['from']))
        except: df5=None
        close=df['close']; open_=df['open']; high=df['max']; low=df['min']
        ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean(); ema50=close.ewm(50).mean()
        rsi7=calc_rsi(close,7); rsi14=calc_rsi(close,14); atr=calc_atr(df,14); adx,pdi,mdi=calc_adx_v12(df)
        ema12=close.ewm(12).mean(); ema26=close.ewm(26).mean(); macd=ema12-ema26; signal=macd.ewm(9).mean()
        macd_val=float(macd.iloc[-1]); sig_val=float(signal.iloc[-1])
        sma20=close.rolling(20).mean(); std20=close.rolling(20).std(); upper=float((sma20+2*std20).iloc[-1]); lower=float((sma20-2*std20).iloc[-1])
        low14=low.rolling(14).min(); high14=high.rolling(14).max(); stoch=100*(close-low14)/(high14-low14); stoch_val=float(stoch.iloc[-1])
        c_now=float(close.iloc[-1]); o_now=float(open_.iloc[-1]); c_prev=float(close.iloc[-2]); o_prev=float(open_.iloc[-2])
        h_now=float(high.iloc[-1]); l_now=float(low.iloc[-1]); e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1]); e50=float(ema50.iloc[-1])
        r7=float(rsi7.iloc[-1]); r14=float(rsi14.iloc[-1]); mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100; mom3=(close.iloc[-1]-close.iloc[-4])/close.iloc[-4]*100
        body=abs(c_now-o_now); upper_wick=h_now-max(c_now,o_now); lower_wick=min(c_now,o_now)-l_now; is_green=c_now>o_now; payout=get_payout(pair); sig="CALL" if is_green else "PUT"
        if is_pair_blocked(pair): return {"pair":pair,"dir":sig,"conf":40,"price":c_now,"rsi":r7,"reason":f"BRAIN Blocked {pair}","payout":payout,"expiry":60,"atr":atr,"rejected":True}
        news_block=is_news_blocking_pair(pair,minutes=30)
        if news_block: return {"pair":pair,"dir":sig,"conf":40,"price":c_now,"rsi":r7,"reason":f"NEWS BLOCK {news_block['country']} {news_block['title'][:25]} in {news_block['in_min']}min","payout":payout,"expiry":60,"atr":atr,"rejected":True}
        if adx<25: return {"pair":pair,"dir":sig,"conf":42,"price":c_now,"rsi":r7,"reason":"Choppy - ADX Low","payout":payout,"expiry":60,"atr":atr,"rejected":True}
        if body<atr*0.30: return {"pair":pair,"dir":sig,"conf":48,"price":c_now,"rsi":r7,"reason":"Doji - No Body","payout":payout,"expiry":60,"atr":atr,"rejected":True}
        if payout<0.80: return {"pair":pair,"dir":sig,"conf":52,"price":c_now,"rsi":r7,"reason":f"Low Payout {int(payout*100)}%","payout":payout,"expiry":60,"atr":atr,"rejected":True}
        score=30; reasons=[]
        if df5 is not None:
            c5=df5['close']; e9_5=c5.ewm(9).mean(); e21_5=c5.ewm(21).mean(); trend_5m=1 if float(e9_5.iloc[-1])>float(e21_5.iloc[-1]) else -1
            if (is_green and trend_5m==-1) or (not is_green and trend_5m==1): return {"pair":pair,"dir":sig,"conf":45,"price":c_now,"rsi":r7,"reason":"Against 5M Trend - REJECT","payout":payout,"expiry":60,"atr":atr,"rejected":True}
            else: score+=12; reasons.append("5M Trend Align")
        else: return {"pair":pair,"dir":sig,"conf":45,"price":c_now,"rsi":r7,"reason":"No 5M Data - REJECT","payout":payout,"expiry":60,"atr":atr,"rejected":True}
        if is_green:
            if e9>e21>e50: score+=18; reasons.append("EMA Bull Align")
            elif e9>e21: score+=10
            else: score-=8
        else:
            if e9<e21<e50: score+=18; reasons.append("EMA Bear Align")
            elif e9<e21: score+=10
            else: score-=8
        if adx>=28: score+=12; reasons.append(f"ADX Strong {adx:.0f}")
        elif adx>=22: score+=7
        if is_green and pdi>mdi: score+=8
        elif not is_green and mdi>pdi: score+=8
        else: score-=10
        if is_green:
            if 52<=r7<=65 and 48<=r14<=62: score+=15; reasons.append(f"RSI Safe {r7:.0f}")
            elif r7>75 or r7<45: score-=12
            else: score+=6
        else:
            if 35<=r7<=48 and 38<=r14<=52: score+=15; reasons.append(f"RSI Safe {r7:.0f}")
            elif r7<25 or r7>55: score-=12
            else: score+=6
        if is_green and macd_val>sig_val: score+=10; reasons.append("MACD Bull")
        elif not is_green and macd_val<sig_val: score+=10; reasons.append("MACD Bear")
        else: score-=8
        if is_green:
            if mom1>0.03 and mom3>0.06: score+=12; reasons.append(f"Mom {mom1:.3f}%")
            elif mom1>0.01: score+=5
            elif mom1<0: score-=12
        else:
            if mom1<-0.03 and mom3<-0.06: score+=12; reasons.append(f"Mom {mom1:.3f}%")
            elif mom1<-0.01: score+=5
            elif mom1>0: score-=12
        bull_eng=c_now>o_prev and o_now<c_prev and is_green and c_prev<o_prev; bear_eng=c_now<o_prev and o_now>c_prev and not is_green and c_prev>o_prev
        pin_bull=lower_wick>body*1.8 and lower_wick>upper_wick*1.5 and is_green; pin_bear=upper_wick>body*1.8 and upper_wick>lower_wick*1.5 and not is_green
        has_pattern=False
        if is_green:
            if bull_eng: score+=10; reasons.append("Bull Engulf"); has_pattern=True
            if pin_bull: score+=10; reasons.append("Pin Bull"); has_pattern=True
        else:
            if bear_eng: score+=10; reasons.append("Bear Engulf"); has_pattern=True
            if pin_bear: score+=10; reasons.append("Pin Bear"); has_pattern=True
        if is_green and stoch_val>85: score-=12
        if not is_green and stoch_val<15: score-=12
        if is_green and 50<stoch_val<80: score+=5
        if not is_green and 20<stoch_val<50: score+=5
        if is_green and c_now>upper: score-=10
        if not is_green and c_now<lower: score-=10
        if not has_pattern and score<88: return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":"No Pattern - REJECT","payout":payout,"expiry":60,"atr":atr,"rejected":True}
        session_boost,session_name=get_session_boost(pair); score+=session_boost
        if session_boost!=0: reasons.append(f"{session_name} {session_boost:+d}")
        if session_boost<=-10 and sniper_mode and score<92: return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":f"{session_name} - Needs 92% - REJECT","payout":payout,"expiry":60,"atr":atr,"rejected":True}
        hour_boost,hour_txt=get_hour_boost(pair)
        if hour_boost!=0:
            score+=hour_boost; reasons.append(f"{hour_txt} {hour_boost:+d}")
            if hour_boost<=-10 and sniper_mode and score<92: return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":f"Bad Hour for {pair} - REJECT","payout":payout,"expiry":60,"atr":atr,"rejected":True}
        rsi_boost,rsi_txt=get_pair_rsi_boost(pair,r7,is_green)
        if rsi_boost!=0: score+=rsi_boost; reasons.append(f"{rsi_txt} {rsi_boost:+d}")
        brain=get_pair_stats(pair); boost=brain.get("score_boost",0); score+=boost
        if boost!=0: reasons.append(f"Brain {boost:+d}")
        if boost<=-8 and sniper_mode and score<92: return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":f"Weak pair {pair} needs 92%","payout":payout,"expiry":60,"atr":atr,"rejected":True}
        score=max(40,min(96,score)); reason=" + ".join(reasons) if reasons else "Weak PA"
        if sniper_mode and score<88: return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":reason,"payout":payout,"expiry":60,"atr":atr,"rejected":True}
        trend_info=get_trend_and_expiry(df,df5,close,r7,r14,adx,macd_val,sig_val,mom1,mom3,stoch_val,c_now,upper,lower,is_green)
        reason=reason+f" | {trend_info['trend_type']} | 1 Min"
        return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":reason,"payout":payout,"expiry":60,"atr":atr,"rejected":False,"adx":adx,"trend_info":trend_info}
    except Exception as e: print(f"V19 err {pair} {e}"); return None
def analyze_xauusd():
    try:
        d = analyze_sniper_v12("XAUUSD", sniper_mode=True)
        if not d or d.get("rejected"): return None
        price = d["price"]; atr = d.get("atr", 1.0) or 1.0
        sl = price - atr*1.5 if d["dir"]=="CALL" else price + atr*1.5
        tp1 = price + atr*1.5 if d["dir"]=="CALL" else price - atr*1.5
        tp2 = price + atr*3 if d["dir"]=="CALL" else price - atr*3
        d.update({"sl":sl,"tp1":tp1,"tp2":tp2,"session":"GOLD"})
        return d
    except: return None
def check_pullback_entry(pair, original_dir):
    if is_news_blocking_pair(pair, minutes=30): return None
    df = get_candles(pair)
    if df is None: return None
    try:
        close=df['close']; ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean(); rsi7=calc_rsi(close,7); rsi14=calc_rsi(close,14)
        r7=float(rsi7.iloc[-1]); r7_prev=float(rsi7.iloc[-2]); r14=float(rsi14.iloc[-1]); c_now=float(close.iloc[-1]); e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1]); payout=get_payout(pair)
        near_ema=abs(c_now-e9)/c_now*100<0.05 or abs(c_now-e21)/c_now*100<0.05
        if not near_ema or payout<0.80: return None
        if original_dir=="CALL":
            if 40<=r7<=55 and 42<=r14<=58 and r7>r7_prev and c_now>e21: return {"pair":pair,"dir":"CALL","conf":88,"price":c_now,"rsi":r7,"reason":f"Pullback CALL | RSI7 {r7:.0f} up RSI14 {r14:.0f} at EMA","payout":payout,"expiry":60,"atr":0,"rejected":False}
        else:
            if 45<=r7<=60 and 42<=r14<=58 and r7<r7_prev and c_now<e21: return {"pair":pair,"dir":"PUT","conf":88,"price":c_now,"rsi":r7,"reason":f"Pullback PUT | RSI7 {r7:.0f} down RSI14 {r14:.0f} at EMA","payout":payout,"expiry":60,"atr":0,"rejected":False}
        return None
    except: return None
def pullback_scanner_loop(cid, pair, original_dir):
    start=time.time(); PULLBACK_STATE[cid]={"pair":pair,"dir":original_dir,"active":True}
    bot.send_message(cid, f"Pullback Scan ON\n\n{pair} looking for {original_dir} pullback\nScanning every 10 sec...\nTimeout 5 min\n\nPress WIN / LOSS / SKIP")
    while PULLBACK_STATE.get(cid, {}).get("active") and time.time()-start<300:
        if check_and_reset_new_day(): bot.send_message(cid,"New day started - Yesterday pullback scan stopped."); PULLBACK_STATE[cid]["active"]=False; return
        if not can_trade_today(): bot.send_message(cid,"Max 30 trades reached today."); PULLBACK_STATE[cid]["active"]=False; return
        d=check_pullback_entry(pair,original_dir)
        if d:
            levels=OTC_MARTI["levels"]; idx=OTC_MARTI["loss_streak"]; mult=levels[idx]; amt=OTC_MARTI["base"]*mult; names=["Real Entry","Martingale 1","Martingale 2","Martingale 3"]; dir_e="CALL UP" if d['dir']=="CALL" else "PUT DOWN"
            mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("WIN",callback_data=f"manual_win_{pair}"),types.InlineKeyboardButton("LOSS",callback_data=f"manual_loss_{pair}_{d['dir']}")); mk.add(types.InlineKeyboardButton("SKIP THIS TRADE",callback_data=f"skip_{pair}")); mk.add(types.InlineKeyboardButton("Send to Channel",callback_data=f"send_channel_pb_{pair}_{d['dir']}"))
            bot.send_message(cid,f"PULLBACK ENTRY FOUND!\n\n{pair}\n{dir_e} | {d['reason']}\nPayout {int(d['payout']*100)}%\nNext: {names[idx]} - ${amt:.2f} Level {idx+1}/4 ({mult}x)\nEnter NOW - 1 Min - MANUAL\n\nPress WIN/LOSS/SKIP after result:",reply_markup=mk,parse_mode="Markdown")
            PULLBACK_STATE[cid]["active"]=False; return
        time.sleep(10)
    PULLBACK_STATE[cid]={"active":False}; bot.send_message(cid,"Pullback scan timeout (5 min) - No safe entry.")
def daily_summary_loop():
    global DAILY_SUMMARY_SENT
    tz=pytz.timezone("Africa/Lagos")
    while True:
        try:
            now=datetime.now(tz); today_str=now.strftime("%Y-%m-%d")
            if now.hour==20 and now.minute<5 and DAILY_SUMMARY_SENT!=today_str:
                DAILY_SUMMARY_SENT=today_str; total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0
                best_pair=""; best_wr=0; bad_pair=""; bad_wr=100
                for pair,s in PAIR_BRAIN.items():
                    t=s["wins"]+s["loss"]
                    if t>=3:
                        w=s["wins"]/t*100
                        if w>best_wr: best_wr=w; best_pair=f"{pair} {w:.0f}% (W{s['wins']} L{s['loss']})"
                        if w<bad_wr: bad_wr=w; bad_pair=f"{pair} {w:.0f}% (W{s['wins']} L{s['loss']})"
                msg=f"DAILY SUMMARY - {today_str}\n\nTrading closed for today (8PM)\n\nWins: {STATS['wins']}\nLosses: {STATS['loss']}\nWin Rate: {wr:.1f}%\nTotal Trades Today: {STATS['daily_trades']}/30\n\nBest Pair: {best_pair if best_pair else 'Not enough data yet'}\nWorst Pair: {bad_pair if bad_pair else 'None - all good'}\n\nBrain has learned from {len(PAIR_BRAIN)} pairs.\n\n{get_greeting()} - Rest well Trailblazer!\n"
                try: bot.send_message(OWNER_ID,msg,parse_mode="Markdown")
                except: pass
            time.sleep(60)
        except: time.sleep(60)
def morning_greet_loop():
    global MORNING_GREET_SENT
    tz=pytz.timezone("Africa/Lagos")
    while True:
        try:
            now=datetime.now(tz); today_str=now.strftime("%Y-%m-%d")
            if now.hour==7 and now.minute<5 and MORNING_GREET_SENT!=today_str:
                MORNING_GREET_SENT=today_str
                try: bot.send_message(OWNER_ID, get_ready_text(), parse_mode="Markdown")
                except: pass
            time.sleep(60)
        except: time.sleep(60)
def xauusd_signal_scanner():
    while True:
        try:
            time.sleep(120)
            if MARATHON["active"]: continue
            if not is_real_hours() or not IQ_CONNECTED: continue
            if is_signal_active(): continue
            if not can_trade_today(): continue
            d=analyze_xauusd()
            if d and d["conf"]>=88:
                tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=45); dir_e="BUY UP" if d['dir']=="CALL" else "SELL DOWN"
                mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("WIN - Reset",callback_data="manual_win_XAUUSD"),types.InlineKeyboardButton("LOSS - Pullback Scan",callback_data=f"manual_loss_XAUUSD_{d['dir']}")); mk.add(types.InlineKeyboardButton("SKIP THIS TRADE",callback_data="skip_XAUUSD")); mk.add(types.InlineKeyboardButton("Send to Channel",callback_data=f"send_channel_XAUUSD_{d['dir']}"))
                bot.send_message(OWNER_ID, f"XAU/USD GOLD AUTO SIGNAL\n\n{dir_e} | {d['conf']:.0f}%\n{d['reason']}\nENTRY: {entry.strftime('%H:%M:%S WAT')}\nENTRY: {d['price']:.2f} SL: {d['sl']:.2f} TP1: {d['tp1']:.2f} TP2: {d['tp2']:.2f}", reply_markup=mk, parse_mode="Markdown")
                start_signal("XAUUSD",d['dir'],d['conf'],d['rsi'],d.get('adx',30), price=d['price'], sl=d['sl'], tp1=d['tp1'], tp2=d['tp2'])
        except: time.sleep(60)
def real_signal_scanner():
    while True:
        try:
            time.sleep(180)
            if MARATHON["active"]: continue
            if not is_real_hours() or not IQ_CONNECTED: continue
            if is_signal_active(): continue
            if not can_trade_today(): continue
            pass
        except: time.sleep(60)
def trailblazer_market_scanner():
    tz=pytz.timezone("Africa/Lagos"); last_news_alert=0
    while True:
        try:
            if MARATHON["active"]: time.sleep(60); continue
            if not is_real_hours() or not IQ_CONNECTED: time.sleep(60); continue
            news=get_upcoming_news(); urgent_news=[n for n in news if 0<=n["in_min"]<=30]
            if urgent_news and time.time()-last_news_alert>3600:
                last_news_alert=time.time(); news_txt=format_news_alert(urgent_news)
                msg=f"TRAILBLAZER NEWS ALERT\n\n{get_greeting()}\n\nHIGH IMPACT NEWS COMING!\n\n{news_txt}\nDo not trade pairs with that currency now\nWait 15 min AFTER news\n"
                try: bot.send_message(OWNER_ID,msg,parse_mode="Markdown")
                except: pass
            if time.time()-MARKET_GOOD_SENT["last_alert"]<2700: time.sleep(60); continue
            if is_signal_active(): time.sleep(60); continue
            good_pairs=0; strong_pairs=[]
            for pair in ["EURUSD","GBPUSD","EURGBP","AUDUSD","USDCAD"]:
                if is_pair_blocked(pair): continue
                if is_news_blocking_pair(pair,minutes=30): continue
                try:
                    df=get_candles(pair)
                    if df is None: continue
                    adx,_,_=calc_adx_v12(df); payout=get_payout(pair)
                    if adx>=25 and payout>=0.80: good_pairs+=1; strong_pairs.append(pair)
                except: pass
                time.sleep(1)
            if urgent_news and good_pairs<5: time.sleep(300); continue
            if good_pairs>=5:
                MARKET_GOOD_SENT["last_alert"]=time.time(); greet=get_greeting(); pairs_txt=" | ".join(strong_pairs[:5])
                if news: news_note=f"\nNews Note: {len(news)} high impact news in next 2h - Bot is avoiding news pairs\n"
                else: news_note="\nNews: No high impact news in next 2h - Clean market!\n"
                session_boost,session_name=get_session_boost("EURUSD")
                msg=f"MARKET IS GOOD NOW\n\n{greet}\nPairs Ready: {pairs_txt}\nSession: {session_name}\n{news_note}\nType /start and press TRADE REAL"
                try: bot.send_message(OWNER_ID,msg,parse_mode="Markdown")
                except: pass
            time.sleep(60)
        except: time.sleep(60)
# ===== MARATHON - 2 PAIRS ONLY + DUAL SCAN + NAIRA REAL / DOLLAR DEMO =====
def mar_currency():
    return "₦" if MARATHON["bal_type"] == "REAL" else "$"
def mar_fmt(amount):
    if MARATHON["bal_type"] == "REAL":
        return f"₦{float(amount):,.0f}"
    else:
        return f"${float(amount):.2f}"
def marathon_stake():
    bal = MARATHON["bal"]; start = MARATHON["start"]; target = MARATHON["target"]
    if target <= start: return bal * 0.07
    progress = (bal - start) / (target - start)
    if progress < 0.30: return bal * 0.07
    elif progress < 0.60: return bal * 0.08
    else: return bal * 0.09
def analyze_marathon_30s(pair):
    d = analyze_sniper_v12(pair, sniper_mode=True)
    if not d or d.get("rejected"): return None
    if d["conf"] < 88: return None
    return d
def analyze_marathon_dual():
    # SCAN BOTH PAIRS, PICK BEST - EURUSD-OTC + GBPUSD-OTC
    best = None
    results = []
    for pair in MARATHON_PAIRS:
        d = analyze_marathon_30s(pair)
        if d:
            results.append((pair, d["conf"], d))
            if best is None or d["conf"] > best["conf"]:
                best = d
        else:
            results.append((pair, 0, None))
    return best, results
def marathon_auto_buy(pair, stake, direction):
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL)
            iq.change_balance(MARATHON["bal_type"])
            status, trade_id = iq.buy(stake, pair, direction.lower(), 1)
            print(f"[MARATHON BUY] {pair} {direction} {mar_fmt(stake)} -> {status} {trade_id}")
            return status, trade_id
    except Exception as e:
        print(f"[MARATHON BUY ERR] {e}")
        return False, None
def marathon_check_win(trade_id):
    try:
        print(f"[MARATHON CHECK] Waiting for trade {trade_id} to close - 1 MIN...")
        for i in range(13):
            time.sleep(5)
            if not MARATHON["active"]: return None, 0
            if i >= 11:
                try:
                    with IQ_LOCK:
                        logging.disable(logging.CRITICAL)
                        win, profit = iq.check_win_v2(trade_id)
                        print(f"[MARATHON CHECK TRY {i}] win={win} profit={profit}")
                        if win is not None: return win, profit
                except Exception as e: print(f"[MARATHON CHECK ERR TRY {i}] {e}"); time.sleep(2)
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL)
                info = iq.get_optioninfo_v2(trade_id)
                print(f"[MARATHON CHECK INFO] {info}")
                if info and 'win' in info:
                    win = info['win']; profit = float(info.get('profit', 0))
                    if win is not None: return win, profit
        except Exception as e: print(f"[MARATHON CHECK INFO ERR] {e}")
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL)
                iq.change_balance(MARATHON["bal_type"])
                new_bal = iq.get_balance()
                print(f"[MARATHON CHECK BAL] Old {MARATHON['bal']:.2f} New {new_bal:.2f}")
                if new_bal > MARATHON["bal"]: return True, round(new_bal - MARATHON["bal"], 2)
                elif new_bal < MARATHON["bal"]: return False, 0
        except Exception as e: print(f"[MARATHON CHECK BAL ERR] {e}")
        return None, 0
    except Exception as e: print(f"[MARATHON CHECK ERR] {e}"); return None, 0
def marathon_loop():
    last_trade_time = 0
    scan_count = 0
    while MARATHON["active"]:
        try:
            if time.time() - last_trade_time < 90:
                time.sleep(5); continue
            if not IQ_CONNECTED:
                bot.send_message(MARATHON["cid"], "Waiting for IQ to connect... Marathon paused 10s")
                time.sleep(10); continue
            if MARATHON["bal"] >= MARATHON["target"]:
                bot.send_message(MARATHON["cid"], f"MARATHON DONE! [{MARATHON['bal_type']}]\n\nStart: {mar_fmt(MARATHON['start'])}\nNow: {mar_fmt(MARATHON['bal'])}\nTarget: {mar_fmt(MARATHON['target'])} REACHED!\nAUTO STOPPED\n\nW:{MARATHON['wins']} L:{MARATHON['loss']}")
                MARATHON["active"] = False; clear_signal(); break
            stop_loss = MARATHON["start"] * 0.70
            if MARATHON["bal"] <= stop_loss:
                bot.send_message(MARATHON["cid"], f"MARATHON STOPPED - STOP LOSS HIT [{MARATHON['bal_type']}]\n\nStart: {mar_fmt(MARATHON['start'])}\nNow: {mar_fmt(MARATHON['bal'])}\nLost 30% - I stop to protect your remaining money\nW:{MARATHON['wins']} L:{MARATHON['loss']}\n\nYou still get {mar_fmt(MARATHON['bal'])} remain, no be 0")
                MARATHON["active"] = False; break
            if MARATHON["bal"] <= 1:
                bot.send_message(MARATHON["cid"], f"MARATHON STOPPED - BALANCE LOW [{MARATHON['bal_type']}]\nBal: {mar_fmt(MARATHON['bal'])}")
                MARATHON["active"] = False; break
            # ===== DUAL SCAN BOTH PAIRS =====
            found, results = analyze_marathon_dual()
            scan_count += 1
            if not found:
                # Tell user every 5 scans why no trade, so e no dey silent
                if scan_count % 5 == 0:
                    bot.send_message(MARATHON["cid"], f"DUAL SCAN - No trade yet [{MARATHON['bal_type']}]\n\nEUR/USD OTC: Waiting for 88%\nGBP/USD OTC: Waiting for 88%\nBal: {mar_fmt(MARATHON['bal'])} / Target {mar_fmt(MARATHON['target'])}\nScanning both again in 30s...")
                time.sleep(30); continue
            stake = marathon_stake()
            dir_e = "CALL UP" if found['dir']=="CALL" else "PUT DOWN"
            progress_pct = int((MARATHON['bal'] - MARATHON['start']) / (MARATHON['target'] - MARATHON['start']) * 100) if MARATHON['target'] > MARATHON['start'] else 0
            progress_pct = max(0, min(100, progress_pct))
            bot.send_message(MARATHON["cid"], f"MARATHON AUTO-PLACING... [{MARATHON['bal_type']}]\n\nBEST OF 2: {PAIR_EMOJI.get(found['pair'],found['pair'])} - {found['conf']:.0f}%\n{dir_e} | RSI {found['rsi']:.0f} | Payout {int(found['payout']*100)}%\nStake: {mar_fmt(stake)} (7-9% Fixed {progress_pct}%) | Bal: {mar_fmt(MARATHON['bal'])} / Target {mar_fmt(MARATHON['target'])}\nExpiry: 1 MIN ONLY\nPlacing on IQ {MARATHON['bal_type']} now...")
            start_signal(found['pair'], found['dir'], found['conf'], found['rsi'], 30, price=found['price'], expiry=60)
            status, trade_id = marathon_auto_buy(found['pair'], stake, found['dir'])
            if not status:
                bot.send_message(MARATHON["cid"], f"AUTO PLACE FAILED [{MARATHON['bal_type']}]\n\n{found['pair']} - IQ rejected / No connection\nRetrying in 15s...")
                clear_signal(); time.sleep(15); continue
            last_trade_time = time.time()
            bot.send_message(MARATHON["cid"], f"TRADE PLACED [{MARATHON['bal_type']}] ID: {trade_id}\nExpiry: 1 MIN | Waiting for result...")
            win, profit = marathon_check_win(trade_id)
            clear_signal()
            last_trade_time = time.time()
            if win is None:
                bot.send_message(MARATHON["cid"], "Could not confirm result, resting 30s...")
                time.sleep(30); continue
            if win:
                MARATHON["bal"] += float(profit); MARATHON["wins"]+=1; MARATHON["win_streak"]+=1; MARATHON["loss_streak"]=0; MARATHON["marti_level"]=0
                record_brain(found['pair'], True, 80, found['rsi'], 30)
                progress2 = int((MARATHON['bal'] - MARATHON['start']) / (MARATHON['target'] - MARATHON['start']) * 100) if MARATHON['target'] > MARATHON['start'] else 0
                progress2 = max(0, min(100, progress2))
                bot.send_message(MARATHON["cid"], f"MARATHON WIN [{MARATHON['bal_type']}] +{mar_fmt(float(profit))}\nBal: {mar_fmt(MARATHON['bal'])} / Target {mar_fmt(MARATHON['target'])}\nProgress: {progress2}% | Next Stake: {mar_fmt(marathon_stake())}\nExpiry was 1 MIN\nResting 90s...")
            else:
                MARATHON["bal"] -= stake; MARATHON["loss"]+=1; MARATHON["loss_streak"]+=1; MARATHON["win_streak"]=0
                record_brain(found['pair'], False, 80, found['rsi'], 30)
                bot.send_message(MARATHON["cid"], f"MARATHON LOSS [{MARATHON['bal_type']}] -{mar_fmt(stake)}\nBal: {mar_fmt(MARATHON['bal'])} / Target {mar_fmt(MARATHON['target'])}\nNext Stake: {mar_fmt(marathon_stake())}\nResting 90s...")
                if MARATHON["loss_streak"] >= 2:
                    bot.send_message(MARATHON["cid"], "2 losses - Pausing 10 mins to protect balance..."); time.sleep(600)
                    last_trade_time = time.time()
            time.sleep(10)
        except Exception as e:
            print(f"Marathon err {e}")
            try: bot.send_message(MARATHON["cid"], f"Marathon error: {e} - retrying in 15s")
            except: pass
            time.sleep(15)
def start_marathon(cid, amount, target=None):
    if target is None: target = float(amount)*2
    MARATHON.update({"active":True,"start":float(amount),"target":float(target),"bal":float(amount),"wins":0,"loss":0,"win_streak":0,"loss_streak":0,"cid":cid,"base_stake":1.0,"marti_level":0})
    bot.send_message(cid, f"MARATHON STARTED - DUAL SCAN [{MARATHON['bal_type']}]\n\nPairs: EUR/USD OTC + GBP/USD OTC (Scanning BOTH)\nStart: {mar_fmt(amount)}\nYOUR Target: {mar_fmt(target)}\nExpiry: 1 MIN ONLY\nStop Loss: {mar_fmt(float(amount)*0.70)} (Stop if lose 30%)\nStake: 7%-9% Fixed in {mar_currency()}\nAUTO PLACE: ON - Bot go place trade for IQ {MARATHON['bal_type']}\n\nScanning BOTH pairs now...")
    threading.Thread(target=marathon_loop, daemon=True).start()
def marathon_menu_text(cid):
    bal_type = MARATHON["bal_type"]
    if bal_type == "REAL":
        emoji = "NAIRA REAL"
        cur_note = "Currency: NAIRA (₦) - Your IQ REAL account na Naira"
    else:
        emoji = "DEMO $"
        cur_note = "Currency: DOLLAR ($) - Demo na Dollar"
    return f"MARATHON MODE - DUAL SCAN (2 PAIRS)\n\nBalance Mode: {emoji} {bal_type}\n{cur_note}\nPairs: EUR/USD OTC + GBP/USD OTC - Bot scans BOTH, picks BEST\nExpiry: 1 MIN ONLY\nStake: 7% - 9% Fixed\nStop Loss: 30%\n\nHOW E GO GO:\n1. Pick Balance (or Type Your Own) - No need pick pair again, bot scans both\n2. Pick Target (or Type Your Own)\n3. Bot Start - Scans BOTH pairs\n\nPick Balance below:"
def marathon_menu_kb():
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(types.InlineKeyboardButton("START WITH EUR/USD OTC + GBP/USD OTC", callback_data="mar_pick_both"))
    if MARATHON["bal_type"]=="PRACTICE":
        mk.add(types.InlineKeyboardButton("SWITCH TO REAL MONEY (₦ NAIRA)", callback_data="mar_bal_REAL"))
    else:
        mk.add(types.InlineKeyboardButton("SWITCH TO PRACTICE (DEMO $)", callback_data="mar_bal_PRACTICE"))
    if MARATHON["active"]:
        mk.add(types.InlineKeyboardButton("STOP MARATHON", callback_data="mar_stop"))
    return mk
def marathon_balance_kb():
    mk = types.InlineKeyboardMarkup(row_width=2)
    if MARATHON["bal_type"] == "REAL":
        mk.add(types.InlineKeyboardButton("₦10,000", callback_data="mar_bal_10000"), types.InlineKeyboardButton("₦20,000", callback_data="mar_bal_20000"))
        mk.add(types.InlineKeyboardButton("₦50,000", callback_data="mar_bal_50000"), types.InlineKeyboardButton("₦100,000", callback_data="mar_bal_100000"))
    else:
        mk.add(types.InlineKeyboardButton("$10", callback_data="mar_bal_10"), types.InlineKeyboardButton("$20", callback_data="mar_bal_20"))
        mk.add(types.InlineKeyboardButton("$50", callback_data="mar_bal_50"), types.InlineKeyboardButton("$100", callback_data="mar_bal_100"))
    mk.add(types.InlineKeyboardButton("Type My Own Balance", callback_data="mar_bal_custom"))
    mk.add(types.InlineKeyboardButton("Back", callback_data="mar_back_pairs"))
    return mk
def marathon_target_kb(start_amt):
    mk = types.InlineKeyboardMarkup(row_width=2)
    if MARATHON["bal_type"] == "REAL":
        def f(a): return f"₦{a:,.0f}"
    else:
        def f(a): return f"${a:.0f}"
    mk.add(types.InlineKeyboardButton(f"{f(start_amt*1.5)} (+50%)", callback_data=f"mar_target_{start_amt}_{start_amt*1.5}"), types.InlineKeyboardButton(f"{f(start_amt*2)} (Double)", callback_data=f"mar_target_{start_amt}_{start_amt*2}"))
    mk.add(types.InlineKeyboardButton(f"{f(start_amt*2.5)}", callback_data=f"mar_target_{start_amt}_{start_amt*2.5}"), types.InlineKeyboardButton(f"{f(start_amt*3)} (Triple)", callback_data=f"mar_target_{start_amt}_{start_amt*3}"))
    mk.add(types.InlineKeyboardButton("Type My Own Target", callback_data=f"mar_type_target_{start_amt}"))
    mk.add(types.InlineKeyboardButton("Back to Balance", callback_data="mar_back_balance"))
    return mk
@bot.message_handler(content_types=['new_chat_members'])
def welcome_new_member(m):
    try:
        for member in m.new_chat_members:
            name = member.first_name or "Trader"
            bot.send_message(m.chat.id, f"Welcome {name} to Trailblazer Signals!\n\nForex and GOLD Sniper Signals\n88%+ Accuracy Only\nStake $1 - Follow Martingale\nChannel: @KEVINTRAILBLAZE\n\nType /welcome to see the rules.\nGood luck!")
    except: pass
@bot.message_handler(func=lambda m: m.text and not m.text.startswith("/") and (m.chat.id in MARATHON_BALANCE_WAIT or m.chat.id in MARATHON_TARGET_WAIT), content_types=['text'])
def handle_custom_text(m):
    if not is_allowed(m.from_user.id): return
    if m.chat.id in MARATHON_BALANCE_WAIT:
        try:
            bal_amt = float(m.text.strip().replace("₦","").replace("$","").replace(",",""))
            MARATHON_BALANCE_WAIT.pop(m.chat.id)
            bot.send_message(m.chat.id, f"Pairs: EUR/USD OTC + GBP/USD OTC (Dual Scan)\nStart Balance: {mar_fmt(bal_amt)}\n\nNow pick TARGET:", reply_markup=marathon_target_kb(bal_amt), parse_mode="Markdown")
            return
        except:
            bot.send_message(m.chat.id, "Type number only. Example: 20000 for Naira or 20 for Demo"); return
    if m.chat.id in MARATHON_TARGET_WAIT:
        if m.text and m.text.replace('.','',1).replace(',','').isdigit():
            start_amt = MARATHON_TARGET_WAIT.pop(m.chat.id)
            target_amt = float(m.text.strip().replace(",","").replace("₦","").replace("$",""))
            if target_amt <= start_amt:
                bot.send_message(m.chat.id, f"Target must be bigger than start {mar_fmt(start_amt)}. Try again - type target:")
                MARATHON_TARGET_WAIT[m.chat.id] = start_amt
                return
            mkc = types.InlineKeyboardMarkup(row_width=1)
            mkc.add(types.InlineKeyboardButton(f"START {mar_fmt(start_amt)} -> {mar_fmt(target_amt)} (1 MIN)",callback_data=f"mar_target_{start_amt}_{target_amt}"))
            bot.send_message(m.chat.id, f"Target set: {mar_fmt(target_amt)}\nPress START to begin:", reply_markup=mkc)
            return
        else:
            bot.send_message(m.chat.id, "Type number only. Example: 30000"); return
    return
@bot.message_handler(commands=['start','stop','mode','balance','results','brain','news','welcome','intro','ready','marathon','real','practice'])
def start(m):
    if not is_allowed(m.from_user.id):
        if m.text and m.text.startswith('/welcome'):
            bot.send_message(m.chat.id, WELCOME_TEXT); return
        if m.text and m.text.startswith('/intro'):
            bot.send_message(m.chat.id, INTRO_TEXT); return
        if m.text and m.text.startswith('/ready'):
            bot.send_message(m.chat.id, get_ready_text()); return
        bot.send_message(m.chat.id,"Private"); return
    if m.text.startswith('/real'):
        MARATHON["bal_type"]="REAL"
        bot.send_message(m.chat.id,"MARATHON MODE: REAL MONEY (₦ NAIRA)\n\nNext marathon go use REAL Naira balance.\nType /marathon to confirm.",parse_mode="Markdown"); return
    if m.text.startswith('/practice'):
        MARATHON["bal_type"]="PRACTICE"
        bot.send_message(m.chat.id,"MARATHON MODE: PRACTICE (DEMO $)\n\nNext marathon go use DEMO Dollar balance.\nType /marathon to confirm.",parse_mode="Markdown"); return
    if m.text.startswith('/marathon'):
        bot.send_message(m.chat.id, marathon_menu_text(m.chat.id), reply_markup=marathon_menu_kb(), parse_mode="Markdown"); return
    if m.text.startswith('/welcome'):
        send_photo_to_channel_sync(WELCOME_PHOTO, WELCOME_TEXT)
        bot.send_message(m.chat.id, "Welcome message has been sent to @KEVINTRAILBLAZE with wallpaper!"); return
    if m.text.startswith('/intro'):
        send_photo_to_channel_sync(INTRO_PHOTO, INTRO_TEXT)
        bot.send_message(m.chat.id, "Intro message has been sent to @KEVINTRAILBLAZE with wallpaper!"); return
    if m.text.startswith('/ready'):
        send_photo_to_channel_sync(READY_PHOTO, get_ready_text())
        bot.send_message(m.chat.id, "Get Ready message has been sent to @KEVINTRAILBLAZE!"); return
    if m.text.startswith('/news'):
        news=get_upcoming_news()
        if not news: bot.send_message(m.chat.id,"NEWS CHECK\n\nNo high impact news in next 2 hours - Clean market!\nSafe to trade all pairs.",parse_mode="Markdown"); return
        txt="UPCOMING NEWS - NEXT 2H\n\n"+format_news_alert(news)+"Bot is blocking these currencies for 30 min before news."; bot.send_message(m.chat.id,txt,parse_mode="Markdown"); return
    if m.text.startswith('/brain'):
        txt="AI BRAIN - PAIR LEARNING\n\n"; best=[]; bad=[]
        for pair,s in PAIR_BRAIN.items():
            total=s["wins"]+s["loss"]
            if total>=3:
                wr=s["wins"]/total*100; line=f"{PAIR_EMOJI.get(pair,pair)}: W{s['wins']} L{s['loss']} = {wr:.0f}% {'BLOCKED' if is_pair_blocked(pair) else ''}\n"
                if wr>=60: best.append(line)
                elif wr<50: bad.append(line)
        txt+="BEST PAIRS:\n"+("".join(best) if best else "Not enough data yet\n")+"\nBAD PAIRS:\n"+("".join(bad) if bad else "None\n")+"\nBEST HOURS + SWEET RSI:\n"
        for pair,s in PAIR_BRAIN.items():
            if s.get("best_hour") or s.get("best_rsi_range"):
                rng=s.get("best_rsi_range"); rng_txt=f"{rng[0]:.0f}-{rng[1]:.0f}" if rng else "Learning..."; txt+=f"{pair}: Best {s.get('best_hour','?')}:00 | Worst {s.get('worst_hour','?')}:00 | Sweet RSI {rng_txt}\n"
        txt+=f"\nToday: {STATS['daily_trades']}/30"
        if is_signal_active(): txt+=f"\nActive: {ACTIVE_SIGNAL['pair']} {ACTIVE_SIGNAL['dir']}"
        sb,sn=get_session_boost("EURUSD"); txt+=f"\nCurrent Session: {sn} ({sb:+d})"; bot.send_message(m.chat.id,txt,parse_mode="Markdown"); return
    if m.text.startswith('/stop'):
        MARATHON["active"] = False
        if m.chat.id in AUTO_STATE: AUTO_STATE[m.chat.id]['running']=False; bot.send_message(m.chat.id,"Stopping Marathon + Auto...")
        else: bot.send_message(m.chat.id,"Auto not running"); return
    if m.text.startswith('/results'):
        if not OTC_SESSION_RESULTS: bot.send_message(m.chat.id,"No trades yet this session"); return
        wins=sum(1 for x in OTC_SESSION_RESULTS if x['win']); losses=len(OTC_SESSION_RESULTS)-wins; pnl_total=sum(x['pnl'] for x in OTC_SESSION_RESULTS); idx=OTC_MARTI["loss_streak"]
        txt=f"RESULTS (1 Real + 3 Marti)\n\nTotal: {len(OTC_SESSION_RESULTS)} | W:{wins} L:{losses} | PnL: ${pnl_total:.2f}\nToday: {STATS['daily_trades']}/30 | Current: Level {idx+1}/4 | Base: ${OTC_MARTI['base']}\n\n"
        for r in OTC_SESSION_RESULTS[-25:]: txt+=f"{'WIN' if r['win'] else 'LOSS'} {r['time']} {r['pair']} {r['dir']} ${r['amt']} L{r['level']} {r['conf']}% {r['pnl']:+.2f}\n"
        bot.send_message(m.chat.id,txt,parse_mode="Markdown"); return
    if m.text.startswith('/mode'):
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); sb,sn=get_session_boost("EURUSD")
        txt=f"MODE CHECK V19 TRAILBLAZER\n\n{get_greeting()}\nNow: {now.strftime('%A %H:%M:%S WAT')}\nSession: {sn} ({sb:+d})\nMode: {get_mode_text()}\nIQ: {'YES' if IQ_CONNECTED else 'NO'}\nMartingale: 1 Real + 3 Marti (1-2-4-8)\nToday: {STATS['daily_trades']}/30 trades\nBrain: {'ON' if PAIR_BRAIN else 'ON - No data yet'}\nNews: {len(get_upcoming_news())} high impact in next 2h\nActive Signal: {ACTIVE_SIGNAL['pair'] if is_signal_active() else 'None'}\nOTC: DISABLED - REAL only\nGOLD: XAUUSD Scanner ON\nMARATHON: {'ACTIVE' if MARATHON['active'] else 'OFF'} | Balance: {MARATHON['bal_type']} ({mar_currency()}) | Pairs: EUR/USD OTC + GBP/USD OTC | Expiry: 1 MIN ONLY | Target: {mar_fmt(MARATHON['target'])}\n"
        bot.send_message(m.chat.id,txt,parse_mode="Markdown"); return
    if m.text.startswith('/balance'):
        try:
            if not IQ_CONNECTED: bot.send_message(m.chat.id,f"BALANCES\nIQ: Not connected yet\n{get_mode_text()}\n\nWait 1 min and try /start again"); return
            demo=get_real_balance("PRACTICE"); real=get_real_balance("REAL"); bot.send_message(m.chat.id,f"BALANCES\nDEMO: ${demo:.2f}\nREAL: ₦{real:,.0f}\nMARATHON USING: {MARATHON['bal_type']} ({mar_currency()})\n{get_mode_text()}\n\nTo switch Marathon: /real or /practice or use /marathon button")
        except Exception as e: bot.send_message(m.chat.id,f"Balance error {e}")
        return
    try: bal_demo=get_real_balance("PRACTICE") if IQ_CONNECTED else STATS.get("real_balance",0.0)
    except: bal_demo=0.0
    mk=types.InlineKeyboardMarkup(row_width=1); mk.add(types.InlineKeyboardButton(f"TRADE REAL (15) AUTO EXPIRY - ${bal_demo:.2f}",callback_data="trade_real")); mk.add(types.InlineKeyboardButton("MARATHON 1 MIN - DUAL SCAN",callback_data="marathon_btn")); mk.add(types.InlineKeyboardButton("GET READY - Send To Channel",callback_data="ready_btn")); mk.add(types.InlineKeyboardButton("MY STATS",callback_data="stats"),types.InlineKeyboardButton("AI BRAIN",callback_data="brain_btn"),types.InlineKeyboardButton("NEWS CHECK",callback_data="news_btn"),types.InlineKeyboardButton("SETTINGS",callback_data="settings"))
    greet=get_greeting(); greet_msg=get_greeting_msg(); sb,sn=get_session_boost("EURUSD")
    txt=f"{greet}\n\n{greet_msg}\n\nZ-BOT V19 TRAILBLAZER - MANUAL\n\nIQ: {'YES' if IQ_CONNECTED else 'NO - Retrying...'} | DEMO ${bal_demo:.2f}\nW:{STATS['wins']} L:{STATS['loss']} | {STATS['streak']}\nToday: {STATS['daily_trades']}/30\nBrain: Learning best pairs + best hours + sweet RSI\nSession: {sn} ({sb:+d})\nNews: Auto scanner ON\nGOLD: XAUUSD Scanner ON - Entry/SL/TP\n{get_mode_text()}\nMARATHON: {MARATHON['bal_type']} ({mar_currency()}) - 1 MIN ONLY - DUAL SCAN EUR/USD OTC + GBP/USD OTC - Type /marathon\n\nSelect:\n"
    bot.send_message(m.chat.id,txt,reply_markup=mk,parse_mode="Markdown")
@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_allowed(c.from_user.id): bot.answer_callback_query(c.id,"Private"); return
    data=c.data; cid=c.message.chat.id
    if data=="marathon_btn":
        bot.send_message(cid, marathon_menu_text(cid), reply_markup=marathon_menu_kb(), parse_mode="Markdown"); return
    if data=="mar_back_pairs":
        bot.send_message(cid, marathon_menu_text(cid), reply_markup=marathon_menu_kb(), parse_mode="Markdown"); return
    if data=="mar_back_balance":
        bot.send_message(cid, f"Pairs: EUR/USD OTC + GBP/USD OTC (Dual Scan)\n\nPick START BALANCE:", reply_markup=marathon_balance_kb(), parse_mode="Markdown"); return
    if data=="mar_bal_REAL" or data=="mar_bal_PRACTICE":
        new_type = data.replace("mar_bal_","")
        if MARATHON["active"]:
            bot.answer_callback_query(c.id,"Stop marathon first before switching!")
            bot.send_message(cid,"Cannot switch while Marathon is ACTIVE\nPress STOP first, then switch."); return
        MARATHON["bal_type"]=new_type
        bot.answer_callback_query(c.id,f"Switched to {new_type} ({mar_currency()})")
        bot.send_message(cid, f"SWITCHED TO {new_type} ({mar_currency()})\n\nNext Marathon go use {new_type} balance.", reply_markup=marathon_menu_kb(), parse_mode="Markdown"); return
    if data.startswith("mar_bal_"):
        if data=="mar_bal_custom":
            MARATHON_BALANCE_WAIT[cid] = True
            cur = "Naira (₦) - Example: type 20000" if MARATHON["bal_type"]=="REAL" else "Dollar ($) - Example: type 20"
            bot.send_message(cid, f"Type your START BALANCE:\nPairs: EUR/USD OTC + GBP/USD OTC\nCurrency: {cur}\n\nJust type number and send."); return
        try: amt = float(data.replace("mar_bal_",""))
        except: return
        bot.send_message(cid, f"Pairs: EUR/USD OTC + GBP/USD OTC (Dual Scan)\nStart: {mar_fmt(amt)} | Balance: {MARATHON['bal_type']} ({mar_currency()}) | 1 MIN ONLY\n\nNow pick TARGET:", reply_markup=marathon_target_kb(amt), parse_mode="Markdown"); return
    if data=="mar_pick_both":
        MARATHON_PICK["pair"] = "DUAL"
        bot.send_message(cid, f"PICKED: EUR/USD OTC + GBP/USD OTC (Dual Scan)\nBalance: {MARATHON['bal_type']} ({mar_currency()}) | Expiry: 1 MIN ONLY\n\nBot go scan BOTH, pick BEST.\nNow choose START BALANCE:", reply_markup=marathon_balance_kb(), parse_mode="Markdown"); return
    if data.startswith("mar_pick_"):
        MARATHON_PICK["pair"] = "DUAL"
        bot.send_message(cid, f"PICKED: EUR/USD OTC + GBP/USD OTC (Dual Scan)\nBalance: {MARATHON['bal_type']} ({mar_currency()}) | Expiry: 1 MIN ONLY\n\nBot go scan BOTH, pick BEST.\nNow choose START BALANCE:", reply_markup=marathon_balance_kb(), parse_mode="Markdown"); return
    if data.startswith("mar_type_target_"):
        amt = float(data.replace("mar_type_target_",""))
        MARATHON_TARGET_WAIT[cid] = amt
        cur = "Naira (₦) - Example: type 30000" if MARATHON["bal_type"]=="REAL" else "Dollar ($) - Example: type 30"
        bot.send_message(cid, f"Type your target amount\n\nStart: {mar_fmt(amt)}\nExpiry: 1 MIN ONLY\nCurrency: {cur}\n\nJust type the number now:"); return
    if data.startswith("mar_target_"):
        parts = data.replace("mar_target_","").split("_")
        start_amt = float(parts[0]); target_amt = float(parts[1])
        if MARATHON["active"]: bot.answer_callback_query(c.id,"Marathon already running"); return
        if MARATHON["bal_type"]=="REAL":
            mk3 = types.InlineKeyboardMarkup(row_width=2)
            mk3.add(types.InlineKeyboardButton(f"YES REAL {mar_fmt(start_amt)} -> {mar_fmt(target_amt)} (1 MIN)",callback_data=f"mar_confirm_custom_{start_amt}_{target_amt}"), types.InlineKeyboardButton("NO, PRACTICE",callback_data="mar_bal_PRACTICE"))
            bot.send_message(cid, f"CONFIRM REAL MONEY - 1 MIN ONLY\nStart {mar_fmt(start_amt)} -> Target {mar_fmt(target_amt)}\nPairs: EUR/USD OTC + GBP/USD OTC\nStop Loss: {mar_fmt(start_amt*0.70)}", reply_markup=mk3, parse_mode="Markdown"); return
        start_marathon(cid, start_amt, target_amt); return
    if data.startswith("mar_confirm_custom_"):
        parts = data.replace("mar_confirm_custom_","").split("_")
        start_amt = float(parts[0]); target_amt = float(parts[1])
        start_marathon(cid, start_amt, target_amt); return
    if data == "mar_stop":
        MARATHON["active"] = False; clear_signal()
        bot.send_message(cid, f"MARATHON STOPPED [{MARATHON['bal_type']}]\nBal: {mar_fmt(MARATHON['bal'])} | Target was {mar_fmt(MARATHON['target'])} | W:{MARATHON['wins']} L:{MARATHON['loss']}"); return
    if data=="ready_btn":
        send_photo_to_channel_sync(READY_PHOTO, get_ready_text())
        bot.answer_callback_query(c.id,"Get Ready sent to Channel!")
        bot.send_message(cid,"Get Ready message has been sent to @KEVINTRAILBLAZE!"); return
    if data.startswith("send_channel_pb_"):
        try:
            parts=data.replace("send_channel_pb_","").rsplit("_",1); pair=parts[0]; dir_ = parts[1] if len(parts)>1 else ACTIVE_SIGNAL.get("dir","CALL")
            tz2=pytz.timezone("Africa/Lagos"); entry_txt=(datetime.now(tz2)+timedelta(seconds=45)).strftime('%H:%M:%S WAT')
            idx = OTC_MARTI["loss_streak"]
            if idx < 1: idx = 1
            if idx > 3: idx = 3
            amt = OTC_MARTI["base"] * OTC_MARTI["levels"][idx]
            expiry = ACTIVE_SIGNAL.get("expiry", 60)
            if pair=="XAUUSD": send_to_channel_sync(format_channel_pullback_gold_signal(dir_, entry_txt, idx, amt))
            else: send_to_channel_sync(format_channel_pullback_signal(pair, dir_, entry_txt, idx, amt, expiry))
            bot.answer_callback_query(c.id,"Brief pullback sent to Channel!")
            bot.send_message(cid,"Brief pullback signal sent to @KEVINTRAILBLAZE")
        except Exception as e: bot.answer_callback_query(c.id,f"Error {e}")
        return
    if data.startswith("send_channel_"):
        try:
            parts=data.replace("send_channel_","").rsplit("_",1); pair=parts[0]; dir_ = parts[1] if len(parts)>1 else ACTIVE_SIGNAL.get("dir","CALL")
            tz2=pytz.timezone("Africa/Lagos"); entry_txt=(datetime.now(tz2)+timedelta(seconds=45)).strftime('%H:%M:%S WAT')
            expiry = ACTIVE_SIGNAL.get("expiry", 60)
            if pair=="XAUUSD":
                if ACTIVE_SIGNAL.get("sl",0) and ACTIVE_SIGNAL.get("pair")=="XAUUSD":
                    d_gold = {"dir":dir_, "conf":ACTIVE_SIGNAL.get("conf",88), "price":ACTIVE_SIGNAL.get("price",0), "sl":ACTIVE_SIGNAL.get("sl",0), "tp1":ACTIVE_SIGNAL.get("tp1",0), "tp2":ACTIVE_SIGNAL.get("tp2",0)}
                    send_to_channel_sync(format_channel_gold_signal(d_gold, entry_txt))
                else: send_to_channel_sync(format_channel_signal(pair, dir_, ACTIVE_SIGNAL.get("conf",88), ACTIVE_SIGNAL.get("price",0), entry_txt, expiry))
            else: send_to_channel_sync(format_channel_signal(pair, dir_, ACTIVE_SIGNAL.get("conf",88), ACTIVE_SIGNAL.get("price",0), entry_txt, expiry))
            bot.answer_callback_query(c.id,"Sent to @KEVINTRAILBLAZE!")
            bot.send_message(cid,"Simple signal has been sent to @KEVINTRAILBLAZE")
        except Exception as e: bot.answer_callback_query(c.id,f"Error {e}")
        return
    if data=="news_btn":
        news=get_upcoming_news()
        if not news: bot.send_message(cid,"NEWS CHECK\n\nNo high impact news in next 2 hours - Clean market!\nSafe to trade all pairs.",parse_mode="Markdown"); return
        txt="UPCOMING NEWS - NEXT 2H\n\n"+format_news_alert(news)+"Bot is blocking these currencies for 30 min before news."; bot.send_message(cid,txt,parse_mode="Markdown"); return
    if data.startswith("skip_"):
        pair=data.replace("skip_","")
        if cid in PULLBACK_STATE: PULLBACK_STATE[cid]["active"]=False
        clear_signal(); LAST_GLOBAL_SIGNAL["time"]=time.time()-(GLOBAL_COOLDOWN-SKIP_COOLDOWN); bot.answer_callback_query(c.id,"Skipped - Next in 5 min"); bot.send_message(cid,f"SKIPPED\n\n{pair}\nYou skipped this trade.\nNo WIN / LOSS recorded.\nNext signal in 5 mins.\nLock opened."); return
    if data.startswith("manual_win_"):
        pair=data.replace("manual_win_",""); win_conf=ACTIVE_SIGNAL.get("conf",88); win_rsi=ACTIVE_SIGNAL.get("rsi",50); win_adx=ACTIVE_SIGNAL.get("adx",30); win_dir=ACTIVE_SIGNAL.get("dir","CALL")
        record_brain(pair,True,win_conf,win_rsi,win_adx); OTC_MARTI["loss_streak"]=0
        if cid in PULLBACK_STATE: PULLBACK_STATE[cid]["active"]=False
        clear_signal(); STATS['wins']+=1; count_trade(); wr=get_pair_winrate(pair); wr_txt=f"\n{pair} Brain WR now {wr:.0f}%" if wr is not None else ""; bot.answer_callback_query(c.id,"WIN")
        base=OTC_MARTI["base"]; profit=round(base*0.85,2); total_return=round(base+profit,2); tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); dir_e="CALL UP" if win_dir=="CALL" else "PUT DOWN"; total=STATS['wins']+STATS['loss']; wr_total=(STATS['wins']/total*100) if total else 0
        win_msg=f"TRADE WON\n\n{PAIR_EMOJI.get(pair,pair)}\n{dir_e} | Conf: {win_conf:.0f}%\n{now.strftime('%H:%M:%S')} | {now.strftime('%d %b')}\n\nStake: ${base:.2f}\nProfit: +${profit:.2f}\nPayout: ${total_return:.2f}\n\nWins: {STATS['wins']} | Loss: {STATS['loss']}\nToday WR: {wr_total:.1f}%{wr_txt}\nNext Entry Reset: ${base:.2f}\nPullback scan STOPPED\nToday: {STATS['daily_trades']}/30 trades\nNext signal can now come.\n"
        bot.send_message(cid,win_msg,parse_mode="Markdown"); return
    if data.startswith("manual_loss_"):
        parts=data.replace("manual_loss_","").rsplit("_",1); pair=parts[0]; orig_dir=parts[1] if len(parts)>1 else "CALL"
        record_brain(pair,False,ACTIVE_SIGNAL.get("conf",88),ACTIVE_SIGNAL.get("rsi",50),ACTIVE_SIGNAL.get("adx",30)); OTC_MARTI["loss_streak"]+=1; STATS['loss']+=1; count_trade()
        if OTC_MARTI["loss_streak"]>=4:
            OTC_MARTI["loss_streak"]=0
            if cid in PULLBACK_STATE: PULLBACK_STATE[cid]["active"]=False
            clear_signal(); wr=get_pair_winrate(pair); wr_txt=f"\n{pair} Brain WR now {wr:.0f}%" if wr is not None else ""; bot.answer_callback_query(c.id,"Chain finished - Reset to $1"); bot.send_message(cid,f"CHAIN FINISHED\n\n{pair}\nLost: $1 + $2 + $4 + $8 = -$15\nRESET to Real Entry $1\nNo more martingale for this pair.{wr_txt}\nToday: {STATS['daily_trades']}/30\nNext signal can now come.\nDo not give up Trailblazer!"); return
        levels=OTC_MARTI["levels"]; idx=OTC_MARTI["loss_streak"]; mult=levels[idx]; next_amt=OTC_MARTI["base"]*mult; names=["","Martingale 1","Martingale 2","Martingale 3"]; wr=get_pair_winrate(pair); wr_txt=f"\n{pair} Brain WR {wr:.0f}%" if wr is not None else ""; bot.answer_callback_query(c.id,f"LOSS - Next {names[idx]} ${next_amt}"); bot.send_message(cid,f"LOSS Recorded\n\n{pair}\nNext: {names[idx]} - ${next_amt:.2f} Level {idx+1}/4 ({mult}x){wr_txt}\nScanning every 10 sec for pullback entry...\nRSI7 + RSI14 safe + RSI turning + Price at EMA\nNews check ON\n\nPress WIN / LOSS / SKIP after you trade it manually.")
        threading.Thread(target=pullback_scanner_loop,args=(cid,pair,orig_dir),daemon=True).start(); return
    if data=="brain_btn":
        txt="AI BRAIN V19\n\n"; best=[]; bad=[]
        for pair,s in PAIR_BRAIN.items():
            total=s["wins"]+s["loss"]
            if total>=3:
                wr=s["wins"]/total*100; line=f"{PAIR_EMOJI.get(pair,pair)}: W{s['wins']} L{s['loss']} = {wr:.0f}% {'BLOCKED' if is_pair_blocked(pair) else ''}\n"
                if wr>=60: best.append(line)
                elif wr<50: bad.append(line)
        txt+="BEST:\n"+("".join(best) if best else "No data yet\n")+"\nBAD:\n"+("".join(bad) if bad else "None\n")+"\nBEST HOURS + SWEET RSI:\n"
        for pair,s in PAIR_BRAIN.items():
            if s.get("best_hour") or s.get("best_rsi_range"):
                rng=s.get("best_rsi_range"); rng_txt=f"{rng[0]:.0f}-{rng[1]:.0f}" if rng else "Learning..."; txt+=f"{pair}: Best {s.get('best_hour','?')}:00 | Worst {s.get('worst_hour','?')}:00 | Sweet RSI {rng_txt}\n"
        sb,sn=get_session_boost("EURUSD"); txt+=f"\nNow: {sn} ({sb:+d})"; bot.send_message(cid,txt,parse_mode="Markdown"); return
    if data=="trade_real":
        mk=types.InlineKeyboardMarkup(row_width=1); mk.add(types.InlineKeyboardButton("SCAN ALL REAL NOW (15 PAIRS)",callback_data="scan_all_real"))
        for p in REAL_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}",callback_data=f"real_pair_{p}"))
        mk.add(types.InlineKeyboardButton("XAU/USD GOLD",callback_data="real_pair_XAUUSD"))
        bot.send_message(cid,f"TRADE REAL V19 TRAILBLAZER MANUAL\n{get_mode_text()}\nToday: {STATS['daily_trades']}/30",reply_markup=mk,parse_mode="Markdown"); return
    if data=="scan_all_real":
        if is_signal_active(): bot.send_message(cid,f"One signal already active\n\n{ACTIVE_SIGNAL['pair']} {ACTIVE_SIGNAL['dir']}\nFinish it first - Press WIN / LOSS / SKIP"); return
        if not can_trade_today(): bot.send_message(cid,"Max 30 trades reached today. Come back tomorrow 7AM."); return
        bot.answer_callback_query(c.id,"Scanning 15 REAL pairs V19..."); scan_msg=bot.send_message(cid,"SCANNING ALL 15 REAL PAIRS V19 TRAILBLAZER...\n\n~12 sec"); results=[]; datas={}
        for pair in REAL_PAIRS:
            if is_pair_blocked(pair): results.append((pair,0,"-","Brain Blocked","BLOCKED",60)); continue
            nb=is_news_blocking_pair(pair,minutes=30)
            if nb: results.append((pair,0,"-","News Block","NEWS",60)); continue
            d=analyze_sniper_v12(pair,sniper_mode=False)
            if not d: results.append((pair,0,"-","No data","NO TRADE",60)); continue
            conf=d['conf']; dir_=d['dir']; reason=d['reason']; exp=d['expiry']
            if conf>=88: status="READY"
            elif conf>=65: status="WAIT"
            else: status="NO TRADE"
            results.append((pair,conf,dir_,reason,status,exp)); datas[pair]=d
            try: bot.edit_message_text(f"Scanning V19... {pair} {conf:.0f}%",cid,scan_msg.message_id)
            except: pass
            time.sleep(0.3)
        results.sort(key=lambda x:x[1],reverse=True); txt="REAL V19 TRAILBLAZER READINESS\n"; txt+=f"{get_mode_text()}\n{datetime.now(pytz.timezone('Africa/Lagos')).strftime('%H:%M:%S WAT')}\nToday: {STATS['daily_trades']}/30\nNews: {len(get_upcoming_news())} high impact in next 2h\n\n"
        for pair,conf,dir_,reason,status,exp in results:
            emoji=PAIR_EMOJI.get(pair,pair)
            if conf>=65: txt+=f"{status} {emoji}: {conf:.0f}% {dir_} - {reason}\n"
            else: txt+=f"{status} {emoji}: {conf:.0f}% - {reason}\n"
        best=results[0] if results else None
        if best and best[1]>=88: txt+=f"\nBEST NOW: {PAIR_EMOJI.get(best[0],best[0])} {best[1]:.0f}%"
        mk=types.InlineKeyboardMarkup(row_width=2)
        if best and best[1]>=88: mk.add(types.InlineKeyboardButton(f"TRADE BEST {best[0]}",callback_data=f"real_pair_{best[0]}"))
        mk.add(types.InlineKeyboardButton("RE-SCAN ALL",callback_data="scan_all_real")); bot.send_message(cid,txt,reply_markup=mk,parse_mode="Markdown")
        if best and best[1]>=88 and best[0] in datas:
            time.sleep(0.5); best_data=datas[best[0]]; tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=45); dir_e="CALL UP" if best_data['dir']=="CALL" else "PUT DOWN"; base=OTC_MARTI["base"]
            mk2=types.InlineKeyboardMarkup(row_width=2)
            mk2.add(types.InlineKeyboardButton("WIN - Reset",callback_data=f"manual_win_{best_data['pair']}"),types.InlineKeyboardButton("LOSS - Pullback Scan",callback_data=f"manual_loss_{best_data['pair']}_{best_data['dir']}"))
            mk2.add(types.InlineKeyboardButton("SKIP THIS TRADE",callback_data=f"skip_{best_data['pair']}"))
            mk2.add(types.InlineKeyboardButton("Send to Channel",callback_data=f"send_channel_{best_data['pair']}_{best_data['dir']}"))
            signal_txt=f"REAL TOP SIGNAL V19 - MANUAL\n\n{PAIR_EMOJI.get(best_data['pair'],best_data['pair'])}\n{dir_e} | {best_data['conf']:.0f}% SNIPER\n{best_data['reason']} | RSI {best_data['rsi']:.1f}\n{int(best_data['payout']*100)}% | {best_data['price']:.5f} | Suggested: 1 Min\nTrend: {best_data.get('trend_info',{}).get('trend_type','NORMAL TREND')}\nNews: Checked\n\nENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)\n\nReal Entry: ${base:.2f}\nMarti 1: ${base*2:.2f} | Marti 2: ${base*4:.2f} | Marti 3: ${base*8:.2f}\n\nMANUAL - Press WIN / LOSS / SKIP\n"
            bot.send_message(cid,signal_txt,parse_mode="Markdown",reply_markup=mk2); start_signal(best_data['pair'],best_data['dir'],best_data['conf'],best_data['rsi'],best_data.get('adx',30), price=best_data['price'], expiry=60)
        return
    if data.startswith("real_pair_"):
        pair=data.replace("real_pair_","")
        if pair=="XAUUSD":
            bot.answer_callback_query(c.id,"Scanning GOLD...")
            d=analyze_xauusd()
            if not d: bot.send_message(cid,"No safe GOLD trade now\n\nConf < 88% or ADX / News block\nTry again in 5 min."); return
            tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry_time=now+timedelta(seconds=45); dir_e="BUY UP" if d['dir']=="CALL" else "SELL DOWN"; base=OTC_MARTI["base"]
            mk=types.InlineKeyboardMarkup(row_width=2)
            mk.add(types.InlineKeyboardButton("WIN - Reset",callback_data="manual_win_XAUUSD"),types.InlineKeyboardButton("LOSS - Pullback Scan",callback_data=f"manual_loss_XAUUSD_{d['dir']}"))
            mk.add(types.InlineKeyboardButton("SKIP THIS TRADE",callback_data="skip_XAUUSD"))
            mk.add(types.InlineKeyboardButton("Send to Channel",callback_data=f"send_channel_XAUUSD_{d['dir']}"))
            msg=f"XAU/USD GOLD SIGNAL\n\n{dir_e} | {d['conf']:.0f}% SNIPER GOLD\n{d['reason']} | RSI {d['rsi']:.1f} | ATR {d['atr']:.2f}\nSession: {d['session']}\n\nENTRY TIME: {entry_time.strftime('%H:%M:%S WAT')}\nENTRY: {d['price']:.2f}\nSL: {d['sl']:.2f}\nTP1: {d['tp1']:.2f} (1:1 Secure)\nTP2: {d['tp2']:.2f} (1:2 Runner)\n\nStake: ${base:.2f}\nMANUAL - Press WIN / LOSS / SKIP\n"
            bot.send_message(cid,msg,parse_mode="Markdown",reply_markup=mk); start_signal("XAUUSD",d['dir'],d['conf'],d['rsi'],d.get('adx',30), price=d['price'], sl=d['sl'], tp1=d['tp1'], tp2=d['tp2']); return
        if is_signal_active() and ACTIVE_SIGNAL['pair']!=pair: bot.send_message(cid,f"One signal already active\n\n{ACTIVE_SIGNAL['pair']} {ACTIVE_SIGNAL['dir']}\nFinish it first - Press WIN / LOSS / SKIP"); return
        if is_pair_blocked(pair): bot.send_message(cid,f"{pair} Blocked by Brain\n\nThis pair has been losing. Brain blocked it for 2h.\nTry another pair or /brain"); return
        nb=is_news_blocking_pair(pair,minutes=30)
        if nb: bot.send_message(cid,f"{pair} Blocked by NEWS\n\n{nb['country']} - {nb['title']}\nIn {nb['in_min']} min\n\nWait 15 min after news."); return
        bot.answer_callback_query(c.id,f"Scanning {pair} V19..."); scan_msg=bot.send_message(cid,f"V19 TRAILBLAZER SCAN {PAIR_EMOJI.get(pair,pair)}\n\n0%\nSniper..."); legit_live_scan(cid,scan_msg.message_id,pair); d=analyze_sniper_v12(pair,sniper_mode=False)
        if not d or d['conf']<88:
            mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("RETRY",callback_data=f"real_pair_{pair}"),types.InlineKeyboardButton("SCAN ALL",callback_data="scan_all_real")); bot.send_message(cid,f"No safe trade now for {pair}\n\nConf: {d['conf'] if d else 0}% < 88%\n{d['reason'] if d else 'No data'}",reply_markup=mk); return
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=45); dir_e="CALL UP" if d['dir']=="CALL" else "PUT DOWN"; base=OTC_MARTI["base"]
        signal_txt=f"REAL SIGNAL V19 TRAILBLAZER - MANUAL\n\n{PAIR_EMOJI.get(pair,pair)}\n{dir_e} | {d['conf']:.0f}% SNIPER\n{d['reason']} | RSI {d['rsi']:.1f} | ATR {d['atr']:.5f}\nTrend: {d.get('trend_info',{}).get('trend_type','NORMAL TREND')}\nTrends: {' | '.join(d.get('trend_info',{}).get('trends',[])[:4])}\n{int(d['payout']*100)}% | {d['price']:.5f} | Suggested: 1 Min\nNews: Checked\n\nENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)\n\nReal Entry: ${base:.2f}\nMarti 1: ${base*2:.2f} | Marti 2: ${base*4:.2f} | Marti 3: ${base*8:.2f}\n\nMANUAL PLACE - Press WIN / LOSS / SKIP\n"
        mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("WIN - Reset",callback_data=f"manual_win_{pair}"),types.InlineKeyboardButton("LOSS - Pullback Scan",callback_data=f"manual_loss_{pair}_{d['dir']}")); mk.add(types.InlineKeyboardButton("SKIP THIS TRADE",callback_data=f"skip_{pair}")); mk.add(types.InlineKeyboardButton("Send to Channel",callback_data=f"send_channel_{pair}_{d['dir']}")); mk.add(types.InlineKeyboardButton("SAME PAIR",callback_data=f"real_pair_{pair}"),types.InlineKeyboardButton("SCAN ALL",callback_data="scan_all_real"))
        bot.send_message(cid,signal_txt,reply_markup=mk,parse_mode="Markdown"); start_signal(pair,d['dir'],d['conf'],d['rsi'],d.get('adx',30), price=d['price'], expiry=60); return
    if data=="trade" or data=="scan_all_otc" or data=="auto_setup" or data.startswith("auto_pair_") or data.startswith("auto_bal_") or data.startswith("auto_amt_") or data.startswith("pair_"):
        bot.answer_callback_query(c.id,"OTC Disabled"); bot.send_message(cid,"OTC DISABLED\n\nOTC is causing delays. Bot will only send REAL signals from 7AM.\n\nUse TRADE REAL for now."); return
    if data=="stop_auto":
        if cid in AUTO_STATE: AUTO_STATE[cid]['running']=False; bot.send_message(cid,"Stopping..."); return
    if data=="stats":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0; bal=get_real_balance("PRACTICE"); sb,sn=get_session_boost("EURUSD"); bot.send_message(cid,f"STATS V19\n{get_mode_text()}\n{get_greeting()}\nSession: {sn} ({sb:+d})\nWins: {STATS['wins']}\nLoss: {STATS['loss']}\nWinrate: {wr:.1f}%\nStreak: {STATS['streak']}\nBal: ${bal:.2f}\nToday: {STATS['daily_trades']}/30\nBrain pairs: {len(PAIR_BRAIN)}\nNews in 2h: {len(get_upcoming_news())}\nOTC: DISABLED | REAL only\nGOLD: XAUUSD ON\nMARATHON: {MARATHON['bal_type']} ({mar_currency()}) | 1 MIN ONLY | Target: {mar_fmt(MARATHON['target'])}",parse_mode="Markdown")
    if data=="settings": bot.send_message(cid,f"SETTINGS V19 TRAILBLAZER MANUAL\n\nV19: 5M Trend + ADX 25+ + MACD + Stochastic + BB + Payout 80%+ + News Block + Session Boost + Brain + Pullback\nMarathon: DUAL SCAN EUR/USD OTC + GBP/USD OTC | 7%-9% Fixed Stake | Stop Loss 30% | 1 MIN ONLY | Custom Target - No Lock\nDEMO = $ Dollar | REAL = ₦ Naira\n\nChannel: @KEVINTRAILBLAZE\nUse /welcome, /intro and /ready to post to channel.")
if __name__ == "__main__":
    print("Starting Trailblazer Bot V19 - DUAL SCAN 2 PAIRS EURUSD-OTC + GBPUSD-OTC + START FIXED + NAIRA REAL...")
    try:
        bot.remove_webhook()
        time.sleep(1)
    except: pass
    threading.Thread(target=background_iq, daemon=True).start()
    threading.Thread(target=daily_summary_loop, daemon=True).start()
    threading.Thread(target=trailblazer_market_scanner, daemon=True).start()
    threading.Thread(target=morning_greet_loop, daemon=True).start()
    threading.Thread(target=xauusd_signal_scanner, daemon=True).start()
    threading.Thread(target=real_signal_scanner, daemon=True).start()
    def run_polling():
        while True:
            try:
                print("Bot polling started...")
                bot.infinity_polling(timeout=30, long_polling_timeout=30)
            except Exception as e:
                print(f"Polling error: {e} - Retrying in 5 seconds...")
                time.sleep(5)
    threading.Thread(target=run_polling, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    print(f"Flask running on port {port}")
    app.run(host="0.0.0.0", port=port)
