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
logging.disable(logging.ERROR)
BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELE_TOKEN")
OWNER_ID = 8659453018
CHANNEL_ID = "@KEVINTRAILBLAZE"
WELCOME_PHOTO = "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=1080&q=80"
INTRO_PHOTO = "https://images.unsplash.com/photo-1621761191319-c6fb62004040?w=1080&q=80"
READY_PHOTO = "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=1080&q=80"
if not BOT_TOKEN:
    print("ERROR BOT_TOKEN missing")
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)

# --- USERS ---
USERS_FILE = "users.json"
ALLOWED_USERS = set()
def load_users():
    global ALLOWED_USERS
    try:
        with open(USERS_FILE, "r") as f:
            ALLOWED_USERS = set(json.load(f))
    except:
        ALLOWED_USERS = set()
def save_users():
    try:
        with open(USERS_FILE, "w") as f:
            json.dump(list(ALLOWED_USERS), f)
    except:
        pass
load_users()
def is_admin(uid):
    return uid == OWNER_ID
def is_allowed(uid):
    return uid == OWNER_ID or uid in ALLOWED_USERS

# --- PER USER BRAIN ---
USER_DATA_FILE = "user_data.json"
USER_DATA = {}
def load_user_data():
    global USER_DATA
    try:
        with open(USER_DATA_FILE, "r") as f:
            USER_DATA = json.load(f)
    except:
        USER_DATA = {}
def save_user_data():
    try:
        with open(USER_DATA_FILE, "w") as f:
            json.dump(USER_DATA, f)
    except:
        pass
load_user_data()
def get_user_data(uid):
    key = str(uid)
    if key not in USER_DATA:
        USER_DATA[key] = {"wins": 0, "loss": 0, "streak": 0, "daily_trades": 0, "marti_streak": 0, "pairs": {}}
    return USER_DATA[key]
def record_user_result(uid, pair, won):
    u = get_user_data(uid)
    if pair not in u["pairs"]:
        u["pairs"][pair] = {"wins": 0, "loss": 0}
    if won:
        u["wins"] += 1
        u["pairs"][pair]["wins"] += 1
        u["marti_streak"] = 0
        u["streak"] += 1
    else:
        u["loss"] += 1
        u["pairs"][pair]["loss"] += 1
        u["marti_streak"] += 1
        u["streak"] = 0
    u["daily_trades"] += 1
    save_user_data()
    return u
def send_signal_to_users(pair, dir_, text):
    for uid in list(ALLOWED_USERS):
        try:
            mk = types.InlineKeyboardMarkup(row_width=2)
            mk.add(types.InlineKeyboardButton("✅ MY WIN", callback_data="user_win_" + pair), types.InlineKeyboardButton("❌ MY LOSS", callback_data="user_loss_" + pair + "_" + dir_))
            mk.add(types.InlineKeyboardButton("⏭️ SKIP", callback_data="user_skip_" + pair))
            bot.send_message(uid, text, parse_mode="Markdown", reply_markup=mk)
        except Exception as e:
            print("send user fail " + str(e))

# --- AUTO 90 OFF BY DEFAULT ---
AUTO_FILE = "auto90.json"
AUTO_SEND_90 = False
def load_auto():
    global AUTO_SEND_90
    try:
        with open(AUTO_FILE, "r") as f:
            d = json.load(f)
            AUTO_SEND_90 = d.get("auto_send_90", False)
    except:
        AUTO_SEND_90 = False
def save_auto():
    try:
        with open(AUTO_FILE, "w") as f:
            json.dump({"auto_send_90": AUTO_SEND_90}, f)
    except:
        pass
load_auto()

REAL_PAIRS = ["EURUSD","GBPUSD","EURGBP","AUDUSD","USDCAD","USDCHF","EURAUD","GBPCHF","EURCHF","NZDUSD","GBPAUD","EURCAD","AUDCAD","GBPCAD","AUDNZD"]
OTC_PAIRS = ["EURUSD-OTC","GBPUSD-OTC","AUDUSD-OTC","USDCAD-OTC","EURGBP-OTC","EURAUD-OTC","GBPAUD-OTC","NZDUSD-OTC","GBPCHF-OTC","EURCHF-OTC","USDCHF-OTC","AUDCAD-OTC","EURCAD-OTC"]
PAIR_EMOJI = {"EURUSD":"🇪🇺 EUR/USD REAL","GBPUSD":"🇬🇧 GBP/USD REAL","EURGBP":"🇪🇺 EUR/GBP REAL","AUDUSD":"🇦🇺 AUD/USD REAL","USDCAD":"🇺🇸 USD/CAD REAL","USDCHF":"🇺🇸 USD/CHF REAL","EURAUD":"🇪🇺 EUR/AUD REAL","GBPCHF":"🇬🇧 GBP/CHF REAL","EURCHF":"🇪🇺 EUR/CHF REAL","NZDUSD":"🇳🇿 NZD/USD REAL","GBPAUD":"🇬🇧 GBP/AUD REAL","EURCAD":"🇪🇺 EUR/CAD REAL","AUDCAD":"🇦🇺 AUD/CAD REAL","GBPCAD":"🇬🇧 GBP/CAD REAL","AUDNZD":"🇦🇺 AUD/NZD REAL","XAUUSD":"🥇 XAU/USD GOLD","EURUSD-OTC":"🇪🇺 EUR/USD OTC","GBPUSD-OTC":"🇬🇧 GBP/USD OTC","EURGBP-OTC":"🇪🇺 EUR/GBP OTC","AUDUSD-OTC":"🇦🇺 AUD/USD OTC","USDCHF-OTC":"🇺🇸 USD/CHF OTC","EURAUD-OTC":"🇪🇺 EUR/AUD OTC","GBPAUD-OTC":"🇬🇧 GBP/AUD OTC","NZDUSD-OTC":"🇳🇿 NZD/USD OTC","GBPCHF-OTC":"🇬🇧 GBP/CHF OTC","EURCHF-OTC":"🇪🇺 EUR/CHF OTC","USDCAD-OTC":"🇺🇸 USD/CAD OTC","AUDCAD-OTC":"🇦🇺 AUD/CAD OTC","EURCAD-OTC":"🇪🇺 EUR/CAD OTC"}

WELCOME_TEXT = "🔥🔥🔥 WELCOME TO TRAILBLAZER SIGNALS 🔥🔥🔥\n━━━━━━━━━━━━━━━━━━\n👋 Welcome Trader! You don arrive for right place.\n\n🥇 WHAT WE DO HERE\n📈 Forex and GOLD Sniper Signals\n🎯 88%+ Accuracy Only\n🧠 Smart System Wey Dey Learn From Every Win and Loss\n💰 Martingale 1-2-4-8 To Recover Losses\n\n📜 CHANNEL RULES\n✅ 1. Follow The Stake - $1, $2, $4, $8 - No Greedy\n✅ 2. No Overtrade - Max 30 Signals Per Day\n✅ 3. Enter Exactly At Entry Time\n✅ 4. Press WIN or LOSS After Every Trade\n❌ 5. No Spam, No DM Admin For Signals\n❌ 6. No Borrow Money To Trade\n\n🚀 NEW HERE? Type /intro For Full Guide\n📊 Type /mystats To See Your Result\n📢 Channel: @KEVINTRAILBLAZE\n\n━━━━━━━━━━━━━━━━━━\n💪 Good Luck Trader! Make We Grow Together! 🤑\n🏆 TRAILBLAZER - WE MOVE! 🔥"
INTRO_TEXT = "📚📚 TRAILBLAZER INTRO 📚📚\n━━━━━━━━━━━━━━━━━━\n💱 WHAT IS FOREX?\nForex Means Foreign Exchange. You Predict If Price Go UP ⬆️ Or DOWN ⬇️\nExample: EUR/USD - Euro Against Dollar.\nIf Euro Strong, Press BUY / CALL 🟢\nIf Euro Weak, Press SELL / PUT 🔴\n\n📈 HOW YOU DEY MAKE MONEY?\n1️⃣ Enter With $1\n2️⃣ If You Correct, IQ Pay You 85% = $1.85 Back 🤑\n3️⃣ If You Wrong, We Use Martingale $1 ➡️ $2 ➡️ $4 ➡️ $8 To Recover\n\n🥇 GOLD (XAU/USD) SAME WAY\nGold Price Go Up and Down. We Trade Am With Stop Loss and Take Profit.\n\n🚀 HOW TO START ON IQ OPTION\n1️⃣ CREATE ACCOUNT - iqoption.com -> Sign Up\n2️⃣ VERIFY EMAIL 📧\n3️⃣ PRACTICE WITH DEMO 🎮 - $10,000 Demo, Practice 2-3 Days\n4️⃣ VERIFY ACCOUNT (KYC) 🪪 - Upload ID and Selfie\n5️⃣ DEPOSIT 💳 - Start With $10-$20 Only\n6️⃣ TRADE WITH US 🔥 - Wait For Signal, Enter At ENTRY TIME\n\n⚠️ RULES:\n• No Overtrade - Max 30 Per Day\n• Follow Stake - $1, $2, $4, $8\n• Only Trade Money You Fit Lose\n\n📢 Channel: @KEVINTRAILBLAZE\n👋 Welcome Again! Make We Go! 🚀"

STATS = {"balance":0.0,"real_balance":0.0,"wins":0,"loss":0,"streak":0,"daily_trades":0,"daily_date":""}
AUTO_STATE = {}
IQ_LOCK = threading.Lock()
IQ_CONNECTED = False
iq = None
PAYOUT_CACHE = {}
PAYOUT_TIME = 0
OTC_SESSION_RESULTS = []
OTC_MARTI = {"loss_streak":0, "base":1.0, "bal":"PRACTICE", "levels":[1,2,4,8]}
PULLBACK_STATE = {}
ACTIVE_SIGNAL = {"active": False, "pair": None, "dir": None, "conf":0, "rsi":0, "adx":0, "started": 0, "day": "", "price": 0, "sl": 0, "tp1": 0, "tp2": 0, "expiry": 120}
LAST_GLOBAL_SIGNAL = {"time": 0}
GLOBAL_COOLDOWN = 360
SKIP_COOLDOWN = 120
DAILY_SUMMARY_SENT = ""
MARKET_GOOD_SENT = {"date": "", "last_alert": 0}
MORNING_GREET_SENT = ""
NEWS_CACHE = {"data": [], "time": 0}

def send_to_channel_sync(text):
    try:
        bot.send_message(CHANNEL_ID, text, parse_mode="Markdown")
    except Exception as e:
        print("channel err " + str(e))
def send_photo_to_channel_sync(photo_url, caption):
    try:
        bot.send_photo(CHANNEL_ID, photo_url, caption=caption, parse_mode="Markdown")
    except Exception as e:
        print("photo err " + str(e))
        try:
            bot.send_message(CHANNEL_ID, caption, parse_mode="Markdown")
        except:
            pass

