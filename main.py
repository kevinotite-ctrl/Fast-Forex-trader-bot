# FAST FOREX V7 - NO CRASH - LAZY IMPORT
import os, sys, time, threading, random, requests, subprocess
from flask import Flask, request
import telebot

print("=== FAST V7 STARTING ===", flush=True)
app = Flask(__name__)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PO_EMAIL = os.getenv("PO_EMAIL")
PO_PASSWORD = os.getenv("PO_PASSWORD")

USE_DEMO = True
BASE_AMOUNT = 1
MARTINGALE_AMOUNTS = [1, 2, 4]
MAX_MARTINGALE = 3
SCAN_INTERVAL = 30
EXPIRY = 60
FAST_PAIRS = ["EURUSD","GBPUSD","USDJPY","EURJPY","AUDUSD","USDCAD"]

OWNER_ID = None
PO_CLIENT = None
SCANNING = True
NEXT_SCAN_AT = time.time() + 30
current_amount = 1
martingale_level = 0
DAILY_LOSS = 0
DAILY_WIN = 0

bot = telebot.TeleBot(TOKEN)

def get_ema(c,p):
    e=c[0]; k=2/(p+1)
    for x in c[1:]: e=x*k+e*(1-k)
    return e

def get_rsi(c,per=7):
    g=[]; l=[]
    for i in range(1,len(c)):
        d=c[i]-c[i-1]
        g.append(max(d,0)); l.append(max(-d,0))
    if len(g)<per: return 50
    ag=sum(g[-per:])/per; al=sum(l[-per:])/per
    if al==0: return 70
    return 100-(100/(1+ag/al))

def ensure_po_installed():
    try:
        import pocketoptionapi
        return True
    except:
        print("PO not installed, installing now...", flush=True)
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--no-cache-dir", "git+https://github.com/ChipaDevTeam/PocketOptionAPI.git"])
            print("Installed!", flush=True)
            return True
        except Exception as e:
            print(f"Install fail {e}", flush=True)
            return False

def po_connect():
    global PO_CLIENT
    if not ensure_po_installed():
        return False
    try:
        print("🔌 Trying PO connect...", flush=True)
        from pocketoptionapi.stable_api import PocketOption
        client = PocketOption(PO_EMAIL, PO_PASSWORD)
        client.connect()
        time.sleep(5)
        if USE_DEMO:
            try: client.change_balance("DEMO")
            except: pass
            time.sleep(2)
        bal = client.get_balance()
        print(f"✅ CONNECTED Bal {bal}", flush=True)
        class W:
            def __init__(self,c): self.c=c
            def balance(self): return self.c.get_balance()
            def get_candles(self,p,tf,cnt):
                try: return self.c.get_candles(p,tf,cnt)
                except: return self.c.get_candles(p,cnt)
            def buy(self,a,p,d,e): return self.c.buy(a,p,d,e)[0],None
            def check_win(self,i): return self.c.check_win(i)
        PO_CLIENT = W(client)
        return True
    except Exception as e:
        print(f"Connect fail: {e}", flush=True)
        import traceback; traceback.print_exc()
        return False

def analyze_fast(pair):
    try:
        candles=PO_CLIENT.get_candles(pair,60,50)
        closes=[]
        for c in candles:
            if isinstance(c,dict): closes.append(c.get('close',0))
            elif isinstance(c,(list,tuple)): closes.append(c[2] if len(c)>2 else c[0])
            else: closes.append(float(c))
        if len(closes)<30: return None,"No candles",0
        ema9=get_ema(closes[-20:],9); ema21=get_ema(closes,21); rsi=get_rsi(closes,7)
        close=closes[-1]
        if close>ema9 and ema9>ema21 and 48<=rsi<=75:
            return "call",f"📈 UP EMA9 {round(ema9,5)} > {round(ema21,5)} RSI {round(rsi,1)} 🔥",85
        if close<ema9 and ema9<ema21 and 25<=rsi<=52:
            return "put",f"📉 DOWN EMA9 {round(ema9,5)} < {round(ema21,5)} RSI {round(rsi,1)} 🔥",85
        return None,f"⏳ RSI {round(rsi,1)}",0
    except Exception as e:
        return None,f"Err {e}",0

