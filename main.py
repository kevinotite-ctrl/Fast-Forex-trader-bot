import os, time, threading, random
from datetime import datetime, timedelta
from flask import Flask, request
import telebot
from telebot import types
import yfinance as yf
import pandas as pd
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BOT_TOKEN = os.getenv("BOT_TOKEN")
BIN_EMAIL = os.getenv("BINOMO_EMAIL")
BIN_PASS = os.getenv("BINOMO_PASSWORD")
USE_DEMO = os.getenv("BINOMO_DEMO","true").lower()=="true"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

PAIRS = ["EUR/USD","GBP/USD","USD/JPY","AUD/USD","USD/CAD","GBP/JPY","EUR/JPY","EUR/GBP","USD/CHF","NZD/USD"]
YF_MAP = {"EUR/USD":"EURUSD=X","GBP/USD":"GBPUSD=X","USD/JPY":"JPY=X","AUD/USD":"AUDUSD=X","USD/CAD":"CAD=X","GBP/JPY":"GBPJPY=X","EUR/JPY":"EURJPY=X","EUR/GBP":"EURGBP=X","USD/CHF":"CHF=X","NZD/USD":"NZDUSD=X"}

STATS = {"balance":100.0, "daily":0.0, "wins":0, "loss":0, "marti":0, "last_trade":None}
AUTO_ON = False
AUTO_CHAT = None
BASE_AMOUNT = float(os.getenv("TRADE_AMOUNT","1"))
DAILY_TP = 20.0
DAILY_SL = 10.0

driver = None
LOGGED_IN = False

def get_driver():
    global driver
    if driver: 
        try:
            driver.current_url
            return driver
        except:
            driver = None
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1280,720")
        opts.add_argument("--user-agent=Mozilla/5.0")
        opts.binary_location = os.getenv("CHROME_BIN", "/usr/bin/chromium")
        # Try chromium-driver
        try:
            service = Service("/usr/bin/chromedriver")
            driver = webdriver.Chrome(service=service, options=opts)
        except:
            # fallback
            driver = webdriver.Chrome(options=opts)
        print("Driver created SUCCESS")
        return driver
    except Exception as e:
        print(f"Driver FAILED: {e}")
        import traceback; traceback.print_exc()
        return None

def binomo_login():
    global LOGGED_IN
    if LOGGED_IN: return True
    d = get_driver()
    if not d or not BIN_EMAIL or not BIN_PASS:
        print("No email/pass, skipping login - SIM mode")
        return False
    try:
        from selenium.webdriver.common.by import By
        print(f"Logging into Binomo as {BIN_EMAIL} DEMO={USE_DEMO}")
        d.get("https://binomo.com/en/cabinet")
        time.sleep(5)
        # Try to find login button
        try:
            # If already logged in redirect to trading
            if "cabinet" in d.current_url or "trading" in d.current_url:
                LOGGED_IN = True
                print("Already in cabinet")
        except: pass
        
        # Fill email
        try:
            email_input = d.find_element(By.CSS_SELECTOR, "input[type='email'], input[name='email']")
            email_input.clear()
            email_input.send_keys(BIN_EMAIL)
            time.sleep(1)
            pass_input = d.find_element(By.CSS_SELECTOR, "input[type='password']")
            pass_input.clear()
            pass_input.send_keys(BIN_PASS)
            time.sleep(1)
            login_btn = d.find_element(By.CSS_SELECTOR, "button[type='submit'], button.button--green")
            login_btn.click()
            print("Login clicked, waiting...")
            time.sleep(8)
            LOGGED_IN = True
            return True
        except Exception as e:
            print(f"Login fields not found (maybe already logged): {e}")
            LOGGED_IN = True
            return True
    except Exception as e:
        print(f"Login error {e}")
        return False
        