def format_channel_signal(pair, dir_, conf, price, entry_time_txt, expiry=120):
    if dir_ == "CALL":
        action = "🟢 BUY / CALL ⬆️"
        meaning = "Price Expected To Go UP, Press GREEN BUY / CALL Button In IQ Option"
    else:
        action = "🔴 SELL / PUT ⬇️"
        meaning = "Price Expected To Go DOWN, Press RED SELL / PUT Button In IQ Option"
    pair_name = PAIR_EMOJI.get(pair, pair)
    if price and price != 0:
        price_txt = "{:.5f}".format(price)
    else:
        price_txt = "Market Price"
    expiry_min = int(expiry // 60) if expiry else 2
    conf_txt = "{:.0f}".format(conf)
    out = "🔥🔥🔥 TRAILBLAZER SIGNAL 🔥🔥🔥\n\n"
    out += "💱 Pair: " + pair_name + "\n"
    out += "📊 Signal: " + action + "\n"
    out += "🎯 Confidence: " + conf_txt + "%\n\n"
    out += "💡 What It Means:\n" + meaning + "\n\n"
    out += "━━━━━━━━━━━━━━━━━━\n"
    out += "⏰ ENTRY TIME: " + entry_time_txt + "\n"
    out += "💰 ENTRY PRICE: " + price_txt + "\n"
    out += "💵 STAKE: $1 (If You Lose, Next Is $2, Then $4, Then $8)\n"
    out += "⏱️ EXPIRY: " + str(expiry_min) + " Minutes - Use Same Expiry\n"
    out += "━━━━━━━━━━━━━━━━━━\n\n"
    out += "👣 HOW TO TRADE:\n"
    out += "1️⃣ Open IQ Option App\n"
    out += "2️⃣ Search For " + pair + "\n"
    out += "3️⃣ Wait Till " + entry_time_txt + "\n"
    out += "4️⃣ Set Expiry To " + str(expiry_min) + " Min\n"
    out += "5️⃣ Press " + action + "\n"
    out += "6️⃣ Enter With $1 And Wait\n\n"
    out += "⚠️ RULES:\n✅ Enter Exactly At Entry Time\n✅ No Greedy - Follow $1, $2, $4, $8\n❌ No Overtrade\n\n"
    out += "📢 Channel: @KEVINTRAILBLAZE\nGood Luck! 💪🤑"
    return out

def format_channel_gold_signal(d, entry_time_txt):
    dir_ = d["dir"]
    conf = d["conf"]
    price = d["price"]
    sl = d["sl"]
    tp1 = d["tp1"]
    tp2 = d["tp2"]
    if dir_ == "CALL":
        dir_e = "🟢 BUY ⬆️"
        what = "Gold Price Expected To Go UP, Press GREEN BUY"
    else:
        dir_e = "🔴 SELL ⬇️"
        what = "Gold Price Expected To Go DOWN, Press RED SELL"
    out = "🥇🥇🥇 GOLD SIGNAL - XAU/USD 🥇🥇🥇\n\n"
    out += "📊 Signal: " + dir_e + "\n"
    out += "🎯 Confidence: {:.0f}%\n\n".format(conf)
    out += "💡 What It Means:\n" + what + "\n\n"
    out += "━━━━━━━━━━━━━━━━━━\n"
    out += "⏰ ENTRY TIME: " + entry_time_txt + "\n"
    out += "💰 ENTRY: {:.2f}\n".format(price)
    out += "🛑 STOP LOSS: {:.2f}\n".format(sl)
    out += "🎯 TAKE PROFIT 1: {:.2f} (Small Profit)\n".format(tp1)
    out += "🎯 TAKE PROFIT 2: {:.2f} (Bigger Profit)\n".format(tp2)
    out += "━━━━━━━━━━━━━━━━━━\n\n"
    out += "👣 Open IQ Option -> GOLD / XAU/USD -> Wait Till " + entry_time_txt + " -> Press " + dir_e + "\n"
    out += "⚠️ GOLD: Hold Till TP or SL. No Close Early.\n\n"
    out += "📢 Channel: @KEVINTRAILBLAZE\nMake We Grow Together! 🔥"
    return out

def format_channel_pullback_signal(pair, dir_, entry_time_txt, level_idx=1, amount=2.0, expiry=120):
    if dir_ == "CALL":
        action = "🟢 BUY / CALL ⬆️"
    else:
        action = "🔴 SELL / PUT ⬇️"
    pair_name = PAIR_EMOJI.get(pair, pair)
    level_names = ["", "Martingale 1", "Martingale 2", "Martingale 3"]
    if 1 <= level_idx <= 3:
        level_name = level_names[level_idx]
    else:
        level_name = "Martingale " + str(level_idx)
    expiry_min = int(expiry // 60) if expiry else 2
    out = "🔁 " + level_name.upper() + " - " + pair_name + "\n\n"
    out += "📊 " + action + "\n"
    out += "⏰ Entry: " + entry_time_txt + "\n"
    out += "💵 Stake: ${:.2f}\n".format(amount)
    out += "⏱️ Expiry: " + str(expiry_min) + " Min\n\n"
    out += "👉 Open IQ Option -> Search " + pair + " -> Press " + action + " At Entry Time.\n\n"
    out += "📢 @KEVINTRAILBLAZE"
    return out

def format_channel_pullback_gold_signal(dir_, entry_time_txt, level_idx=1, amount=2.0):
    if dir_ == "CALL":
        dir_e = "🟢 BUY ⬆️"
    else:
        dir_e = "🔴 SELL ⬇️"
    level_names = ["", "Martingale 1", "Martingale 2", "Martingale 3"]
    if 1 <= level_idx <= 3:
        level_name = level_names[level_idx]
    else:
        level_name = "Martingale " + str(level_idx)
    out = "🔁 " + level_name.upper() + " - 🥇 GOLD XAU/USD\n\n"
    out += "📊 " + dir_e + "\n"
    out += "⏰ Entry: " + entry_time_txt + "\n"
    out += "💵 Stake: ${:.2f}\n\n".format(amount)
    out += "👉 Open IQ Option -> GOLD -> Press " + dir_e + "\nUse Same SL / TP As First Signal.\n\n📢 @KEVINTRAILBLAZE"
    return out

def get_lagos_day():
    return datetime.now(pytz.timezone("Africa/Lagos")).strftime("%Y-%m-%d")
def check_and_reset_new_day():
    today = get_lagos_day()
    if STATS["daily_date"] != today:
        STATS["daily_date"] = today
        STATS["daily_trades"] = 0
        ACTIVE_SIGNAL.update({"active": False, "pair": None, "dir": None, "conf": 0, "rsi": 0, "adx": 0, "started": 0, "day": "", "price": 0, "sl": 0, "tp1": 0, "tp2": 0, "expiry": 120})
        PULLBACK_STATE.clear()
        OTC_MARTI["loss_streak"] = 0
        return True
    if ACTIVE_SIGNAL["active"] and ACTIVE_SIGNAL.get("day") and ACTIVE_SIGNAL["day"] != today:
        ACTIVE_SIGNAL.update({"active": False, "pair": None, "dir": None, "conf": 0, "rsi": 0, "adx": 0, "started": 0, "day": "", "price": 0, "sl": 0, "tp1": 0, "tp2": 0, "expiry": 120})
        PULLBACK_STATE.clear()
        OTC_MARTI["loss_streak"] = 0
        return True
    return False
def get_greeting():
    tz = pytz.timezone("Africa/Lagos")
    hour = datetime.now(tz).hour
    if 5 <= hour < 12:
        return "🌅 GOOD MORNING TRAILBLAZER ☀️"
    elif 12 <= hour < 17:
        return "☀️ GOOD AFTERNOON TRAILBLAZER 🔥"
    elif 17 <= hour < 21:
        return "🌇 GOOD EVENING TRAILBLAZER 🌙"
    else:
        return "🌙 GOOD NIGHT TRAILBLAZER 💤"
def get_session_boost(pair):
    tz = pytz.timezone("Africa/Lagos")
    now = datetime.now(tz)
    hour = now.hour + now.minute / 60
    if pair == "XAUUSD":
        if 14.5 <= hour < 17:
            return 10, "🥇🇬🇧🇺🇸 GOLD LONDON+NY OVERLAP 🔥"
        if 8 <= hour < 11:
            return 8, "🥇 LONDON OPEN GOLD"
        if 12 <= hour < 13.5:
            return -10, "😴 LUNCH DEAD ZONE"
        if 18 <= hour < 20:
            return -5, "🌙 EVENING SLOW"
        return 0, "🥇 GOLD NORMAL"
    if 8 <= hour < 11:
        return 8, "🇬🇧 LONDON OPEN"
    elif 14.5 <= hour < 17:
        return 10, "🇬🇧🇺🇸 LONDON + NY OVERLAP 🔥"
    elif 14 <= hour < 14.5:
        return 4, "🇺🇸 NY PRE-OPEN"
    elif 12 <= hour < 13.5:
        return -10, "😴 LUNCH DEAD ZONE"
    elif 18 <= hour < 20:
        return -5, "🌙 EVENING SLOW"
    elif 11 <= hour < 12:
        return 3, "🇬🇧 LONDON MORNING"
    elif 17 <= hour < 18:
        return 2, "🇺🇸 NY AFTERNOON"
    else:
        return 0, "🌍 NORMAL"
def get_upcoming_news():
    try:
        if time.time() - NEWS_CACHE["time"] < 300:
            return NEWS_CACHE["data"]
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        now = datetime.now(pytz.timezone("UTC")).replace(tzinfo=None)
        upcoming = []
        for event in root.findall("event"):
            try:
                title = event.find("title").text
                country = event.find("country").text
                impact = event.find("impact").text
                date_str = event.find("date").text
                time_str = event.find("time").text
                if impact != "High":
                    continue
                if country not in ["USD","EUR","GBP","AUD","CAD","NZD","CHF"]:
                    continue
                dt = datetime.strptime(date_str + " " + time_str, "%m-%d-%Y %I:%M%p")
                dt_utc = dt + timedelta(hours=5)
                diff_min = (dt_utc - now).total_seconds() / 60
                if -15 <= diff_min <= 120:
                    upcoming.append({"title": title, "country": country, "time_utc": dt_utc, "in_min": int(diff_min), "impact": impact})
            except:
                continue
        NEWS_CACHE["data"] = upcoming
        NEWS_CACHE["time"] = time.time()
        return upcoming
    except Exception as e:
        print("News err " + str(e))
        return []
def is_news_blocking_pair(pair, minutes=30):
    news = get_upcoming_news()
    if not news:
        return None
    if pair == "XAUUSD":
        base = "XAU"
        quote = "USD"
    else:
        base = pair[:3]
        if len(pair) >= 6:
            quote = pair[3:6]
        else:
            quote = ""
    for n in news:
        nc = n["country"]
        nin = n["in_min"]
        if nc in [base, quote] and nin <= minutes and nin >= -15:
            return n
    return None
def format_news_alert(news_list):
    if not news_list:
        return ""
    txt = "📰 **UPCOMING HIGH IMPACT NEWS** 📰\n\n"
    for n in news_list:
        nc = n["country"]
        title = n["title"]
        nin = n["in_min"]
        flag_map = {"USD":"🇺🇸","EUR":"🇪🇺","GBP":"🇬🇧","AUD":"🇦🇺","CAD":"🇨🇦","NZD":"🇳🇿","CHF":"🇨🇭"}
        flag = flag_map.get(nc, "🌍")
        if nin < 0:
            when = "Started " + str(-nin) + " min ago"
        elif nin == 0:
            when = "⚡ RIGHT NOW!"
        else:
            when = "In " + str(nin) + " min"
        txt += "🔴 " + flag + " " + nc + " - " + title + "\n⏰ " + when + "\n\n"
    return txt
def get_ready_text():
    tz = pytz.timezone("Africa/Lagos")
    now = datetime.now(tz)
    sb, sn = get_session_boost("EURUSD")
    news = get_upcoming_news()
    if not news:
        news_txt = "✅ No High Impact News In Next 2 Hours - Clean Market"
    else:
        news_txt = "⚠️ " + str(len(news)) + " High Impact News In Next 2 Hours - Bot Will Avoid Those Pairs"
    out = "🚀🚀🚀 GET READY TRAILBLAZERS 🚀🚀🚀\n\n"
    out += get_greeting() + "\n\n"
    out += "⏰ Time: " + now.strftime("%A, %d %b %Y - %H:%M WAT") + "\n"
    out += "⏰ Session: " + sn + "\n"
    out += "📊 Mode: " + get_mode_text() + "\n"
    out += "📰 News: " + news_txt + "\n"
    out += "📅 Today: " + str(STATS["daily_trades"]) + "/30 Trades Used\n\n"
    out += "━━━━━━━━━━━━━━━━━━\n✅ CHECKLIST - DO THIS NOW:\n━━━━━━━━━━━━━━━━━━\n\n"
    out += "1️⃣ OPEN IQ OPTION APP 📱\n2️⃣ CHECK BALANCE 💰 - At Least $15-$20\n3️⃣ CHECK INTERNET 🌐 - Strong WiFi/Data\n4️⃣ CHARGE PHONE 🔋 - At Least 50%\n5️⃣ SET STAKE TO $1 💵 - Martingale $1->$2->$4->$8\n6️⃣ SET CHART TO 1 MINUTE 📊\n7️⃣ CLEAR YOUR MIND 🧠\n\n"
    out += "━━━━━━━━━━━━━━━━━━\n📋 TODAY:\n🎯 Only 88%+ Sniper Signals\n💱 15 Forex + GOLD\n⏱️ Enter Exactly At Entry Time\n✅ Win - Go Back To $1\n❌ Lose - Wait For Martingale\n⏭️ Miss - Skip, No Chase\n\n🔥 SIGNALS COMING SOON - STAY READY! 🔥\n📢 Channel: @KEVINTRAILBLAZE"
    return out

PAIR_BRAIN = {}
def load_brain():
    global PAIR_BRAIN
    try:
        with open("brain.json","r") as f:
            PAIR_BRAIN = json.load(f)
    except:
        PAIR_BRAIN = {}
def save_brain():
    try:
        with open("brain.json","w") as f:
            json.dump(PAIR_BRAIN, f)
    except:
        pass
def get_pair_stats(pair):
    if pair not in PAIR_BRAIN:
        PAIR_BRAIN[pair] = {"wins":0,"loss":0,"history":[],"blocked_until":0,"score_boost":0,"hour_stats":{},"rsi_wins":[],"rsi_loss":[],"best_hour":None,"worst_hour":None,"best_rsi_range":None}
    s = PAIR_BRAIN[pair]
    if "hour_stats" not in s:
        s["hour_stats"] = {}
    if "rsi_wins" not in s:
        s["rsi_wins"] = []
    if "rsi_loss" not in s:
        s["rsi_loss"] = []
    return s
def get_pair_winrate(pair):
    s = get_pair_stats(pair)
    total = s["wins"] + s["loss"]
    if total < 3:
        return None
    return s["wins"] / total * 100
def is_pair_blocked(pair):
    s = get_pair_stats(pair)
    return time.time() < s["blocked_until"]
def record_brain(pair, won, conf, rsi, adx):
    s = get_pair_stats(pair)
    tz = pytz.timezone("Africa/Lagos")
    hour = str(datetime.now(tz).hour)
    if won:
        s["wins"] += 1
    else:
        s["loss"] += 1
    if hour not in s["hour_stats"]:
        s["hour_stats"][hour] = {"wins":0,"loss":0}
    if won:
        s["hour_stats"][hour]["wins"] += 1
    else:
        s["hour_stats"][hour]["loss"] += 1
    if won:
        s["rsi_wins"].append(rsi)
    else:
        s["rsi_loss"].append(rsi)
    s["rsi_wins"] = s["rsi_wins"][-30:]
    s["rsi_loss"] = s["rsi_loss"][-30:]
    s["history"].append({"win":won,"conf":conf,"rsi":rsi,"adx":adx,"time":time.time(),"hour":hour})
    s["history"] = s["history"][-30:]
    best_h = None
    best_wr = 0
    worst_h = None
    worst_wr = 100
    for h, st in s["hour_stats"].items():
        total = st["wins"] + st["loss"]
        if total >= 3:
            wr = st["wins"]/total*100
            if wr > best_wr:
                best_wr = wr
                best_h = h
            if wr < worst_wr:
                worst_wr = wr
                worst_h = h
    s["best_hour"] = best_h
    s["worst_hour"] = worst_h
    if len(s["rsi_wins"]) >= 5:
        avg = sum(s["rsi_wins"]) / len(s["rsi_wins"])
        s["best_rsi_range"] = [avg - 7, avg + 7]
    wr = get_pair_winrate(pair)
    total = s["wins"] + s["loss"]
    if total >= 5:
        if wr < 40:
            s["blocked_until"] = time.time() + 7200
            s["score_boost"] = -15
        elif wr < 50:
            s["score_boost"] = -8
        elif wr >= 65:
            s["score_boost"] = 8
            s["blocked_until"] = 0
        elif wr >= 55:
            s["score_boost"] = 3
        else:
            s["score_boost"] = 0
    save_brain()
def get_hour_boost(pair):
    s = get_pair_stats(pair)
    tz = pytz.timezone("Africa/Lagos")
    hour = str(datetime.now(tz).hour)
    hs = s.get("hour_stats", {})
    if hour not in hs:
        return 0, ""
    st = hs[hour]
    total = st["wins"] + st["loss"]
    if total < 3:
        return 0, ""
    wr = st["wins"]/total*100
    if wr >= 70:
        return 8, "🧠 Best Hour " + hour + ":00 {:.0f}%".format(wr)
    elif wr >= 60:
        return 4, "🧠 Good Hour " + hour + ":00 {:.0f}%".format(wr)
    elif wr < 40:
        return -10, "🧠 Bad Hour " + hour + ":00 {:.0f}%".format(wr)
    elif wr < 50:
        return -5, "🧠 Weak Hour " + hour + ":00 {:.0f}%".format(wr)
    return 0, ""
def get_pair_rsi_boost(pair, current_rsi, is_call):
    s = get_pair_stats(pair)
    rng = s.get("best_rsi_range")
    wins = s.get("rsi_wins", [])
    if not rng or len(wins) < 5:
        return 0, ""
    low = rng[0]
    high = rng[1]
    if low <= current_rsi <= high:
        return 6, "🧠 RSI Sweet Spot {:.0f} in [{:.0f}-{:.0f}]".format(current_rsi, low, high)
    dist = min(abs(current_rsi - low), abs(current_rsi - high))
    if dist > 15:
        return -6, "🧠 RSI Off {:.0f} vs Sweet [{:.0f}-{:.0f}]".format(current_rsi, low, high)
    return 0, ""
load_brain()
def is_signal_active():
    check_and_reset_new_day()
    return ACTIVE_SIGNAL["active"]
def start_signal(pair, dir_, conf=0, rsi=0, adx=0, price=0, sl=0, tp1=0, tp2=0, expiry=120):
    check_and_reset_new_day()
    ACTIVE_SIGNAL.update({"active":True,"pair":pair,"dir":dir_,"conf":conf,"rsi":rsi,"adx":adx,"started":time.time(),"day":get_lagos_day(),"price":price,"sl":sl,"tp1":tp1,"tp2":tp2,"expiry":expiry})
def clear_signal():
    ACTIVE_SIGNAL.update({"active":False,"pair":None,"dir":None,"conf":0,"rsi":0,"adx":0,"started":0,"day":"","price":0,"sl":0,"tp1":0,"tp2":0,"expiry":120})
def is_real_hours():
    try:
        tz = pytz.timezone("Africa/Lagos")
        now = datetime.now(tz)
        if now.weekday() >= 5:
            return False
        return 7 <= now.hour < 20
    except:
        now = datetime.now(timezone.utc) + timedelta(hours=1)
        if now.weekday() >= 5:
            return False
        return 7 <= now.hour < 20
def get_mode_text():
    if is_real_hours():
        return "REAL SIGNAL (7AM-8PM)"
    else:
        return "OTC DISABLED - Waiting For REAL 7AM"
def can_trade_today():
    check_and_reset_new_day()
    return STATS["daily_trades"] < 30
def count_trade():
    STATS["daily_trades"] += 1

@app.route("/")
def home():
    t = datetime.now(pytz.timezone("Africa/Lagos")).strftime("%H:%M:%S")
    return "V4 TRAILBLAZER EMOJI RUNNING IQ:" + str(IQ_CONNECTED) + " " + t
@app.route("/" + str(BOT_TOKEN), methods=["POST"])
def wh():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode("utf-8"))])
    return "ok"