@app.route('/')
def home():
    try: b=PO_CLIENT.balance() if PO_CLIENT else 0
    except: b=0
    return f"AUTO DEMO ONLINE Bal {b} Next ${current_amount}"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try: bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('UTF-8'))])
    except: pass
    return "OK",200

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID
    OWNER_ID=m.chat.id
    bot.send_message(m.chat.id,"🔌 Connecting... wait 15s")
    ok=po_connect()
    try: bal=PO_CLIENT.balance() if ok else "?"
    except: bal="?"
    if ok: bot.send_message(m.chat.id,f"⚡ AUTO-TRADER ✅\n🧪 DEMO\n💼 Bal: ${bal}\n💵 Next: ${current_amount}\n🎯 Auto ON")
    else: bot.send_message(m.chat.id,f"❌ Failed - check logs\nBal: {bal}")

@bot.message_handler(commands=['balance','pause','resume','scan','reset'])
def cmds(m):
    global SCANNING, current_amount, martingale_level, NEXT_SCAN_AT, OWNER_ID
    OWNER_ID=m.chat.id
    t=m.text.lower()
    if '/pause' in t: SCANNING=False; bot.send_message(m.chat.id,"⏸️ PAUSED")
    elif '/resume' in t: SCANNING=True; NEXT_SCAN_AT=time.time()+10; bot.send_message(m.chat.id,"▶️ RESUMED 🔥")
    elif '/balance' in t:
        try: bal=PO_CLIENT.balance(); bot.send_message(m.chat.id,f"💰 ${round(bal,2)}\n💵 Next ${current_amount}\n🏆 {DAILY_WIN} | 📉 {DAILY_LOSS}")
        except: bot.send_message(m.chat.id,"❌ Not connected /start")
    elif '/reset' in t: martingale_level=0; current_amount=BASE_AMOUNT; bot.send_message(m.chat.id,f"🔄 Reset ${BASE_AMOUNT}")
    elif '/scan' in t: bot.send_message(m.chat.id,"🔍 Scanning...")

def auto_loop():
    global NEXT_SCAN_AT, current_amount, martingale_level, DAILY_LOSS, DAILY_WIN
    while True:
        time.sleep(3)
        if not OWNER_ID or not SCANNING or time.time()<NEXT_SCAN_AT: continue
        if PO_CLIENT is None and not po_connect():
            NEXT_SCAN_AT=time.time()+SCAN_INTERVAL; continue
        pairs=FAST_PAIRS[:]; random.shuffle(pairs)
        traded=False
        for pair in pairs:
            d,rs,conf=analyze_fast(pair)
            if d and conf>=75:
                traded=True
                try:
                    msg=bot.send_message(OWNER_ID,f"🚀 {conf}%\n💱 {pair} {d.upper()}\n💵 ${current_amount}\n📊 {rs}\n⏳ Placing...")
                    tid,_=PO_CLIENT.buy(current_amount,pair,d,EXPIRY)
                    bot.edit_message_text(f"✅ PLACED {pair} {d.upper()} ${current_amount} 🧪\n📊 {rs}\n⌛ Waiting...",OWNER_ID,msg.message_id)
                    time.sleep(70)
                    res=PO_CLIENT.check_win(tid)
                    prof=res if isinstance(res,(int,float)) else res.get('profit',0) if isinstance(res,dict) else 0
                    win=prof>0
                    try: bal=PO_CLIENT.balance()
                    except: bal=0
                    if win:
                        DAILY_WIN+=1; martingale_level=0; current_amount=MARTINGALE_AMOUNTS[0]
                        bot.edit_message_text(f"💰✅ WIN +${round(prof,2)} 🤑\n💼 ${round(bal,2)}\n🏆 {DAILY_WIN}\nNext ${current_amount}",OWNER_ID,msg.message_id)
                    else:
                        DAILY_LOSS+=1; martingale_level+=1
                        if martingale_level>=MAX_MARTINGALE: martingale_level=0; current_amount=MARTINGALE_AMOUNTS[0]
                        else: current_amount=MARTINGALE_AMOUNTS[martingale_level]
                        bot.edit_message_text(f"📉❌ LOSS {pair} 😢\n💼 ${round(bal,2)}\n➡️ Next ${current_amount} Lvl {martingale_level+1}",OWNER_ID,msg.message_id)
                    NEXT_SCAN_AT=time.time()+SCAN_INTERVAL
                    break
                except Exception as e: print(f"Trade err {e}",flush=True); continue
        if not traded: NEXT_SCAN_AT=time.time()+SCAN_INTERVAL

threading.Thread(target=auto_loop,daemon=True).start()

if __name__=="__main__":
    try: bot.remove_webhook(); time.sleep(1); ext=os.getenv("RENDER_EXTERNAL_URL");
    except: pass
    try:
        if ext: bot.set_webhook(url=f"{ext}/{TOKEN}")
    except: pass
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