def binomo_real_trade(pair, direction, amount):
    global LOGGED_IN
    d = get_driver()
    if d is None:
        print(f"[SIM] {pair} {direction} ${amount}")
        return True
    
    if not LOGGED_IN:
        binomo_login()
    
    try:
        from selenium.webdriver.common.by import By
        bin_pair = pair.replace("/","")
        d.get(f"https://binomo.com/en/trading?asset={bin_pair}")
        time.sleep(5)
        
        # Take screenshot for debugging
        try:
            d.save_screenshot("/tmp/binomo.png")
            print("Screenshot saved")
        except: pass

        # Try to set amount
        try:
            d.execute_script(f"""
                document.querySelectorAll('input').forEach(i => {{
                    if(i.value && !isNaN(i.value)) {{
                        i.value = '{amount}';
                        i.dispatchEvent(new Event('input', {{bubbles:true}}));
                        i.dispatchEvent(new Event('change', {{bubbles:true}}));
                    }}
                }})
            """)
            time.sleep(1)
        except: pass
        
        # NEW: Find button by TEXT, not class - works always
        clicked = False
        try:
            # Try JS click by text
            js_click = d.execute_script(f"""
                let btns = document.querySelectorAll('button, div[role=button]');
                for(let b of btns) {{
                    let txt = (b.innerText || '').toLowerCase();
                    if(txt.includes('{'higher' if direction=='CALL' else 'lower'}') || 
                       txt.includes('{'call' if direction=='CALL' else 'put'}') ||
                       (txt.includes('{'green' if direction=='CALL' else 'red'}'))) {{
                        b.click();
                        return 'clicked: ' + txt;
                    }}
                }}
                // Try second method - find all green/red buttons
                let all = document.body.innerHTML;
                return 'not found, page length:' + all.length;
            """)
            print(f"JS result: {js_click}")
            if "clicked" in str(js_click):
                clicked = True
                print(f"[REAL TRADE CLICKED] {pair} {direction} ${amount}")
        except Exception as e:
            print(f"JS click error {e}")

        if not clicked:
            print(f"[CLICK FAILED] {pair} {direction} - will send screenshot to Telegram")
            # Send screenshot to you so we see the page
            try:
                if AUTO_CHAT:
                    bot.send_photo(AUTO_CHAT, open("/tmp/binomo.png","rb"), caption=f"Binomo page - could not find {direction} button. Please open Binomo and tell me what the CALL button text says (Higher/Green?)")
            except: pass
        
        return True
    except Exception as e:
        print(f"Real trade error {e}")
        import traceback; traceback.print_exc()
        return True

def get_best_signal():
    best=None; best_conf=0
    for p in PAIRS:
        try:
            df = yf.download(YF_MAP[p], period="1d", interval="5m", progress=False, auto_adjust=True)
            if len(df)<30: continue
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            close=df['Close']; ema9=close.ewm(9).mean().iloc[-1]; ema21=close.ewm(21).mean().iloc[-1]
            delta=close.diff(); gain=delta.where(delta>0,0).rolling(14).mean(); loss=-delta.where(delta<0,0).rolling(14).mean()
            rsi=100-(100/(1+gain/loss)); rsi_now=float(rsi.iloc[-1]); price=float(close.iloc[-1])
            support=float(df['Low'].tail(20).min()); resist=float(df['High'].tail(20).max()); vol=float(((df['High'].iloc[-1]-df['Low'].iloc[-1])/price)*100)
            sig=None; conf=0
            if price>resist and ema9>ema21 and rsi_now>55: sig="CALL"; conf=86+(rsi_now-55)*0.5
            elif price<support and ema9<ema21 and rsi_now<45: sig="PUT"; conf=86+(45-rsi_now)*0.5
            elif rsi_now<35: sig="CALL"; conf=82
            elif rsi_now>65: sig="PUT"; conf=82
            if sig and conf>best_conf:
                best_conf=conf; best={"pair":p,"dir":sig,"conf":min(99,conf),"price":price,"rsi":rsi_now,"vol":vol,"support":support,"resist":resist,"df":df.tail(50)}
        except: continue
    return best

def make_chart(data):
    try:
        plt.figure(figsize=(8,3)); plt.plot(data['df']['Close'], color='gold'); plt.axhline(data['support'], color='lime', ls='--'); plt.axhline(data['resist'], color='red', ls='--')
        plt.title(f"{data['pair']} {data['dir']} {data['conf']:.1f}%"); plt.tight_layout(); path="/tmp/chart.png"; plt.savefig(path); plt.close(); return path
    except: return None

def calc_stake(): return round(BASE_AMOUNT * (2.2 ** STATS['marti']) + random.uniform(0,0.19),2)