def background_iq():
    global iq, IQ_CONNECTED
    time.sleep(3)
    for attempt in range(10):
        try:
            from iqoptionapi.stable_api import IQ_Option
            EMAIL = os.getenv("IQ_EMAIL")
            PWD = os.getenv("IQ_PASS")
            PROXY = os.getenv("PROXY_URL")
            if not EMAIL or not PWD:
                print("IQ_EMAIL/PASS missing")
                return
            iq = IQ_Option(EMAIL, PWD)
            if PROXY:
                try:
                    pc = PROXY.replace("http://","").replace("https://","")
                    if "@" in pc:
                        up, hp = pc.split("@")
                        pu, pp = up.split(":")
                        ph, pt = hp.split(":")
                        iq.set_proxy(proxy_type="http", host=ph, port=int(pt), user=pu, password=pp)
                except:
                    pass
            logging.disable(logging.CRITICAL)
            iq.connect()
            IQ_CONNECTED = iq.check_connect()
            if IQ_CONNECTED:
                try:
                    iq.change_balance("PRACTICE")
                    time.sleep(1)
                    STATS["real_balance"] = iq.get_balance()
                    print("IQ SUCCESS")
                except:
                    pass
                return
            time.sleep(8)
        except Exception as e:
            print("IQ Fail " + str(e))
            time.sleep(10)
    IQ_CONNECTED = False

def iq_reconnect():
    global iq, IQ_CONNECTED
    try:
        from iqoptionapi.stable_api import IQ_Option
        logging.disable(logging.CRITICAL)
        iq = IQ_Option(os.getenv("IQ_EMAIL"), os.getenv("IQ_PASS"))
        PROXY = os.getenv("PROXY_URL")
        if PROXY:
            try:
                pc = PROXY.replace("http://","").replace("https://","")
                if "@" in pc:
                    up, hp = pc.split("@")
                    pu, pp = up.split(":")
                    ph, pt = hp.split(":")
                    iq.set_proxy(proxy_type="http", host=ph, port=int(pt), user=pu, password=pp)
            except:
                pass
        iq.connect()
        IQ_CONNECTED = iq.check_connect()
        if IQ_CONNECTED:
            try:
                STATS["real_balance"] = iq.get_balance()
            except:
                pass
        return IQ_CONNECTED
    except:
        IQ_CONNECTED = False
        return False

def get_real_balance(bal_type="PRACTICE"):
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL)
            iq.change_balance(bal_type)
            return iq.get_balance()
    except:
        return 0.0
def get_payout(pair):
    global PAYOUT_CACHE, PAYOUT_TIME
    if time.time() - PAYOUT_TIME < 60 and pair in PAYOUT_CACHE:
        return PAYOUT_CACHE[pair]
    try:
        logging.disable(logging.CRITICAL)
        all_p = iq.get_all_profit()
        if pair in all_p:
            for k in ["blitz","turbo","binary"]:
                if k in all_p[pair]:
                    PAYOUT_CACHE[pair] = float(all_p[pair][k])
                    PAYOUT_TIME = time.time()
                    return float(all_p[pair][k])
        return 0.85
    except:
        return PAYOUT_CACHE.get(pair, 0.85)
def get_candles(pair):
    if not IQ_CONNECTED and not iq_reconnect():
        return None
    if pair not in REAL_PAIRS and pair not in OTC_PAIRS and pair != "XAUUSD":
        return None
    for _ in range(3):
        try:
            logging.disable(logging.CRITICAL)
            c = iq.get_candles(pair, 60, 100, time.time())
            if c and len(c) > 50:
                return pd.DataFrame(sorted(c, key=lambda x: x["from"]))
            c2 = iq.get_candles(pair, 300, 50, time.time())
            if c2 and len(c2) > 20:
                return pd.DataFrame(sorted(c2, key=lambda x: x["from"]))
            time.sleep(0.4)
        except:
            time.sleep(0.4)
    return None
def calc_rsi(closes, period=7):
    delta = closes.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
def calc_atr(df, period=14):
    try:
        high = df["max"]
        low = df["min"]
        close = df["close"]
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(period).mean().iloc[-1]
    except:
        return 0.0005
def calc_adx_v12(df, period=14):
    try:
        high = df["max"]
        low = df["min"]
        close = df["close"]
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        up = high - high.shift()
        down = low.shift() - low
        plus_dm = ((up > down) & (up > 0)) * up
        minus_dm = ((down > up) & (down > 0)) * down
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
        adx = dx.rolling(period).mean().iloc[-1]
        return float(adx), float(plus_di.iloc[-1]), float(minus_di.iloc[-1])
    except:
        return 0, 0, 0
def get_trend_and_expiry(df, df5, close, r7, r14, adx, macd_val, sig_val, mom1, mom3, stoch_val, c_now, upper, lower, is_green):
    trends = []
    trend_score = 0
    e9 = float(close.ewm(9).mean().iloc[-1])
    e21 = float(close.ewm(21).mean().iloc[-1])
    e50 = float(close.ewm(50).mean().iloc[-1])
    if e9 > e21 > e50:
        trends.append("📈 EMA Strong Uptrend")
        trend_score += 2
    elif e9 < e21 < e50:
        trends.append("📉 EMA Strong Downtrend")
        trend_score += 2
    elif e9 > e21:
        trends.append("↗️ EMA Weak Uptrend")
        trend_score += 1
    elif e9 < e21:
        trends.append("↘️ EMA Weak Downtrend")
        trend_score += 1
    else:
        trends.append("➡️ EMA Flat")
    if df5 is not None:
        c5 = df5["close"]
        e9_5 = float(c5.ewm(9).mean().iloc[-1])
        e21_5 = float(c5.ewm(21).mean().iloc[-1])
        if e9_5 > e21_5:
            trends.append("📈 5M Uptrend")
        else:
            trends.append("📉 5M Downtrend")
        if (is_green and e9_5 > e21_5) or (not is_green and e9_5 < e21_5):
            trends.append("✅ 1M + 5M AGREE")
            trend_score += 3
        else:
            trends.append("⚠️ 1M vs 5M CONFLICT")
            trend_score -= 2
    if adx >= 35:
        trends.append("💪 ADX Very Strong {:.0f}".format(adx))
        trend_score += 3
    elif adx >= 28:
        trends.append("🔥 ADX Strong {:.0f}".format(adx))
        trend_score += 2
    elif adx >= 25:
        trends.append("👍 ADX OK {:.0f}".format(adx))
        trend_score += 1
    else:
        trends.append("😴 ADX Weak {:.0f}".format(adx))
    if macd_val > sig_val:
        trends.append("📈 MACD Bullish")
        trend_score += 1
    else:
        trends.append("📉 MACD Bearish")
        trend_score += 1
    if trend_score >= 7:
        expiry = 300
        expiry_txt = "5 Min - STRONG TREND"
        trend_type = "🔥 STRONG TREND"
    elif trend_score >= 5:
        expiry = 180
        expiry_txt = "3 Min - GOOD TREND"
        trend_type = "📈 GOOD TREND"
    elif trend_score >= 3:
        expiry = 120
        expiry_txt = "2 Min - NORMAL TREND"
        trend_type = "➡️ NORMAL TREND"
    elif trend_score >= 1:
        expiry = 60
        expiry_txt = "1 Min - WEAK"
        trend_type = "😴 WEAK / RANGING"
    else:
        expiry = 60
        expiry_txt = "1 Min - CONFLICT"
        trend_type = "⚠️ CONFLICT TREND"
    return {"trends": trends, "trend_score": trend_score, "expiry": expiry, "expiry_txt": expiry_txt, "trend_type": trend_type}

def analyze_sniper_v12(pair, sniper_mode=False):
    df = get_candles(pair)
    if df is None:
        return None
    try:
        df5 = None
        try:
            logging.disable(logging.CRITICAL)
            c5 = iq.get_candles(pair, 300, 50, time.time())
            if c5 and len(c5) > 20:
                df5 = pd.DataFrame(sorted(c5, key=lambda x: x["from"]))
        except:
            df5 = None
        close = df["close"]
        open_ = df["open"]
        high = df["max"]
        low = df["min"]
        ema9 = close.ewm(9).mean()
        ema21 = close.ewm(21).mean()
        ema50 = close.ewm(50).mean()
        rsi7 = calc_rsi(close, 7)
        rsi14 = calc_rsi(close, 14)
        atr = calc_atr(df, 14)
        adx, pdi, mdi = calc_adx_v12(df)
        ema12 = close.ewm(12).mean()
        ema26 = close.ewm(26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(9).mean()
        macd_val = float(macd.iloc[-1])
        sig_val = float(signal.iloc[-1])
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper = float((sma20 + 2 * std20).iloc[-1])
        lower = float((sma20 - 2 * std20).iloc[-1])
        low14 = low.rolling(14).min()
        high14 = high.rolling(14).max()
        stoch = 100 * (close - low14) / (high14 - low14)
        stoch_val = float(stoch.iloc[-1])
        c_now = float(close.iloc[-1])
        o_now = float(open_.iloc[-1])
        c_prev = float(close.iloc[-2])
        o_prev = float(open_.iloc[-2])
        h_now = float(high.iloc[-1])
        l_now = float(low.iloc[-1])
        e9 = float(ema9.iloc[-1])
        e21 = float(ema21.iloc[-1])
        e50 = float(ema50.iloc[-1])
        r7 = float(rsi7.iloc[-1])
        r14 = float(rsi14.iloc[-1])
        mom1 = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100
        mom3 = (close.iloc[-1] - close.iloc[-4]) / close.iloc[-4] * 100
        body = abs(c_now - o_now)
        upper_wick = h_now - max(c_now, o_now)
        lower_wick = min(c_now, o_now) - l_now
        is_green = c_now > o_now
        payout = get_payout(pair)
        if is_green:
            sig = "CALL"
        else:
            sig = "PUT"
        if is_pair_blocked(pair):
            return {"pair": pair, "dir": sig, "conf": 40, "price": c_now, "rsi": r7, "reason": "🧠 BRAIN Blocked", "payout": payout, "expiry": 120, "atr": atr, "rejected": True}
        news_block = is_news_blocking_pair(pair, minutes=30)
        if news_block:
            nb_title = news_block["title"]
            nb_in = news_block["in_min"]
            return {"pair": pair, "dir": sig, "conf": 40, "price": c_now, "rsi": r7, "reason": "📰 NEWS BLOCK " + str(nb_in) + "min " + nb_title[:25], "payout": payout, "expiry": 120, "atr": atr, "rejected": True}
        if adx < 25:
            return {"pair": pair, "dir": sig, "conf": 42, "price": c_now, "rsi": r7, "reason": "Choppy - ADX Low", "payout": payout, "expiry": 120, "atr": atr, "rejected": True}
        if body < atr * 0.30:
            return {"pair": pair, "dir": sig, "conf": 48, "price": c_now, "rsi": r7, "reason": "Doji - No Body", "payout": payout, "expiry": 120, "atr": atr, "rejected": True}
        if payout < 0.80:
            return {"pair": pair, "dir": sig, "conf": 52, "price": c_now, "rsi": r7, "reason": "Low Payout", "payout": payout, "expiry": 120, "atr": atr, "rejected": True}
        score = 30
        reasons = []
        if df5 is not None:
            c5 = df5["close"]
            e9_5 = c5.ewm(9).mean()
            e21_5 = c5.ewm(21).mean()
            if float(e9_5.iloc[-1]) > float(e21_5.iloc[-1]):
                trend_5m = 1
            else:
                trend_5m = -1
            if (is_green and trend_5m == -1) or (not is_green and trend_5m == 1):
                return {"pair": pair, "dir": sig, "conf": 45, "price": c_now, "rsi": r7, "reason": "Against 5M Trend", "payout": payout, "expiry": 120, "atr": atr, "rejected": True}
            else:
                score += 12
                reasons.append("5M Trend Align")
        else:
            return {"pair": pair, "dir": sig, "conf": 45, "price": c_now, "rsi": r7, "reason": "No 5M Data", "payout": payout, "expiry": 120, "atr": atr, "rejected": True}
        if is_green:
            if e9 > e21 > e50:
                score += 18
                reasons.append("EMA Bull Align")
            elif e9 > e21:
                score += 10
            else:
                score -= 8
        else:
            if e9 < e21 < e50:
                score += 18
                reasons.append("EMA Bear Align")
            elif e9 < e21:
                score += 10
            else:
                score -= 8
        if adx >= 28:
            score += 12
            reasons.append("ADX Strong {:.0f}".format(adx))
        elif adx >= 22:
            score += 7
        if is_green and pdi > mdi:
            score += 8
        elif not is_green and mdi > pdi:
            score += 8
        else:
            score -= 10
        if is_green:
            if 52 <= r7 <= 65 and 48 <= r14 <= 62:
                score += 15
                reasons.append("RSI Safe {:.0f}".format(r7))
            elif r7 > 75 or r7 < 45:
                score -= 12
            else:
                score += 6
        else:
            if 35 <= r7 <= 48 and 38 <= r14 <= 52:
                score += 15
                reasons.append("RSI Safe {:.0f}".format(r7))
            elif r7 < 25 or r7 > 55:
                score -= 12
            else:
                score += 6
        if is_green and macd_val > sig_val:
            score += 10
            reasons.append("MACD Bull")
        elif not is_green and macd_val < sig_val:
            score += 10
            reasons.append("MACD Bear")
        else:
            score -= 8
        if is_green:
            if mom1 > 0.03 and mom3 > 0.06:
                score += 12
                reasons.append("Mom {:.3f}%".format(mom1))
            elif mom1 > 0.01:
                score += 5
            elif mom1 < 0:
                score -= 12
        else:
            if mom1 < -0.03 and mom3 < -0.06:
                score += 12
                reasons.append("Mom {:.3f}%".format(mom1))
            elif mom1 < -0.01:
                score += 5
            elif mom1 > 0:
                score -= 12
        bull_eng = c_now > o_prev and o_now < c_prev and is_green and c_prev < o_prev
        bear_eng = c_now < o_prev and o_now > c_prev and not is_green and c_prev > o_prev
        pin_bull = lower_wick > body * 1.8 and lower_wick > upper_wick * 1.5 and is_green
        pin_bear = upper_wick > body * 1.8 and upper_wick > lower_wick * 1.5 and not is_green
        has_pattern = False
        if is_green:
            if bull_eng:
                score += 10
                reasons.append("Bull Engulf")
                has_pattern = True
            if pin_bull:
                score += 10
                reasons.append("Pin Bull")
                has_pattern = True
        else:
            if bear_eng:
                score += 10
                reasons.append("Bear Engulf")
                has_pattern = True
            if pin_bear:
                score += 10
                reasons.append("Pin Bear")
                has_pattern = True
        if is_green and stoch_val > 85:
            score -= 12
        if not is_green and stoch_val < 15:
            score -= 12
        if is_green and 50 < stoch_val < 80:
            score += 5
        if not is_green and 20 < stoch_val < 50:
            score += 5
        if is_green and c_now > upper:
            score -= 10
        if not is_green and c_now < lower:
            score -= 10
        if not has_pattern and score < 88:
            return {"pair": pair, "dir": sig, "conf": score, "price": c_now, "rsi": r7, "reason": "No Pattern", "payout": payout, "expiry": 120, "atr": atr, "rejected": True}
        session_boost, session_name = get_session_boost(pair)
        score += session_boost
        if session_boost != 0:
            reasons.append(session_name + " {:+d}".format(session_boost))
        if session_boost <= -10 and sniper_mode and score < 92:
            return {"pair": pair, "dir": sig, "conf": score, "price": c_now, "rsi": r7, "reason": session_name + " Needs 92%", "payout": payout, "expiry": 120, "atr": atr, "rejected": True}
        hour_boost, hour_txt = get_hour_boost(pair)
        if hour_boost != 0:
            score += hour_boost
            reasons.append(hour_txt + " {:+d}".format(hour_boost))
            if hour_boost <= -10 and sniper_mode and score < 92:
                return {"pair": pair, "dir": sig, "conf": score, "price": c_now, "rsi": r7, "reason": "Bad Hour", "payout": payout, "expiry": 120, "atr": atr, "rejected": True}
        rsi_boost, rsi_txt = get_pair_rsi_boost(pair, r7, is_green)
        if rsi_boost != 0:
            score += rsi_boost
            reasons.append(rsi_txt + " {:+d}".format(rsi_boost))
        brain = get_pair_stats(pair)
        boost = brain.get("score_boost", 0)
        score += boost
        if boost != 0:
            reasons.append("Brain {:+d}".format(boost))
        if boost <= -8 and sniper_mode and score < 92:
            return {"pair": pair, "dir": sig, "conf": score, "price": c_now, "rsi": r7, "reason": "Weak pair needs 92%", "payout": payout, "expiry": 120, "atr": atr, "rejected": True}
        if score < 40:
            score = 40
        if score > 96:
            score = 96
        reason = " + ".join(reasons) if reasons else "Weak PA"
        if sniper_mode and score < 88:
            return {"pair": pair, "dir": sig, "conf": score, "price": c_now, "rsi": r7, "reason": reason, "payout": payout, "expiry": 120, "atr": atr, "rejected": True}
        trend_info = get_trend_and_expiry(df, df5, close, r7, r14, adx, macd_val, sig_val, mom1, mom3, stoch_val, c_now, upper, lower, is_green)
        reason = reason + " | " + trend_info["trend_type"] + " | " + trend_info["expiry_txt"]
        return {"pair": pair, "dir": sig, "conf": score, "price": c_now, "rsi": r7, "reason": reason, "payout": payout, "expiry": trend_info["expiry"], "atr": atr, "rejected": False, "adx": adx, "trend_info": trend_info}
    except Exception as e:
        print("V18 err " + pair + " " + str(e))
        return None

def check_pullback_entry(pair, original_dir):
    if is_news_blocking_pair(pair, minutes=30):
        return None
    df = get_candles(pair)
    if df is None:
        return None
    try:
        close = df["close"]
        ema9 = close.ewm(9).mean()
        ema21 = close.ewm(21).mean()
        rsi7 = calc_rsi(close, 7)
        rsi14 = calc_rsi(close, 14)
        r7 = float(rsi7.iloc[-1])
        r7_prev = float(rsi7.iloc[-2])
        r14 = float(rsi14.iloc[-1])
        c_now = float(close.iloc[-1])
        e9 = float(ema9.iloc[-1])
        e21 = float(ema21.iloc[-1])
        payout = get_payout(pair)
        near_ema = abs(c_now - e9) / c_now * 100 < 0.05 or abs(c_now - e21) / c_now * 100 < 0.05
        if not near_ema or payout < 0.80:
            return None
        if original_dir == "CALL":
            if 40 <= r7 <= 55 and 42 <= r14 <= 58 and r7 > r7_prev and c_now > e21:
                return {"pair": pair, "dir": "CALL", "conf": 88, "price": c_now, "rsi": r7, "reason": "Pullback CALL RSI {:.0f}".format(r7), "payout": payout, "expiry": 120, "atr": 0, "rejected": False}
        else:
            if 45 <= r7 <= 60 and 42 <= r14 <= 58 and r7 < r7_prev and c_now < e21:
                return {"pair": pair, "dir": "PUT", "conf": 88, "price": c_now, "rsi": r7, "reason": "Pullback PUT RSI {:.0f}".format(r7), "payout": payout, "expiry": 120, "atr": 0, "rejected": False}
        return None
    except:
        return None

def pullback_scanner_loop(cid, pair, original_dir):
    start = time.time()
    PULLBACK_STATE[cid] = {"pair": pair, "dir": original_dir, "active": True}
    is_user_pullback = cid != OWNER_ID
    if is_user_pullback:
        bot.send_message(cid, "🔍 **YOUR Pullback Scan ON**\n\n💱 " + pair + " looking for " + original_dir + " pullback for YOU only\n📊 Scanning every 10 sec...\n⏳ Timeout 5 min\n\nPress ✅ MY WIN / ❌ MY LOSS / ⏭️ SKIP")
    else:
        bot.send_message(cid, "🔍 **Pullback Scan ON**\n\n💱 " + pair + " looking for " + original_dir + " pullback\n📊 Scanning every 10 sec...\n⏳ Timeout 5 min\n\nPress ✅ WIN / ❌ LOSS / ⏭️ SKIP")
    while PULLBACK_STATE.get(cid, {}).get("active") and time.time() - start < 300:
        if check_and_reset_new_day():
            bot.send_message(cid, "🔄 New day started - pullback stopped")
            PULLBACK_STATE[cid]["active"] = False
            return
        if not is_user_pullback and not can_trade_today():
            bot.send_message(cid, "⛔ Max 30 trades reached today")
            PULLBACK_STATE[cid]["active"] = False
            return
        d = check_pullback_entry(pair, original_dir)
        if d:
            levels = [1, 2, 4, 8]
            dd = d["dir"]
            reason = d["reason"]
            payout = d["payout"]
            if is_user_pullback:
                idx = get_user_data(cid)["marti_streak"]
                if idx >= 4:
                    idx = 0
                mult = levels[idx]
                amt = 1.0 * mult
                names = ["Real Entry","Martingale 1","Martingale 2","Martingale 3"]
                mk = types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton("✅ MY WIN", callback_data="user_win_" + pair), types.InlineKeyboardButton("❌ MY LOSS", callback_data="user_loss_" + pair + "_" + dd))
                mk.add(types.InlineKeyboardButton("⏭️ SKIP", callback_data="user_skip_" + pair))
                msg = "🎯 **YOUR PULLBACK ENTRY FOUND!**\n\n💱 " + pair + "\n📊 " + dd + " | " + reason + "\n💰 Next: **" + names[idx] + " - ${:.2f} Level {}/4 ({}x)**\n⏱️ Enter NOW - 2 Min".format(amt, idx+1, mult)
                bot.send_message(cid, msg, parse_mode="Markdown", reply_markup=mk)
            else:
                idx = OTC_MARTI["loss_streak"]
                mult = OTC_MARTI["levels"][idx]
                amt = OTC_MARTI["base"] * mult
                names = ["Real Entry","Martingale 1","Martingale 2","Martingale 3"]
                mk = types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton("✅ WIN", callback_data="manual_win_" + pair), types.InlineKeyboardButton("❌ LOSS", callback_data="manual_loss_" + pair + "_" + dd))
                mk.add(types.InlineKeyboardButton("⏭️ SKIP THIS TRADE", callback_data="skip_" + pair))
                mk.add(types.InlineKeyboardButton("📤 Send to Channel", callback_data="send_channel_pb_" + pair + "_" + dd))
                mk.add(types.InlineKeyboardButton("📤👥 Send to Both Me + Users", callback_data="send_both_pb_" + pair + "_" + dd))
                msg = "🎯 **PULLBACK ENTRY FOUND!**\n\n💱 " + pair + "\n📊 " + dd + " | " + reason + "\n💸 Payout {:.0f}%\n💰 Next: **".format(payout*100) + names[idx] + " - ${:.2f} Level {}/4**\n⏱️ Enter NOW - 2 Min".format(amt, idx+1)
                bot.send_message(cid, msg, parse_mode="Markdown", reply_markup=mk)
            PULLBACK_STATE[cid]["active"] = False
            return
        time.sleep(10)
    PULLBACK_STATE[cid] = {"active": False}
    bot.send_message(cid, "⏱️ Pullback scan timeout (5 min) - No safe entry.")

def daily_summary_loop():
    global DAILY_SUMMARY_SENT
    tz = pytz.timezone("Africa/Lagos")
    while True:
        try:
            now = datetime.now(tz)
            today_str = now.strftime("%Y-%m-%d")
            if now.hour == 20 and now.minute < 5 and DAILY_SUMMARY_SENT != today_str:
                DAILY_SUMMARY_SENT = today_str
                total = STATS["wins"] + STATS["loss"]
                if total:
                    wr = STATS["wins"] / total * 100
                else:
                    wr = 0
                msg = "📊 **DAILY SUMMARY - " + today_str + "** 📊\n\n🕗 Trading closed (8PM)\n\n🏆 Wins: " + str(STATS["wins"]) + "\n❌ Losses: " + str(STATS["loss"]) + "\n📈 Win Rate: {:.1f}%\n".format(wr)
                msg += "📅 Trades Today: " + str(STATS["daily_trades"]) + "/30\n\n🌙 Rest well Trailblazer! 💰"
                try:
                    bot.send_message(OWNER_ID, msg, parse_mode="Markdown")
                except:
                    pass
            time.sleep(60)
        except:
            time.sleep(60)

def trailblazer_market_scanner():
    tz = pytz.timezone("Africa/Lagos")
    last_news_alert = 0
    while True:
        try:
            if not is_real_hours() or not IQ_CONNECTED:
                time.sleep(60)
                continue
            news = get_upcoming_news()
            urgent_news = [n for n in news if 0 <= n["in_min"] <= 30]
            if urgent_news and time.time() - last_news_alert > 3600:
                last_news_alert = time.time()
                news_txt = format_news_alert(urgent_news)
                msg = "📰📰📰 **TRAILBLAZER NEWS ALERT** 📰📰📰\n\n" + get_greeting() + "\n\n⚠️ **HIGH IMPACT NEWS COMING!** ⚠️\n\n" + news_txt + "🚨 No trade pairs with that currency now\n⏳ Wait 15 min AFTER news"
                try:
                    bot.send_message(OWNER_ID, msg, parse_mode="Markdown")
                except:
                    pass
            if time.time() - MARKET_GOOD_SENT["last_alert"] < 2700:
                time.sleep(60)
                continue
            if is_signal_active():
                time.sleep(60)
                continue
            good_pairs = 0
            strong_pairs = []
            for pair in ["EURUSD","GBPUSD","EURGBP","AUDUSD","USDCAD"]:
                if is_pair_blocked(pair):
                    continue
                if is_news_blocking_pair(pair, minutes=30):
                    continue
                try:
                    df = get_candles(pair)
                    if df is None:
                        continue
                    adx, _, _ = calc_adx_v12(df)
                    payout = get_payout(pair)
                    if adx >= 25 and payout >= 0.80:
                        good_pairs += 1
                        strong_pairs.append(pair)
                except:
                    pass
                time.sleep(1)
            if urgent_news and good_pairs < 5:
                time.sleep(300)
                continue
            if good_pairs >= 5:
                MARKET_GOOD_SENT["last_alert"] = time.time()
                greet = get_greeting()
                pairs_txt = " • ".join(strong_pairs[:5])
                sb2, sn2 = get_session_boost("EURUSD")
                msg = "🔥🔥🔥 **TRAILBLAZER MARKET IS GOOD** 🔥🔥🔥\n\n" + greet + "\n\n🚀 **SIGNALS COMING SOON - GET READY** 💰💰💰\n\n📊 Market Check:\n✅ " + str(good_pairs) + "/5 Major Pairs Strong\n✅ ADX 25+ - Market moving\n✅ Payout 80%+\n💱 Hot Pairs: " + pairs_txt + "\n⏰ Session: " + sn2 + "\n\n💪 Get IQ Option ready!\n💰 **IT IS TIME TO EARN!** 🚀🚀🚀"
                try:
                    bot.send_message(OWNER_ID, msg, parse_mode="Markdown")
                except:
                    pass
            time.sleep(300)
        except:
            time.sleep(60)

def morning_greet_loop():
    global MORNING_GREET_SENT
    tz = pytz.timezone("Africa/Lagos")
    while True:
        try:
            now = datetime.now(tz)
            today = now.strftime("%Y-%m-%d")
            if now.hour == 7 and now.minute < 5 and MORNING_GREET_SENT != today:
                MORNING_GREET_SENT = today
                msg = "🌅🌅🌅 **GOOD MORNING TRAILBLAZER** 🌅🌅🌅\n\n☀️ Rise and shine! 7AM - Market opened!\n\n💰 **New day, new money!** 💰\n\n📊 Today: Bot scanning 15 REAL + GOLD, 88%+ only, Max 30\n\n🔥 **LET US EARN TODAY!** 🚀💰🔥"
                try:
                    bot.send_message(OWNER_ID, msg, parse_mode="Markdown")
                except:
                    pass
            time.sleep(60)
        except:
            time.sleep(60)