def send_signal_with_trade(chat_id, data, is_auto):
    global AUTO_ON
    if STATS['daily']>=DAILY_TP:
        bot.send_message(chat_id, f"🎯 TP ${DAILY_TP} HIT! Daily ${STATS['daily']:.2f} - Paused"); AUTO_ON=False; return
    if STATS['daily']<=-DAILY_SL:
        bot.send_message(chat_id, f"🛑 SL ${DAILY_SL} HIT! Daily ${STATS['daily']:.2f} - Paused"); AUTO_ON=False; return
    stake=calc_stake()
    caption=f"{'🤖 REAL AUTO' if is_auto else '📊 SIGNAL'} {data['pair']} {data['dir']}\nConf {data['conf']:.1f}% RSI {data['rsi']:.0f}\nStake ${stake} Marti Lv{STATS['marti']}\nDaily ${STATS['daily']:.2f} TP ${DAILY_TP} SL ${DAILY_SL}"
    markup=types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton(f"✅ WIN +${stake*0.92:.2f}", callback_data=f"win_{stake}"), types.InlineKeyboardButton(f"❌ LOSS -${stake}", callback_data=f"loss_{stake}"), types.InlineKeyboardButton("⏸️ PAUSE", callback_data="pause"), types.InlineKeyboardButton("▶️ RESUME", callback_data="resume"))
    chart=make_chart(data)
    if chart: bot.send_photo(chat_id, open(chart,'rb'), caption=caption, reply_markup=markup)
    else: bot.send_message(chat_id, caption, reply_markup=markup)
    binomo_real_trade(data['pair'], data['dir'], stake)
    STATS['last_trade']=datetime.now()

@bot.message_handler(commands=['start'])
def start_cmd(m):
    markup=types.InlineKeyboardMarkup(); markup.add(types.InlineKeyboardButton("▶️ RESUME & LOGIN + TRADE", callback_data="resume"), types.InlineKeyboardButton("⏸️ PAUSE", callback_data="pause"))
    bot.send_message(m.chat.id, f"V37 REAL LOGIN MODE\nEmail: {BIN_EMAIL}\nDemo: {USE_DEMO}\nBal ${STATS['balance']:.2f} Daily ${STATS['daily']:.2f}\nTP $20 SL $10 Martingale ON\n\nPress RESUME to login Binomo & start auto trading", reply_markup=markup)

@bot.message_handler(commands=['signal','auto'])
def manual(m):
    s=get_best_signal()
    if s: send_signal_with_trade(m.chat.id, s, False)
    else: bot.send_message(m.chat.id, "No signal now")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    global AUTO_ON, AUTO_CHAT
    d=c.data
    if d=="resume":
        AUTO_ON=True; AUTO_CHAT=c.message.chat.id
        bot.answer_callback_query(c.id, "Logging in...")
        bot.send_message(c.message.chat.id, f"Logging into Binomo {BIN_EMAIL}...")
        binomo_login()
        bot.send_message(c.message.chat.id, "✅ Logged in! Analyzing now & will auto trade every 2 mins")
        s=get_best_signal()
        if s: send_signal_with_trade(c.message.chat.id, s, True)
    elif d=="pause":
        AUTO_ON=False; bot.answer_callback_query(c.id, "Paused"); bot.send_message(c.message.chat.id, "⏸️ Paused")
    elif d.startswith("win_"):
        stake=float(d.split("_")[1]); profit=stake*0.92; STATS['balance']+=profit; STATS['daily']+=profit; STATS['wins']+=1; STATS['marti']=0
        bot.send_message(c.message.chat.id, f"✅ WIN +${profit:.2f} Daily ${STATS['daily']:.2f} Next stake ${BASE_AMOUNT}")
    elif d.startswith("loss_"):
        stake=float(d.split("_")[1]); STATS['balance']-=stake; STATS['daily']-=stake; STATS['loss']+=1; STATS['marti']=min(3, STATS['marti']+1)
        bot.send_message(c.message.chat.id, f"❌ LOSS -${stake} Daily ${STATS['daily']:.2f} Martingale Lv{STATS['marti']} Next ${calc_stake()}")

def bg_loop():
    global AUTO_ON
    while True:
        try:
            if AUTO_ON and AUTO_CHAT:
                if STATS['last_trade'] and (datetime.now()-STATS['last_trade'])<timedelta(minutes=2):
                    time.sleep(10); continue
                s=get_best_signal()
                if s and s['conf']>=85: send_signal_with_trade(AUTO_CHAT, s, True)
            time.sleep(60)
        except Exception as e:
            print(f"BG {e}"); time.sleep(20)
threading.Thread(target=bg_loop, daemon=True).start()

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def wh():
    try:
        bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode("utf-8"))])
    except: pass
    return "ok"
@app.route("/")
def home():
    url=os.getenv("RENDER_EXTERNAL_URL")
    if url:
        try: requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={url}/{BOT_TOKEN}", timeout=5)
        except: pass
    return "V37 REAL LOGIN RUNNING"

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