def analyze_xauusd():
    pair = "XAUUSD"
    df = get_candles(pair)
    if df is None:
        return None
    try:
        df5 = None
        try:
            logging.disable(logging.CRITICAL)
            c5 = iq.get_candles(pair, 300, 50, time.time())
            if c5 and len(c5) > 20:
                df5 = pd.DataFrame(sorted(c5, key=lambda x: x["from"]))
        except:
            df5 = None
        close = df["close"]
        open_ = df["open"]
        ema9 = close.ewm(9).mean()
        ema21 = close.ewm(21).mean()
        ema50 = close.ewm(50).mean()
        rsi7 = calc_rsi(close, 7)
        rsi14 = calc_rsi(close, 14)
        atr = calc_atr(df, 14)
        adx, pdi, mdi = calc_adx_v12(df)
        ema12 = close.ewm(12).mean()
        ema26 = close.ewm(26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(9).mean()
        macd_val = float(macd.iloc[-1])
        sig_val = float(signal.iloc[-1])
        c_now = float(close.iloc[-1])
        o_now = float(open_.iloc[-1])
        e9 = float(ema9.iloc[-1])
        e21 = float(ema21.iloc[-1])
        e50 = float(ema50.iloc[-1])
        r7 = float(rsi7.iloc[-1])
        mom1 = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100
        is_green = c_now > o_now
        payout = get_payout(pair)
        if is_green:
            sig = "CALL"
        else:
            sig = "PUT"
        if is_pair_blocked(pair):
            return None
        if is_news_blocking_pair(pair, minutes=30):
            return None
        if adx < 25:
            return None
        if payout < 0.80:
            return None
        score = 30
        reasons = []
        if df5 is not None:
            c5 = df5["close"]
            e9_5 = c5.ewm(9).mean()
            e21_5 = c5.ewm(21).mean()
            if float(e9_5.iloc[-1]) > float(e21_5.iloc[-1]):
                trend_5m = 1
            else:
                trend_5m = -1
            if (is_green and trend_5m == -1) or (not is_green and trend_5m == 1):
                return None
            else:
                score += 12
                reasons.append("5M Align")
        else:
            return None
        if is_green:
            if e9 > e21 > e50:
                score += 18
                reasons.append("EMA Bull")
            elif e9 > e21:
                score += 10
            else:
                score -= 8
        else:
            if e9 < e21 < e50:
                score += 18
                reasons.append("EMA Bear")
            elif e9 < e21:
                score += 10
            else:
                score -= 8
        if adx >= 28:
            score += 12
            reasons.append("ADX {:.0f}".format(adx))
        elif adx >= 22:
            score += 7
        if is_green and pdi > mdi:
            score += 8
        elif not is_green and mdi > pdi:
            score += 8
        else:
            score -= 10
        if is_green:
            if 52 <= r7 <= 65:
                score += 15
                reasons.append("RSI {:.0f}".format(r7))
            elif r7 > 75 or r7 < 45:
                score -= 12
            else:
                score += 6
        else:
            if 35 <= r7 <= 48:
                score += 15
                reasons.append("RSI {:.0f}".format(r7))
            elif r7 < 25 or r7 > 55:
                score -= 12
            else:
                score += 6
        if is_green and macd_val > sig_val:
            score += 10
            reasons.append("MACD Bull")
        elif not is_green and macd_val < sig_val:
            score += 10
            reasons.append("MACD Bear")
        else:
            score -= 8
        if is_green and mom1 > 0.03:
            score += 12
        elif not is_green and mom1 < -0.03:
            score += 12
        elif (is_green and mom1 < 0) or (not is_green and mom1 > 0):
            score -= 12
        session_boost, session_name = get_session_boost(pair)
        score += session_boost
        hour_boost, _ = get_hour_boost(pair)
        score += hour_boost
        brain = get_pair_stats(pair)
        score += brain.get("score_boost", 0)
        if score < 40:
            score = 40
        if score > 96:
            score = 96
        if score < 88:
            return None
        entry = c_now
        sl_dist = float(atr) * 1.5
        if sig == "CALL":
            sl = entry - sl_dist
            tp1 = entry + sl_dist
            tp2 = entry + (sl_dist * 2)
        else:
            sl = entry + sl_dist
            tp1 = entry - sl_dist
            tp2 = entry - (sl_dist * 2)
        return {"pair": pair, "dir": sig, "conf": score, "price": entry, "rsi": r7, "reason": " + ".join(reasons), "payout": payout, "atr": float(atr), "adx": adx, "sl": sl, "tp1": tp1, "tp2": tp2, "session": session_name}
    except Exception as e:
        print("XAU err " + str(e))
        return None

def xauusd_signal_scanner():
    tz = pytz.timezone("Africa/Lagos")
    last_xau = 0
    while True:
        try:
            check_and_reset_new_day()
            if is_signal_active():
                time.sleep(15)
                continue
            if time.time() - LAST_GLOBAL_SIGNAL["time"] < GLOBAL_COOLDOWN:
                time.sleep(30)
                continue
            if is_real_hours() and IQ_CONNECTED:
                if not can_trade_today():
                    time.sleep(60)
                    continue
                if time.time() - last_xau < 600:
                    time.sleep(30)
                    continue
                d = analyze_xauusd()
                if d:
                    now = datetime.now(tz)
                    entry_time = now + timedelta(seconds=45)
                    dir_ = d["dir"]
                    conf = d["conf"]
                    reason = d["reason"]
                    rsi_v = d["rsi"]
                    atr_v = d["atr"]
                    sess = d["session"]
                    price = d["price"]
                    sl = d["sl"]
                    tp1 = d["tp1"]
                    tp2 = d["tp2"]
                    payout = d["payout"]
                    adx_v = d["adx"]
                    if dir_ == "CALL":
                        dir_e = "🟢 BUY ⬆️"
                    else:
                        dir_e = "🔴 SELL ⬇️"
                    base = OTC_MARTI["base"]
                    mk = types.InlineKeyboardMarkup(row_width=2)
                    mk.add(types.InlineKeyboardButton("✅ WIN - Reset", callback_data="manual_win_XAUUSD"), types.InlineKeyboardButton("❌ LOSS - Pullback Scan", callback_data="manual_loss_XAUUSD_" + dir_))
                    mk.add(types.InlineKeyboardButton("⏭️ SKIP THIS TRADE", callback_data="skip_XAUUSD"))
                    mk.add(types.InlineKeyboardButton("📤 Send to Channel", callback_data="send_channel_XAUUSD_" + dir_))
                    mk.add(types.InlineKeyboardButton("📤👥 Send to Both Me + Users", callback_data="send_both_XAUUSD_" + dir_))
                    msg = "🥇🥇🥇 **XAU/USD GOLD SIGNAL** 🥇🥇🥇\n\n" + dir_e + " | {:.0f}% SNIPER GOLD\n".format(conf)
                    msg += "📈 " + reason + " | RSI {:.1f} | ATR {:.2f}\n".format(rsi_v, atr_v)
                    msg += "⏰ Session: " + sess + "\n📰 News: ✅ Checked\n📅 Today: " + str(STATS["daily_trades"]) + "/30\n\n"
                    msg += "━━━━━━━━━━━━━━━━━━\n⏰ ENTRY TIME: " + entry_time.strftime("%H:%M:%S WAT") + "\n"
                    msg += "💰 ENTRY: {:.2f}\n🛑 SL: {:.2f}\n🎯 TP1: {:.2f}\n🎯 TP2: {:.2f}\n".format(price, sl, tp1, tp2)
                    msg += "━━━━━━━━━━━━━━━━━━\n\n💵 **Stake:** ${:.2f}\n".format(base)
                    msg += "💸 Payout: {:.0f}%\n\n⚠️ MANUAL - Press WIN / LOSS / SKIP".format(payout*100)
                    bot.send_message(OWNER_ID, msg, parse_mode="Markdown", reply_markup=mk)
                    if AUTO_SEND_90 and conf >= 90:
                        send_signal_to_users("XAUUSD", dir_, msg)
                    last_xau = time.time()
                    LAST_GLOBAL_SIGNAL["time"] = time.time()
                    start_signal("XAUUSD", dir_, conf, rsi_v, adx_v, price=price, sl=sl, tp1=tp1, tp2=tp2)
            time.sleep(25)
        except:
            time.sleep(30)

def real_signal_scanner():
    last_signal = {}
    tz = pytz.timezone("Africa/Lagos")
    while True:
        try:
            check_and_reset_new_day()
            if is_signal_active():
                time.sleep(15)
                continue
            if time.time() - LAST_GLOBAL_SIGNAL["time"] < GLOBAL_COOLDOWN:
                time.sleep(30)
                continue
            if is_real_hours() and IQ_CONNECTED:
                if not can_trade_today():
                    time.sleep(60)
                    continue
                candidates = []
                for pair in REAL_PAIRS:
                    if is_pair_blocked(pair):
                        continue
                    if pair in last_signal and time.time() - last_signal[pair] < 600:
                        continue
                    d = analyze_sniper_v12(pair, sniper_mode=True)
                    if d and not d.get("rejected") and d["conf"] >= 88:
                        candidates.append((pair, d))
                    time.sleep(3)
                if candidates:
                    candidates.sort(key=lambda x: x[1]["conf"], reverse=True)
                    pair, d = candidates[0]
                    now = datetime.now(tz)
                    entry = now + timedelta(seconds=45)
                    dir_ = d["dir"]
                    conf = d["conf"]
                    reason = d["reason"]
                    rsi_v = d["rsi"]
                    atr_v = d["atr"]
                    payout = d["payout"]
                    adx_v = d.get("adx", 30)
                    expiry_v = d.get("expiry", 120)
                    ti = d.get("trend_info", {})
                    expiry_min = ti.get("expiry", 120) // 60
                    trend_type_txt = ti.get("trend_type", "➡️ NORMAL TREND")
                    trends_txt = " | ".join(ti.get("trends", [])[:4])
                    if dir_ == "CALL":
                        dir_e = "🟢 CALL ⬆️"
                    else:
                        dir_e = "🔴 PUT ⬇️"
                    base = OTC_MARTI["base"]
                    pair_label = PAIR_EMOJI.get(pair, pair)
                    mk = types.InlineKeyboardMarkup(row_width=2)
                    mk.add(types.InlineKeyboardButton("✅ WIN - Reset", callback_data="manual_win_" + pair), types.InlineKeyboardButton("❌ LOSS - Pullback Scan", callback_data="manual_loss_" + pair + "_" + dir_))
                    mk.add(types.InlineKeyboardButton("⏭️ SKIP THIS TRADE", callback_data="skip_" + pair))
                    mk.add(types.InlineKeyboardButton("📤 Send to Channel", callback_data="send_channel_" + pair + "_" + dir_))
                    mk.add(types.InlineKeyboardButton("📤👥 Send to Both Me + Users", callback_data="send_both_" + pair + "_" + dir_))
                    wr = get_pair_winrate(pair)
                    if wr is not None:
                        wr_txt = " | 🧠 Brain WR {:.0f}%".format(wr)
                    else:
                        wr_txt = ""
                    msg = "📡 **REAL SIGNAL V18 TRAILBLAZER - MANUAL** 📡\n\n💱 " + pair_label + "\n📊 " + dir_e + " | 🎯 {:.0f}% SNIPER".format(conf) + wr_txt + "\n"
                    msg += "📈 " + reason + " | RSI {:.1f} | ATR {:.5f}\n".format(rsi_v, atr_v)
                    msg += "📊 Trend: " + trend_type_txt + "\n🔍 Trends: " + trends_txt + "\n"
                    msg += "💸 {:.0f}% | ⏱️ Suggested: {} Min\n".format(payout*100, expiry_min)
                    msg += "📅 Today: " + str(STATS["daily_trades"]) + "/30\n📰 News: ✅ Checked\n\n"
                    msg += "⏰ ENTRY: " + entry.strftime("%H:%M:%S WAT") + " (in 45s)\n\n"
                    msg += "**Real Entry:** ${:.2f}\n**Marti 1:** ${:.2f} | **Marti 2:** ${:.2f} | **Marti 3:** ${:.2f}\n\n".format(base, base*2, base*4, base*8)
                    msg += "⚠️ MANUAL - Press WIN / LOSS / SKIP"
                    try:
                        bot.send_message(OWNER_ID, msg, parse_mode="Markdown", reply_markup=mk)
                        if AUTO_SEND_90 and conf >= 90:
                            send_signal_to_users(pair, dir_, msg)
                        last_signal[pair] = time.time()
                        LAST_GLOBAL_SIGNAL["time"] = time.time()
                        start_signal(pair, dir_, conf, rsi_v, adx_v, price=d["price"], expiry=expiry_v)
                    except Exception as e:
                        print("Send err " + str(e))
            time.sleep(25)
        except:
            time.sleep(30)

@bot.message_handler(content_types=["new_chat_members"])
def welcome_new_member(m):
    try:
        for member in m.new_chat_members:
            name = member.first_name or "Trader"
            bot.send_message(m.chat.id, "👋 Welcome " + name + " to Trailblazer Signals! 🔥\n\n🥇 Forex and GOLD Sniper Signals\n📈 88%+ Accuracy Only\n💰 Stake $1 - Follow Martingale\n📢 Channel: @KEVINTRAILBLAZE\n\nType /welcome to see rules.\nGood luck! 💪")
    except:
        pass

@bot.message_handler(commands=["start","help","stop","mode","balance","results","brain","news","welcome","intro","ready","add","remove","list","users","auto","auto90","autostop","autostart","userstats","mystats","myresults"])
def start(m):
    global AUTO_SEND_90
    txt_in = m.text or ""
    # --- HELP FOR BOTH ---
    if txt_in.startswith("/help"):
        if not is_allowed(m.from_user.id):
            bot.send_message(m.chat.id, "❌ Private - Ask admin to add you with /add")
            return
        if is_admin(m.from_user.id):
            bot.send_message(m.chat.id, "👑 ADMIN COMMANDS:\n\n➕ /add 123 - Add user\n➖ /remove 123 - Remove user\n👥 /list - List users\n📊 /userstats - All users stats\n🤖 /auto90 on/off - Auto 90+\n📢 /welcome /intro /ready - Send to Channel\n📍 /mode /brain /results")
        else:
            bot.send_message(m.chat.id, "🙋 YOUR COMMANDS:\n\n🚀 /start - Start\n❓ /help - Help\n📊 /mystats - YOUR wins/loss/next stake\n👋 /welcome - Rules\n📚 /intro - How to trade\n🚀 /ready - Get ready checklist\n\nAfter signal press:\n✅ MY WIN\n❌ MY LOSS\n⏭️ SKIP")
        return
    # --- MYSTATS USER ---
    if txt_in.startswith("/mystats") or txt_in.startswith("/myresults"):
        if not is_allowed(m.from_user.id):
            bot.send_message(m.chat.id, "❌ Private")
            return
        uid = str(m.from_user.id)
        u = get_user_data(uid)
        uw = u["wins"]
        ul = u["loss"]
        ustreak = u["streak"]
        udaily = u["daily_trades"]
        total = uw + ul
        if total:
            wr = uw / total * 100
        else:
            wr = 0
        levels = [1,2,4,8]
        idx = u["marti_streak"]
        if idx < 4:
            next_amt = 1.0 * levels[idx]
        else:
            next_amt = 1.0
        names = ["Real Entry $1","Martingale 1 - $2","Martingale 2 - $4","Martingale 3 - $8"]
        if idx < 4:
            next_txt = names[idx]
        else:
            next_txt = "Real Entry $1"
        txt = "📊 **MY RESULTS** 📊\n\n"
        txt += "🆔 Your ID: " + uid + "\n"
        txt += "🏆 Your Wins: " + str(uw) + "\n❌ Your Loss: " + str(ul) + "\n"
        txt += "📈 Your Win Rate: {:.1f}%\n".format(wr)
        txt += "🔥 Your Streak: " + str(ustreak) + "\n📅 Your Trades Today: " + str(udaily) + "\n"
        txt += "💵 Your Next Stake: " + next_txt + " (${:.2f})\n\n".format(next_amt)
        txt += "📊 **Your Pairs:**\n"
        if not u["pairs"]:
            txt += "No trades yet. Wait for signal and press MY WIN / MY LOSS."
        else:
            for pair, s in u["pairs"].items():
                pw = s["wins"]
                pl = s["loss"]
                t = pw + pl
                if t:
                    w = pw / t * 100
                else:
                    w = 0
                txt += "• " + pair + ": W" + str(pw) + " L" + str(pl) + " = {:.0f}%\n".format(w)
        bot.send_message(m.chat.id, txt, parse_mode="Markdown")
        return
    # --- USERSTATS ADMIN ---
    if txt_in.startswith("/userstats"):
        if not is_admin(m.from_user.id):
            bot.send_message(m.chat.id, "❌ Only admin. Use /mystats")
            return
        parts = txt_in.split()
        if len(parts) < 2:
            if not USER_DATA:
                bot.send_message(m.chat.id, "📭 No user data yet.")
                return
            txt = "👥 **ALL USERS STATS** 👥\n\n"
            for uid, u in USER_DATA.items():
                uw = u["wins"]
                ul = u["loss"]
                total = uw + ul
                if total:
                    wr = uw / total * 100
                else:
                    wr = 0
                lvl = u["marti_streak"] + 1
                txt += "🆔 " + uid + "\n🏆 W" + str(uw) + " ❌ L" + str(ul) + " = {:.0f}% | Next Level: {}/4\n\n".format(wr, lvl)
            txt += "Detail: /userstats 123456789"
            bot.send_message(m.chat.id, txt, parse_mode="Markdown")
            return
        target = parts[1].strip()
        if target not in USER_DATA:
            bot.send_message(m.chat.id, "📭 No data for " + target + " yet.")
            return
        u = USER_DATA[target]
        uw = u["wins"]
        ul = u["loss"]
        ustreak = u["streak"]
        udaily = u["daily_trades"]
        total = uw + ul
        if total:
            wr = uw / total * 100
        else:
            wr = 0
        levels = [1,2,4,8]
        idx = u["marti_streak"]
        if idx < 4:
            next_amt = 1.0 * levels[idx]
        else:
            next_amt = 1.0
        txt = "👤 **USER " + target + " STATS**\n\n"
        txt += "🏆 Wins: " + str(uw) + "\n❌ Loss: " + str(ul) + "\n"
        txt += "📈 Win Rate: {:.1f}%\n".format(wr)
        txt += "🔥 Streak: " + str(ustreak) + "\n📅 Trades: " + str(udaily) + "\n"
        txt += "💵 Next Stake: ${:.2f} (Level {}/4)\n\n".format(next_amt, idx+1)
        txt += "📊 **Pairs:**\n"
        if not u["pairs"]:
            txt += "No trades yet."
        else:
            for pair, s in u["pairs"].items():
                pw = s["wins"]
                pl = s["loss"]
                t = pw + pl
                if t:
                    w = pw / t * 100
                else:
                    w = 0
                txt += "• " + pair + ": W" + str(pw) + " L" + str(pl) + " = {:.0f}%\n".format(w)
        bot.send_message(m.chat.id, txt, parse_mode="Markdown")
        return
    # --- ADD / REMOVE / LIST ADMIN ---
    if txt_in.startswith("/add"):
        if not is_admin(m.from_user.id):
            bot.send_message(m.chat.id, "❌ Only admin can add")
            return
        try:
            new_id = int(txt_in.split()[1])
            ALLOWED_USERS.add(new_id)
            save_users()
            bot.send_message(m.chat.id, "✅ Added user " + str(new_id) + "\nTotal: " + str(len(ALLOWED_USERS)), parse_mode="Markdown")
            try:
                bot.send_message(new_id, "🔥 Welcome to TRAILBLAZER SIGNALS!\n\nYou have been added by admin. You go receive signals when admin send am.\n\nType /start to begin.")
            except:
                pass
        except:
            bot.send_message(m.chat.id, "Usage: /add 123456789")
        return
    if txt_in.startswith("/remove"):
        if not is_admin(m.from_user.id):
            bot.send_message(m.chat.id, "❌ Only admin")
            return
        try:
            rem_id = int(txt_in.split()[1])
            ALLOWED_USERS.discard(rem_id)
            save_users()
            bot.send_message(m.chat.id, "❌ Removed " + str(rem_id) + "\nTotal: " + str(len(ALLOWED_USERS)))
        except:
            bot.send_message(m.chat.id, "Usage: /remove 123456789")
        return
    if txt_in.startswith("/list") or txt_in.startswith("/users"):
        if not is_admin(m.from_user.id):
            bot.send_message(m.chat.id, "❌ Only admin")
            return
        if not ALLOWED_USERS:
            bot.send_message(m.chat.id, "📭 No users yet. Add with: /add 123456789")
        else:
            txt = "👥 **ADDED USERS:**\n\n"
            for u in ALLOWED_USERS:
                txt += "• " + str(u) + "\n"
            if AUTO_SEND_90:
                atxt = "✅ ON"
            else:
                atxt = "🛑 OFF"
            txt += "\nTotal: " + str(len(ALLOWED_USERS)) + "\nAuto 90+: " + atxt
            bot.send_message(m.chat.id, txt, parse_mode="Markdown")
        return
    if txt_in.startswith("/auto") or txt_in.startswith("/autostop") or txt_in.startswith("/autostart"):
        if not is_admin(m.from_user.id):
            bot.send_message(m.chat.id, "❌ Only admin")
            return
        low = txt_in.lower()
        if "off" in low or "stop" in low:
            AUTO_SEND_90 = False
            save_auto()
            bot.send_message(m.chat.id, "🛑 **AUTO SEND 90+ STOPPED**\n\nBot go send 90%+ to YOU ONLY.\nUsers go only get signal if you press 👥 Send to Both", parse_mode="Markdown")
        elif "on" in low or "start" in low:
            AUTO_SEND_90 = True
            save_auto()
            bot.send_message(m.chat.id, "✅ **AUTO SEND 90+ ON**\n\nBot go auto send 90%+ to YOU + ALL USERS.", parse_mode="Markdown")
        else:
            if AUTO_SEND_90:
                st = "✅ ON"
            else:
                st = "🛑 OFF"
            bot.send_message(m.chat.id, "🤖 **AUTO SEND 90+: " + st + "**\n\nCommands:\n/auto90 on - Turn ON\n/auto90 off - Turn OFF\n/autostop - Stop\n/autostart - Start", parse_mode="Markdown")
        return
    # --- WELCOME / INTRO / READY FOR BOTH ---
    if txt_in.startswith("/welcome"):
        if not is_allowed(m.from_user.id):
            bot.send_message(m.chat.id, WELCOME_TEXT)
            return
        if is_admin(m.from_user.id):
            send_photo_to_channel_sync(WELCOME_PHOTO, WELCOME_TEXT)
            bot.send_message(m.chat.id, "✅ Welcome sent to @KEVINTRAILBLAZE 📤📸")
        else:
            bot.send_message(m.chat.id, WELCOME_TEXT)
        return
    if txt_in.startswith("/intro"):
        if not is_allowed(m.from_user.id):
            bot.send_message(m.chat.id, INTRO_TEXT)
            return
        if is_admin(m.from_user.id):
            send_photo_to_channel_sync(INTRO_PHOTO, INTRO_TEXT)
            bot.send_message(m.chat.id, "✅ Intro sent to @KEVINTRAILBLAZE 📤📸")
        else:
            bot.send_message(m.chat.id, INTRO_TEXT)
        return
    if txt_in.startswith("/ready"):
        if not is_allowed(m.from_user.id):
            bot.send_message(m.chat.id, get_ready_text())
            return
        if is_admin(m.from_user.id):
            send_photo_to_channel_sync(READY_PHOTO, get_ready_text())
            bot.send_message(m.chat.id, "✅ Get Ready sent to @KEVINTRAILBLAZE 🚀📤")
        else:
            bot.send_message(m.chat.id, get_ready_text())
        return
    if not is_allowed(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Private")
        return
    if not is_admin(m.from_user.id):
        bot.send_message(m.chat.id, "👋 Welcome to TRAILBLAZER! You are added ✅\n\nWait for admin to send signals. You go receive am here automatically.\n\n📊 Type /mystats to see YOUR results.\n❓ Type /help to see your commands.")
        return
    if txt_in.startswith("/news"):
        news = get_upcoming_news()
        if not news:
            bot.send_message(m.chat.id, "📰 **NEWS CHECK**\n\n✅ No high impact news in next 2 hours - Clean market!\n🎯 Safe to trade all pairs.", parse_mode="Markdown")
            return
        txt = "📰 **UPCOMING NEWS - NEXT 2H**\n\n" + format_news_alert(news) + "⚠️ Bot is blocking these currencies."
        bot.send_message(m.chat.id, txt, parse_mode="Markdown")
        return
    if txt_in.startswith("/brain"):
        txt = "🧠 **AI BRAIN - PAIR LEARNING**\n\n"
        best = []
        bad = []
        for pair, s in PAIR_BRAIN.items():
            total = s["wins"] + s["loss"]
            if total >= 3:
                wr = s["wins"] / total * 100
                if is_pair_blocked(pair):
                    blk = " 🚫 BLOCKED"
                else:
                    blk = ""
                line = PAIR_EMOJI.get(pair, pair) + ": W" + str(s["wins"]) + " L" + str(s["loss"]) + " = {:.0f}%".format(wr) + blk + "\n"
                if wr >= 60:
                    best.append(line)
                elif wr < 50:
                    bad.append(line)
        txt += "🏆 **BEST PAIRS:**\n"
        if best:
            txt += "".join(best)
        else:
            txt += "Not enough data yet\n"
        txt += "\n💀 **BAD PAIRS:**\n"
        if bad:
            txt += "".join(bad)
        else:
            txt += "None\n"
        txt += "\n📅 Today: " + str(STATS["daily_trades"]) + "/30"
        if is_signal_active():
            txt += "\n⏳ Active: " + str(ACTIVE_SIGNAL["pair"]) + " " + str(ACTIVE_SIGNAL["dir"])
        sb, sn = get_session_boost("EURUSD")
        txt += "\n⏰ Session: " + sn + " (" + str(sb) + ")"
        bot.send_message(m.chat.id, txt, parse_mode="Markdown")
        return
    if txt_in.startswith("/stop"):
        if m.chat.id in AUTO_STATE:
            AUTO_STATE[m.chat.id]["running"] = False
            bot.send_message(m.chat.id, "🛑 Stopping...")
        else:
            bot.send_message(m.chat.id, "Auto not running")
        return
    if txt_in.startswith("/results"):
        if not OTC_SESSION_RESULTS:
            bot.send_message(m.chat.id, "📭 No trades yet")
            return
        wins = sum(1 for x in OTC_SESSION_RESULTS if x["win"])
        losses = len(OTC_SESSION_RESULTS) - wins
        pnl_total = sum(x["pnl"] for x in OTC_SESSION_RESULTS)
        idx = OTC_MARTI["loss_streak"]
        txt = "📊 **RESULTS**\n\nTotal: " + str(len(OTC_SESSION_RESULTS)) + " | W:" + str(wins) + " L:" + str(losses) + " | PnL: ${:.2f}\n".format(pnl_total)
        txt += "Today: " + str(STATS["daily_trades"]) + "/30 | Level " + str(idx+1) + "/4"
        bot.send_message(m.chat.id, txt, parse_mode="Markdown")
        return
    if txt_in.startswith("/mode"):
        tz = pytz.timezone("Africa/Lagos")
        now = datetime.now(tz)
        sb, sn = get_session_boost("EURUSD")
        if IQ_CONNECTED:
            iq_txt = "✅ YES"
        else:
            iq_txt = "❌ NO"
        if is_signal_active():
            act = str(ACTIVE_SIGNAL["pair"])
        else:
            act = "None"
        if AUTO_SEND_90:
            atxt = "✅ ON"
        else:
            atxt = "🛑 OFF"
        txt = "📍 **MODE CHECK V4**\n\n" + get_greeting() + "\n"
        txt += "⏰ Now: " + now.strftime("%A %H:%M:%S WAT") + "\n"
        txt += "⏰ Session: " + sn + " (" + str(sb) + ")\n"
        txt += "📊 Mode: " + get_mode_text() + "\n"
        txt += "💎 IQ: " + iq_txt + "\n"
        txt += "📅 Today: " + str(STATS["daily_trades"]) + "/30\n"
        txt += "⏳ Active: " + act + "\n"
        txt += "👥 Users: " + str(len(ALLOWED_USERS)) + " | Auto 90+: " + atxt
        bot.send_message(m.chat.id, txt, parse_mode="Markdown")
        return
    if txt_in.startswith("/balance"):
        try:
            if not IQ_CONNECTED:
                bot.send_message(m.chat.id, "💰 **BALANCES**\nIQ: ❌ Not connected yet")
                return
            demo = get_real_balance("PRACTICE")
            real = get_real_balance("REAL")
            bot.send_message(m.chat.id, "💰 **BALANCES**\n🟢 DEMO: ${:.2f}\n🔴 REAL: ${:.2f}".format(demo, real))
        except Exception as e:
            bot.send_message(m.chat.id, "Balance error " + str(e))
        return
    try:
        if IQ_CONNECTED:
            bal_demo = get_real_balance("PRACTICE")
        else:
            bal_demo = STATS.get("real_balance", 0.0)
    except:
        bal_demo = 0.0
    mk = types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton("📈 TRADE REAL (15) AUTO EXPIRY - ${:.2f}".format(bal_demo), callback_data="trade_real"))
    mk.add(types.InlineKeyboardButton("🚀 GET READY - Send To Channel", callback_data="ready_btn"))
    mk.add(types.InlineKeyboardButton("📊 MY STATS", callback_data="stats"), types.InlineKeyboardButton("🧠 AI BRAIN", callback_data="brain_btn"), types.InlineKeyboardButton("📰 NEWS CHECK", callback_data="news_btn"), types.InlineKeyboardButton("⚙️ SETTINGS", callback_data="settings"))
    greet = get_greeting()
    sb, sn = get_session_boost("EURUSD")
    if IQ_CONNECTED:
        iq_txt = "✅"
    else:
        iq_txt = "❌"
    if AUTO_SEND_90:
        atxt = "✅ ON"
    else:
        atxt = "🛑 OFF"
    txt = greet + "\n\n🤖 **Z-BOT V4 TRAILBLAZER - MANUAL** 🤖\n\n"
    txt += "💎 IQ: " + iq_txt + " | 💰 DEMO ${:.2f}\n".format(bal_demo)
    txt += "🏆 W:" + str(STATS["wins"]) + " L:" + str(STATS["loss"]) + " | 🔥 " + str(STATS["streak"]) + "\n"
    txt += "📅 Today: " + str(STATS["daily_trades"]) + "/30\n"
    txt += "🧠 Brain: Learning best pairs + hours + RSI\n⏰ Session: " + sn + " (" + str(sb) + ")\n"
    txt += "📰 News: Auto scanner ON\n🥇 GOLD: XAUUSD ON\n📍 " + get_mode_text() + "\n"
    txt += "👥 Users: " + str(len(ALLOWED_USERS)) + " | Auto 90+: " + atxt + "\n\n👇 **Select:**"
    bot.send_message(m.chat.id, txt, reply_markup=mk, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_allowed(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Private")
        return
    data = c.data
    cid = c.message.chat.id
    # --- USER OWN WIN / LOSS ---
    if data.startswith("user_win_"):
        pair = data.replace("user_win_", "")
        u = record_user_result(cid, pair, True)
        if cid in PULLBACK_STATE:
            PULLBACK_STATE[cid]["active"] = False
        uw = u["wins"]
        ul = u["loss"]
        bot.answer_callback_query(c.id, "✅ Your WIN recorded!")
        msg = "🏆🏆 **YOUR WIN RECORDED** 🏆🏆\n\n💱 " + pair + "\n✅ Your Wins: " + str(uw) + " | ❌ Your Loss: " + str(ul) + "\n♻️ Your next stake reset to $1 💵\n\nThis na YOUR record only. Admin brain no touch am.\n\nType /mystats to see full record. 📊"
        bot.send_message(cid, msg, parse_mode="Markdown")
        return
    if data.startswith("user_loss_"):
        parts = data.replace("user_loss_", "").rsplit("_", 1)
        pair = parts[0]
        if len(parts) > 1:
            orig_dir = parts[1]
        else:
            orig_dir = "CALL"
        u = record_user_result(cid, pair, False)
        uw = u["wins"]
        ul = u["loss"]
        if u["marti_streak"] >= 4:
            u["marti_streak"] = 0
            save_user_data()
            bot.answer_callback_query(c.id, "Chain finished - Reset to $1")
            msg = "⛔ **YOUR CHAIN FINISHED**\n\n💱 " + pair + "\n❌ You lost: $1 + $2 + $4 + $8 = -$15\n♻️ YOUR reset to $1\nYour Wins: " + str(uw) + " | Your Loss: " + str(ul) + "\n\nAdmin own chain no touch."
            bot.send_message(cid, msg, parse_mode="Markdown")
            return
        levels = [1, 2, 4, 8]
        names = ["", "Martingale 1", "Martingale 2", "Martingale 3"]
        idx = u["marti_streak"]
        mult = levels[idx]
        amt = 1.0 * mult
        bot.answer_callback_query(c.id, "Your LOSS - Next " + names[idx] + " $" + str(amt))
        msg = "❌ **YOUR LOSS RECORDED**\n\n💱 " + pair + "\n👉 YOUR Next: **" + names[idx] + " - ${:.2f} Level {}/4 ({}x)**\n".format(amt, idx+1, mult)
        msg += "Your Wins: " + str(uw) + " | Your Loss: " + str(ul) + "\n\n🔍 YOUR pullback scan go start for you only...\nWait for next signal for " + pair + "."
        bot.send_message(cid, msg, parse_mode="Markdown")
        threading.Thread(target=pullback_scanner_loop, args=(cid, pair, orig_dir), daemon=True).start()
        return
    if data.startswith("user_skip_"):
        pair = data.replace("user_skip_", "")
        if cid in PULLBACK_STATE:
            PULLBACK_STATE[cid]["active"] = False
        bot.answer_callback_query(c.id, "Skipped for you")
        bot.send_message(cid, "⏭️ **YOU SKIPPED**\n\n💱 " + pair + "\nNo WIN / LOSS recorded for YOU.\nAdmin and others no affect.")
        return
    # --- ADMIN ONLY BELOW ---
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Admin only")
        return
    if data == "ready_btn":
        send_photo_to_channel_sync(READY_PHOTO, get_ready_text())
        bot.answer_callback_query(c.id, "✅ Get Ready sent to Channel!")
        bot.send_message(cid, "✅ Get Ready sent to @KEVINTRAILBLAZE! 🚀📤")
        return
    if data.startswith("send_both_") or data.startswith("send_both_pb_"):
        try:
            if data.startswith("send_both_pb_"):
                is_pb = True
            else:
                is_pb = False
            if is_pb:
                clean = data.replace("send_both_pb_", "")
            else:
                clean = data.replace("send_both_", "")
            parts = clean.rsplit("_", 1)
            pair = parts[0]
            if len(parts) > 1:
                dir_ = parts[1]
            else:
                dir_ = ACTIVE_SIGNAL.get("dir", "CALL")
            tz2 = pytz.timezone("Africa/Lagos")
            entry_txt = (datetime.now(tz2) + timedelta(seconds=45)).strftime("%H:%M:%S WAT")
            expiry = ACTIVE_SIGNAL.get("expiry", 120)
            if pair == "XAUUSD":
                if is_pb:
                    idx = OTC_MARTI["loss_streak"]
                    if idx < 1:
                        idx = 1
                    if idx > 3:
                        idx = 3
                    amt = OTC_MARTI["base"] * OTC_MARTI["levels"][idx]
                    text = format_channel_pullback_gold_signal(dir_, entry_txt, idx, amt)
                else:
                    if ACTIVE_SIGNAL.get("sl", 0) and ACTIVE_SIGNAL.get("pair") == "XAUUSD":
                        d_gold = {"dir": dir_, "conf": ACTIVE_SIGNAL.get("conf", 88), "price": ACTIVE_SIGNAL.get("price", 0), "sl": ACTIVE_SIGNAL.get("sl", 0), "tp1": ACTIVE_SIGNAL.get("tp1", 0), "tp2": ACTIVE_SIGNAL.get("tp2", 0)}
                        text = format_channel_gold_signal(d_gold, entry_txt)
                    else:
                        text = format_channel_signal(pair, dir_, ACTIVE_SIGNAL.get("conf", 88), ACTIVE_SIGNAL.get("price", 0), entry_txt, expiry)
            else:
                if is_pb:
                    idx = OTC_MARTI["loss_streak"]
                    if idx < 1:
                        idx = 1
                    if idx > 3:
                        idx = 3
                    amt = OTC_MARTI["base"] * OTC_MARTI["levels"][idx]
                    text = format_channel_pullback_signal(pair, dir_, entry_txt, idx, amt, expiry)
                else:
                    text = format_channel_signal(pair, dir_, ACTIVE_SIGNAL.get("conf", 88), ACTIVE_SIGNAL.get("price", 0), entry_txt, expiry)
            try:
                bot.send_message(OWNER_ID, text, parse_mode="Markdown")
            except:
                pass
            send_signal_to_users(pair, dir_, text)
            bot.answer_callback_query(c.id, "✅ Sent to You + users!")
            bot.send_message(cid, "✅ Sent to You + " + str(len(ALLOWED_USERS)) + " users only 👥\n❌ NOT sent to Channel.\nUsers get their own MY WIN / MY LOSS buttons.")
        except Exception as e:
            bot.answer_callback_query(c.id, "Error " + str(e))
        return
    if data.startswith("send_channel_pb_"):
        try:
            parts = data.replace("send_channel_pb_", "").rsplit("_", 1)
            pair = parts[0]
            if len(parts) > 1:
                dir_ = parts[1]
            else:
                dir_ = ACTIVE_SIGNAL.get("dir", "CALL")
            tz2 = pytz.timezone("Africa/Lagos")
            entry_txt = (datetime.now(tz2) + timedelta(seconds=45)).strftime("%H:%M:%S WAT")
            idx = OTC_MARTI["loss_streak"]
            if idx < 1:
                idx = 1
            if idx > 3:
                idx = 3
            amt = OTC_MARTI["base"] * OTC_MARTI["levels"][idx]
            expiry = ACTIVE_SIGNAL.get("expiry", 120)
            if pair == "XAUUSD":
                send_to_channel_sync(format_channel_pullback_gold_signal(dir_, entry_txt, idx, amt))
            else:
                send_to_channel_sync(format_channel_pullback_signal(pair, dir_, entry_txt, idx, amt, expiry))
            bot.answer_callback_query(c.id, "✅ Pullback sent to Channel!")
            bot.send_message(cid, "✅ Pullback sent to @KEVINTRAILBLAZE 📤")
        except Exception as e:
            bot.answer_callback_query(c.id, "Error " + str(e))
        return
    if data.startswith("send_channel_"):
        try:
            parts = data.replace("send_channel_", "").rsplit("_", 1)
            pair = parts[0]
            if len(parts) > 1:
                dir_ = parts[1]
            else:
                dir_ = ACTIVE_SIGNAL.get("dir", "CALL")
            tz2 = pytz.timezone("Africa/Lagos")
            entry_txt = (datetime.now(tz2) + timedelta(seconds=45)).strftime("%H:%M:%S WAT")
            expiry = ACTIVE_SIGNAL.get("expiry", 120)
            if pair == "XAUUSD":
                if ACTIVE_SIGNAL.get("sl", 0) and ACTIVE_SIGNAL.get("pair") == "XAUUSD":
                    d_gold = {"dir": dir_, "conf": ACTIVE_SIGNAL.get("conf", 88), "price": ACTIVE_SIGNAL.get("price", 0), "sl": ACTIVE_SIGNAL.get("sl", 0), "tp1": ACTIVE_SIGNAL.get("tp1", 0), "tp2": ACTIVE_SIGNAL.get("tp2", 0)}
                    send_to_channel_sync(format_channel_gold_signal(d_gold, entry_txt))
                else:
                    send_to_channel_sync(format_channel_signal(pair, dir_, ACTIVE_SIGNAL.get("conf", 88), ACTIVE_SIGNAL.get("price", 0), entry_txt, expiry))
            else:
                send_to_channel_sync(format_channel_signal(pair, dir_, ACTIVE_SIGNAL.get("conf", 88), ACTIVE_SIGNAL.get("price", 0), entry_txt, expiry))
            bot.answer_callback_query(c.id, "✅ Sent to Channel!")
            bot.send_message(cid, "✅ Signal sent to @KEVINTRAILBLAZE 📤")
        except Exception as e:
            bot.answer_callback_query(c.id, "Error " + str(e))
        return
    if data == "news_btn":
        news = get_upcoming_news()
        if not news:
            bot.send_message(cid, "📰 **NEWS CHECK**\n\n✅ No high impact news in next 2 hours - Clean market!", parse_mode="Markdown")
            return
        txt = "📰 **UPCOMING NEWS - NEXT 2H**\n\n" + format_news_alert(news)
        bot.send_message(cid, txt, parse_mode="Markdown")
        return
    if data.startswith("skip_"):
        pair = data.replace("skip_", "")
        if cid in PULLBACK_STATE:
            PULLBACK_STATE[cid]["active"] = False
        clear_signal()
        LAST_GLOBAL_SIGNAL["time"] = time.time() - (GLOBAL_COOLDOWN - SKIP_COOLDOWN)
        bot.answer_callback_query(c.id, "Skipped - Next in 5 min")
        bot.send_message(cid, "⏭️ **SKIPPED**\n\n💱 " + pair + "\nYou skipped this trade.\nNo WIN / LOSS recorded.\n⏳ Next signal in **5 mins**.\n✅ Lock opened.")
        return
    if data.startswith("manual_win_"):
        pair = data.replace("manual_win_", "")
        win_conf = ACTIVE_SIGNAL.get("conf", 88)
        win_rsi = ACTIVE_SIGNAL.get("rsi", 50)
        win_adx = ACTIVE_SIGNAL.get("adx", 30)
        win_dir = ACTIVE_SIGNAL.get("dir", "CALL")
        record_brain(pair, True, win_conf, win_rsi, win_adx)
        OTC_MARTI["loss_streak"] = 0
        if cid in PULLBACK_STATE:
            PULLBACK_STATE[cid]["active"] = False
        clear_signal()
        STATS["wins"] += 1
        count_trade()
        wr = get_pair_winrate(pair)
        if wr is not None:
            wr_txt = "\n🧠 " + pair + " Brain WR now {:.0f}%".format(wr)
        else:
            wr_txt = ""
        bot.answer_callback_query(c.id, "WIN 🏅")
        base = OTC_MARTI["base"]
        profit = round(base * 0.85, 2)
        total_return = round(base + profit, 2)
        tz = pytz.timezone("Africa/Lagos")
        now = datetime.now(tz)
        if win_dir == "CALL":
            dir_e = "🟢 CALL ⬆️"
        else:
            dir_e = "🔴 PUT ⬇️"
        total = STATS["wins"] + STATS["loss"]
        if total:
            wr_total = STATS["wins"] / total * 100
        else:
            wr_total = 0
        pair_label = PAIR_EMOJI.get(pair, pair)
        win_msg = "🏆━━━━━━━━━━━━━━━━━━🏆\n      ✅ TRADE WON 🏅\n🏆━━━━━━━━━━━━━━━━━━🏆\n\n🎯 " + pair_label + "\n📈 " + dir_e + " | Conf: {:.0f}%\n".format(win_conf)
        win_msg += "🕒 " + now.strftime("%H:%M:%S") + " | " + now.strftime("%d %b") + "\n\n──────────────────\n💵 Stake: ${:.2f}\n💰 Profit: +${:.2f}\n💵 Payout: ${:.2f}\n──────────────────\n\n".format(base, profit, total_return)
        win_msg += "🏅 Wins: " + str(STATS["wins"]) + " | ❌ Loss: " + str(STATS["loss"]) + "\n📊 Today WR: {:.1f}%".format(wr_total) + wr_txt + "\n♻️ Next Entry Reset: ${:.2f}\n".format(base)
        win_msg += "📅 Today: " + str(STATS["daily_trades"]) + "/30 trades\n✅ Next signal can now come."
        bot.send_message(cid, win_msg, parse_mode="Markdown")
        bot.send_message(cid, "🤑")
        return
    if data.startswith("manual_loss_"):
        parts = data.replace("manual_loss_", "").rsplit("_", 1)
        pair = parts[0]
        if len(parts) > 1:
            orig_dir = parts[1]
        else:
            orig_dir = "CALL"
        record_brain(pair, False, ACTIVE_SIGNAL.get("conf", 88), ACTIVE_SIGNAL.get("rsi", 50), ACTIVE_SIGNAL.get("adx", 30))
        OTC_MARTI["loss_streak"] += 1
        STATS["loss"] += 1
        count_trade()
        if OTC_MARTI["loss_streak"] >= 4:
            OTC_MARTI["loss_streak"] = 0
            if cid in PULLBACK_STATE:
                PULLBACK_STATE[cid]["active"] = False
            clear_signal()
            wr = get_pair_winrate(pair)
            if wr is not None:
                wr_txt = "\n🧠 " + pair + " Brain WR now {:.0f}%".format(wr)
            else:
                wr_txt = ""
            bot.answer_callback_query(c.id, "Chain finished - Reset to $1")
            bot.send_message(cid, "⛔ **CHAIN FINISHED**\n\n💱 " + pair + "\n❌ Lost: $1 + $2 + $4 + $8 = -$15\n♻️ RESET to Real Entry $1" + wr_txt + "\n📅 Today: " + str(STATS["daily_trades"]) + "/30\n✅ Next signal can now come.\n💪 No give up Trailblazer! 🔥")
            return
        levels = OTC_MARTI["levels"]
        idx = OTC_MARTI["loss_streak"]
        mult = levels[idx]
        next_amt = OTC_MARTI["base"] * mult
        names = ["", "Martingale 1", "Martingale 2", "Martingale 3"]
        wr = get_pair_winrate(pair)
        if wr is not None:
            wr_txt = "\n🧠 " + pair + " Brain WR {:.0f}%".format(wr)
        else:
            wr_txt = ""
        bot.answer_callback_query(c.id, "LOSS - Next " + names[idx] + " $" + str(next_amt))
        msg = "❌ **LOSS Recorded**\n\n💱 " + pair + "\n👉 Next: **" + names[idx] + " - ${:.2f} Level {}/4 ({}x)**".format(next_amt, idx+1, mult) + wr_txt + "\n🔍 Scanning every 10 sec for pullback entry...\n📍 RSI safe + RSI turning + Price at EMA\n📰 News check ON\n\nPress ✅ WIN / ❌ LOSS / ⏭️ SKIP after you trade."
        bot.send_message(cid, msg)
        threading.Thread(target=pullback_scanner_loop, args=(cid, pair, orig_dir), daemon=True).start()
        return
    if data == "brain_btn":
        txt = "🧠 **AI BRAIN V4**\n\n"
        best = []
        bad = []
        for pair, s in PAIR_BRAIN.items():
            total = s["wins"] + s["loss"]
            if total >= 3:
                wr = s["wins"] / total * 100
                if is_pair_blocked(pair):
                    blk = " 🚫"
                else:
                    blk = ""
                line = PAIR_EMOJI.get(pair, pair) + ": W" + str(s["wins"]) + " L" + str(s["loss"]) + " = {:.0f}%".format(wr) + blk + "\n"
                if wr >= 60:
                    best.append(line)
                elif wr < 50:
                    bad.append(line)
        txt += "🏆 BEST:\n"
        if best:
            txt += "".join(best)
        else:
            txt += "No data yet\n"
        txt += "\n💀 BAD:\n"
        if bad:
            txt += "".join(bad)
        else:
            txt += "None\n"
        sb, sn = get_session_boost("EURUSD")
        txt += "\n⏰ Now: " + sn + " (" + str(sb) + ")"
        bot.send_message(cid, txt, parse_mode="Markdown")
        return
    if data == "trade_real":
        mk = types.InlineKeyboardMarkup(row_width=1)
        mk.add(types.InlineKeyboardButton("🔍 📊 SCAN ALL REAL NOW (15 PAIRS)", callback_data="scan_all_real"))
        for p in REAL_PAIRS:
            mk.add(types.InlineKeyboardButton(PAIR_EMOJI.get(p, p), callback_data="real_pair_" + p))
        mk.add(types.InlineKeyboardButton("🥇 XAU/USD GOLD", callback_data="real_pair_XAUUSD"))
        bot.send_message(cid, "📈 **TRADE REAL V4 TRAILBLAZER MANUAL**\n📍 " + get_mode_text() + "\n📅 Today: " + str(STATS["daily_trades"]) + "/30", reply_markup=mk, parse_mode="Markdown")
        return
    if data == "scan_all_real":
        if is_signal_active():
            bot.send_message(cid, "⏳ **One signal already active**\n\n💱 " + str(ACTIVE_SIGNAL["pair"]) + " " + str(ACTIVE_SIGNAL["dir"]) + "\nFinish it first - Press ✅ WIN / ❌ LOSS / ⏭️ SKIP")
            return
        if not can_trade_today():
            bot.send_message(cid, "⛔ Max 30 trades reached today. Come back tomorrow 7AM.")
            return
        bot.answer_callback_query(c.id, "Scanning 15 REAL pairs V4...")
        scan_msg = bot.send_message(cid, "🔍 **SCANNING ALL 15 REAL PAIRS V4 TRAILBLAZER...**\n\n⏳ ~12 sec")
        results = []
        datas = {}
        for pair in REAL_PAIRS:
            if is_pair_blocked(pair):
                results.append((pair, 0, "-", "🧠 Blocked", "🔴 BLOCKED", 120))
                continue
            nb = is_news_blocking_pair(pair, minutes=30)
            if nb:
                results.append((pair, 0, "-", "📰 News Block", "🔴 NEWS", 120))
                continue
            d = analyze_sniper_v12(pair, sniper_mode=False)
            if not d:
                results.append((pair, 0, "-", "No data", "🔴 NO TRADE", 120))
                continue
            conf = d["conf"]
            dir_ = d["dir"]
            reason = d["reason"]
            exp = d["expiry"]
            if conf >= 88:
                status = "🟢 READY"
            elif conf >= 65:
                status = "🟡 WAIT"
            else:
                status = "🔴 NO TRADE"
            results.append((pair, conf, dir_, reason, status, exp))
            datas[pair] = d
            try:
                bot.edit_message_text("🔍 Scanning V4... " + pair + " {:.0f}%".format(conf), cid, scan_msg.message_id)
            except:
                pass
            time.sleep(0.3)
        results.sort(key=lambda x: x[1], reverse=True)
        txt = "📊 **REAL V4 TRAILBLAZER READINESS** 📊\n"
        txt += "📍 " + get_mode_text() + "\n⏰ " + datetime.now(pytz.timezone("Africa/Lagos")).strftime("%H:%M:%S WAT") + "\n📅 Today: " + str(STATS["daily_trades"]) + "/30\n📰 News: " + str(len(get_upcoming_news())) + " high impact in next 2h\n\n"
        for pair, conf, dir_, reason, status, exp in results:
            emoji = PAIR_EMOJI.get(pair, pair)
            txt += status + " " + emoji + ": {:.0f}% ".format(conf) + dir_ + " - " + reason + "\n"
        best = results[0] if results else None
        if best and best[1] >= 88:
            txt += "\n💡 **BEST NOW:** " + PAIR_EMOJI.get(best[0], best[0]) + " {:.0f}%".format(best[1])
        mk = types.InlineKeyboardMarkup(row_width=2)
        if best and best[1] >= 88:
            mk.add(types.InlineKeyboardButton("✅ TRADE BEST " + best[0], callback_data="real_pair_" + best[0]))
        mk.add(types.InlineKeyboardButton("🔄 RE-SCAN ALL", callback_data="scan_all_real"))
        bot.send_message(cid, txt, reply_markup=mk, parse_mode="Markdown")
        if best and best[1] >= 88 and best[0] in datas:
            time.sleep(0.5)
            best_data = datas[best[0]]
            tz = pytz.timezone("Africa/Lagos")
            now = datetime.now(tz)
            entry = now + timedelta(seconds=45)
            bdir = best_data["dir"]
            bconf = best_data["conf"]
            breason = best_data["reason"]
            brsi = best_data["rsi"]
            bpayout = best_data["payout"]
            bprice = best_data["price"]
            bpair = best_data["pair"]
            if bdir == "CALL":
                dir_e = "🟢 CALL ⬆️"
            else:
                dir_e = "🔴 PUT ⬇️"
            base = OTC_MARTI["base"]
            mk2 = types.InlineKeyboardMarkup(row_width=2)
            mk2.add(types.InlineKeyboardButton("✅ WIN - Reset", callback_data="manual_win_" + bpair), types.InlineKeyboardButton("❌ LOSS - Pullback Scan", callback_data="manual_loss_" + bpair + "_" + bdir))
            mk2.add(types.InlineKeyboardButton("⏭️ SKIP THIS TRADE", callback_data="skip_" + bpair))
            mk2.add(types.InlineKeyboardButton("📤 Send to Channel", callback_data="send_channel_" + bpair + "_" + bdir))
            mk2.add(types.InlineKeyboardButton("📤👥 Send to Both Me + Users", callback_data="send_both_" + bpair + "_" + bdir))
            ti2 = best_data.get("trend_info", {})
            exp_min2 = ti2.get("expiry", 120) // 60
            signal_txt = "📡 **REAL TOP SIGNAL V4 - MANUAL** 📡\n\n💱 " + PAIR_EMOJI.get(bpair, bpair) + "\n📊 " + dir_e + " | 🎯 {:.0f}% SNIPER\n".format(bconf)
            signal_txt += "📈 " + breason + " | RSI {:.1f}\n".format(brsi)
            signal_txt += "💸 {:.0f}% | 💰 {:.5f} | ⏱️ Suggested: {} Min\n".format(bpayout*100, bprice, exp_min2)
            signal_txt += "📊 Trend: " + ti2.get("trend_type", "➡️ NORMAL TREND") + "\n📰 News: ✅ Checked\n\n"
            signal_txt += "⏰ ENTRYContinue from where e cut - na only tail remain, append this to end your file, replace the cut-off part:

```python
            signal_txt += "⏰ ENTRY: " + entry.strftime("%H:%M:%S WAT") + " (in 45s)\n\n"
            signal_txt += "**Real Entry:** ${:.2f}\n**Marti 1:** ${:.2f} | **Marti 2:** ${:.2f} | **Marti 3:** ${:.2f}\n\n".format(base, base*2, base*4, base*8)
            signal_txt += "⚠️ MANUAL - Press WIN / LOSS / SKIP"
            bot.send_message(cid, signal_txt, parse_mode="Markdown", reply_markup=mk2)
            start_signal(bpair, bdir, bconf, brsi, best_data.get("adx", 30), price=bprice, expiry=best_data.get("expiry", 120))
        return
    if data.startswith("real_pair_"):
        pair = data.replace("real_pair_", "")
        if pair == "XAUUSD":
            bot.answer_callback_query(c.id, "Scanning GOLD...")
            d = analyze_xauusd()
            if not d:
                bot.send_message(cid, "⚠️ **No safe GOLD trade now**\n\n📊 Conf < 88% or ADX / News block\nTry again in 5 min.")
                return
            tz = pytz.timezone("Africa/Lagos")
            now = datetime.now(tz)
            entry_time = now + timedelta(seconds=45)
            dir_ = d["dir"]
            conf = d["conf"]
            reason = d["reason"]
            rsi_v = d["rsi"]
            atr_v = d["atr"]
            sess = d["session"]
            price = d["price"]
            sl = d["sl"]
            tp1 = d["tp1"]
            tp2 = d["tp2"]
            if dir_ == "CALL":
                dir_e = "🟢 BUY ⬆️"
            else:
                dir_e = "🔴 SELL ⬇️"
            base = OTC_MARTI["base"]
            mk = types.InlineKeyboardMarkup(row_width=2)
            mk.add(types.InlineKeyboardButton("✅ WIN - Reset", callback_data="manual_win_XAUUSD"), types.InlineKeyboardButton("❌ LOSS - Pullback Scan", callback_data="manual_loss_XAUUSD_" + dir_))
            mk.add(types.InlineKeyboardButton("⏭️ SKIP THIS TRADE", callback_data="skip_XAUUSD"))
            mk.add(types.InlineKeyboardButton("📤 Send to Channel", callback_data="send_channel_XAUUSD_" + dir_))
            mk.add(types.InlineKeyboardButton("📤👥 Send to Both Me + Users", callback_data="send_both_XAUUSD_" + dir_))
            msg = "🥇🥇🥇 **XAU/USD GOLD SIGNAL** 🥇🥇🥇\n\n" + dir_e + " | 🎯 {:.0f}% SNIPER GOLD\n".format(conf)
            msg += "📈 " + reason + " | RSI {:.1f} | ATR {:.2f}\n".format(rsi_v, atr_v)
            msg += "⏰ Session: " + sess + "\n\n"
            msg += "━━━━━━━━━━━━━━━━━━\n⏰ ENTRY TIME: " + entry_time.strftime("%H:%M:%S WAT") + "\n"
            msg += "💰 ENTRY: {:.2f}\n🛑 SL: {:.2f}\n🎯 TP1: {:.2f}\n🎯 TP2: {:.2f}\n".format(price, sl, tp1, tp2)
            msg += "━━━━━━━━━━━━━━━━━━\n\n💵 **Stake:** ${:.2f}\n⚠️ MANUAL - Press WIN / LOSS / SKIP".format(base)
            bot.send_message(cid, msg, parse_mode="Markdown", reply_markup=mk)
            start_signal("XAUUSD", dir_, conf, rsi_v, d.get("adx", 30), price=price, sl=sl, tp1=tp1, tp2=tp2)
            return
        if is_signal_active() and ACTIVE_SIGNAL["pair"] != pair:
            bot.send_message(cid, "⏳ **One signal already active**\n\n💱 " + str(ACTIVE_SIGNAL["pair"]) + " " + str(ACTIVE_SIGNAL["dir"]) + "\nFinish it first - Press ✅ WIN / ❌ LOSS / ⏭️ SKIP")
            return
        if is_pair_blocked(pair):
            bot.send_message(cid, "🧠 **" + pair + " Blocked by Brain**\n\nThis pair has been losing. Try another pair.")
            return
        nb = is_news_blocking_pair(pair, minutes=30)
        if nb:
            nc = nb["country"]
            title = nb["title"]
            nin = nb["in_min"]
            bot.send_message(cid, "📰 **" + pair + " Blocked by NEWS**\n\n🔴 " + nc + " - " + title + "\n⏰ In " + str(nin) + " min\n\nWait 15 min after news.")
            return
        bot.answer_callback_query(c.id, "Scanning " + pair + " V4...")
        scan_msg = bot.send_message(cid, "🔍 **V4 TRAILBLAZER SCAN " + PAIR_EMOJI.get(pair, pair) + "**\n\n0%\n🚀 Sniper...")
        time.sleep(1)
        try:
            bot.edit_message_text("🔍 Scanning V4... " + pair, cid, scan_msg.message_id)
        except:
            pass
        d = analyze_sniper_v12(pair, sniper_mode=False)
        if not d or d["conf"] < 88:
            mk = types.InlineKeyboardMarkup()
            mk.add(types.InlineKeyboardButton("🔄 RETRY", callback_data="real_pair_" + pair), types.InlineKeyboardButton("📈 SCAN ALL", callback_data="scan_all_real"))
            if d:
                conf_v = d["conf"]
                reason_v = d["reason"]
            else:
                conf_v = 0
                reason_v = "No data"
            bot.send_message(cid, "⚠️ **No safe trade now for " + pair + "**\n\n📊 Conf: {:.0f}% < 88%\n🛡️ ".format(conf_v) + reason_v, reply_markup=mk)
            return
        tz = pytz.timezone("Africa/Lagos")
        now = datetime.now(tz)
        entry = now + timedelta(seconds=45)
        dir_ = d["dir"]
        conf = d["conf"]
        reason = d["reason"]
        rsi_v = d["rsi"]
        atr_v = d["atr"]
        payout = d["payout"]
        price = d["price"]
        if dir_ == "CALL":
            dir_e = "🟢 CALL ⬆️"
        else:
            dir_e = "🔴 PUT ⬇️"
        base = OTC_MARTI["base"]
        ti3 = d.get("trend_info", {})
        exp_min3 = ti3.get("expiry", 120) // 60
        trends_txt = " | ".join(ti3.get("trends", [])[:4])
        signal_txt = "📡 **REAL SIGNAL V4 TRAILBLAZER - MANUAL** 📡\n\n💱 " + PAIR_EMOJI.get(pair, pair) + "\n📊 " + dir_e + " | 🎯 {:.0f}% SNIPER\n".format(conf)
        signal_txt += "📈 " + reason + " | RSI {:.1f} | ATR {:.5f}\n".format(rsi_v, atr_v)
        signal_txt += "📊 Trend: " + ti3.get("trend_type", "➡️ NORMAL TREND") + "\n🔍 Trends: " + trends_txt + "\n"
        signal_txt += "💸 {:.0f}% | 💰 {:.5f} | ⏱️ Suggested: {} Min\n".format(payout*100, price, exp_min3)
        signal_txt += "📰 News: ✅ Checked\n\n⏰ ENTRY: " + entry.strftime("%H:%M:%S WAT") + " (in 45s)\n\n"
        signal_txt += "**Real Entry:** ${:.2f}\n**Marti 1:** ${:.2f} | **Marti 2:** ${:.2f} | **Marti 3:** ${:.2f}\n\n".format(base, base*2, base*4, base*8)
        signal_txt += "⚠️ MANUAL - Press WIN / LOSS / SKIP"
        mk = types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("✅ WIN - Reset", callback_data="manual_win_" + pair), types.InlineKeyboardButton("❌ LOSS - Pullback Scan", callback_data="manual_loss_" + pair + "_" + dir_))
        mk.add(types.InlineKeyboardButton("⏭️ SKIP THIS TRADE", callback_data="skip_" + pair))
        mk.add(types.InlineKeyboardButton("📤 Send to Channel", callback_data="send_channel_" + pair + "_" + dir_))
        mk.add(types.InlineKeyboardButton("📤👥 Send to Both Me + Users", callback_data="send_both_" + pair + "_" + dir_))
        mk.add(types.InlineKeyboardButton("🔁 SAME PAIR", callback_data="real_pair_" + pair), types.InlineKeyboardButton("📈 SCAN ALL", callback_data="scan_all_real"))
        bot.send_message(cid, signal_txt, reply_markup=mk, parse_mode="Markdown")
        start_signal(pair, dir_, conf, rsi_v, d.get("adx", 30), price=price, expiry=d.get("expiry", 120))
        return
    if data == "trade" or data == "scan_all_otc" or data == "auto_setup" or data.startswith("auto_pair_") or data.startswith("auto_bal_") or data.startswith("auto_amt_") or data.startswith("pair_"):
        bot.answer_callback_query(c.id, "OTC Disabled")
        bot.send_message(cid, "⛔ **OTC DISABLED**\n\nBot go only send REAL signals from 7AM.\n\nUse TRADE REAL.")
        return
    if data == "stop_auto":
        if cid in AUTO_STATE:
            AUTO_STATE[cid]["running"] = False
            bot.send_message(cid, "🛑 Stopping...")
        return
    if data == "stats":
        total = STATS["wins"] + STATS["loss"]
        if total:
            wr = STATS["wins"] / total * 100
        else:
            wr = 0
        bal = get_real_balance("PRACTICE")
        sb, sn = get_session_boost("EURUSD")
        if AUTO_SEND_90:
            atxt = "✅ ON"
        else:
            atxt = "🛑 OFF"
        msg = "📊 **STATS V4**\n📍 " + get_mode_text() + "\n" + get_greeting() + "\n"
        msg += "⏰ Session: " + sn + " (" + str(sb) + ")\n"
        msg += "🏆 Wins: " + str(STATS["wins"]) + "\n❌ Loss: " + str(STATS["loss"]) + "\n"
        msg += "📈 Winrate: {:.1f}%\n".format(wr)
        msg += "🔥 Streak: " + str(STATS["streak"]) + "\n💰 Bal: ${:.2f}\n".format(bal)
        msg += "📅 Today: " + str(STATS["daily_trades"]) + "/30\n"
        msg += "🧠 Brain pairs: " + str(len(PAIR_BRAIN)) + "\n"
        msg += "📰 News in 2h: " + str(len(get_upcoming_news())) + "\n"
        msg += "📦 OTC: DISABLED | REAL only\n🥇 GOLD: XAUUSD ON\n"
        msg += "👥 Users: " + str(len(ALLOWED_USERS)) + " | Auto 90+: " + atxt
        bot.send_message(cid, msg, parse_mode="Markdown")
    if data == "settings":
        bot.send_message(cid, "⚙️ **SETTINGS V4 TRAILBLAZER MANUAL**\n\n🛡️ V4: 5M Trend + ADX 25+ + MACD + Stochastic + BB + Payout 80%+ + News Block + Session Boost + Brain + Pullback\n\n📢 Channel: @KEVINTRAILBLAZE\nUse /welcome, /intro and /ready to post to channel.")

if __name__ == "__main__":
    print("Starting Trailblazer Bot V4...")
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
                print("Polling error: " + str(e) + " - Retrying in 5 sec...")
                time.sleep(5)
    threading.Thread(target=run_polling, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    print("Flask running on port " + str(port))
    app.run(host="0.0.0.0", port=port)
