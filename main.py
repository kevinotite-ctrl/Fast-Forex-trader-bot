# V8 - FINAL FIX ZIP INSTALLER - NO CRASH
import os, sys, time, threading, random, subprocess, requests
from flask import Flask, request
import telebot

print("=== V8 START ===", flush=True)
app = Flask(__name__)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PO_EMAIL = os.getenv("PO_EMAIL")
PO_PASSWORD = os.getenv("PO_PASSWORD")

USE_DEMO=True
BASE_AMOUNT=1
MARTINGALE=[1,2,4]
MAX_M=3
SCAN_INTERVAL=30
EXPIRY=60
PAIRS=["EURUSD","GBPUSD","USDJPY","EURJPY","AUDUSD","USDCAD"]

OWNER_ID=None
PO_CLIENT=None
SCANNING=True
NEXT_SCAN=time.time()+30
cur_amt=1
mart_lv=0
DLOSS=0
DWIN=0

bot=telebot.TeleBot(TOKEN)

def ema(c,p):
    e=c[0]; k=2/(p+1)
    for x in c[1:]: e=x*k+e*(1-k)
    return e

def rsi(c,per=7):
    g=[]; l=[]
    for i in range(1,len(c)):
        d=c[i]-c[i-1]; g.append(max(d,0)); l.append(max(-d,0))
    if len(g)<per: return 50
    ag=sum(g[-per:])/per; al=sum(l[-per:])/per
    if al==0: return 70
    return 100-(100/(1+ag/al))

def ensure_po():
    try:
        import pocketoptionapi
        print("PO lib OK", flush=True)
        return True
    except:
        print("Installing PO ZIP...", flush=True)
        try:
            subprocess.check_call([sys.executable,"-m","pip","install","--no-cache-dir","https://github.com/ChipaDevTeam/PocketOptionAPI/archive/refs/heads/main.zip"])
            import pocketoptionapi
            print("ZIP Installed OK", flush=True)
            return True
        except Exception as e:
            print(f"ZIP install fail {e}", flush=True)
            return False

def po_connect():
    global PO_CLIENT
    if not ensure_po():
        return False
    try:
        print("🔌 Connecting...", flush=True)
        from pocketoptionapi.stable_api import PocketOption
        client=PocketOption(PO_EMAIL,PO_PASSWORD)
        client.connect()
        time.sleep(5)
        if USE_DEMO:
            try: client.change_balance("DEMO")
            except: pass
        time.sleep(2)
        bal=client.get_balance()
        print(f"✅ CONNECTED Bal {bal}", flush=True)
        class W:
            def __init__(self,c): self.c=c
            def balance(self): return self.c.get_balance()
            def get_candles(self,p,tf,cnt):
                try: return self.c.get_candles(p,tf,cnt)
                except: return self.c.get_candles(p,cnt)
            def buy(self,a,p,d,e): return self.c.buy(a,p,d,e)[0],None
            def check_win(self,i): return self.c.check_win(i)
        PO_CLIENT=W(client)
        return True
    except Exception as e:
        print(f"Connect fail {e}", flush=True)
        import traceback; traceback.print_exc()
        return False

def analyze(pair):
    try:
        candles=PO_CLIENT.get_candles(pair,60,50)
        closes=[]
        for c in candles:
            if isinstance(c,dict): closes.append(c.get('close',0))
            elif isinstance(c,(list,tuple)): closes.append(c[2] if len(c)>2 else c[0])
            else: closes.append(float(c))
        if len(closes)<30: return None,"No candles",0
        e9=ema(closes[-20:],9); e21=ema(closes,21); r=rsi(closes,7)
        cl=closes[-1]
        if cl>e9 and e9>e21 and 48<=r<=75: return "call",f"📈 UP E9 {round(e9,5)} > E21 {round(e21,5)} RSI {round(r,1)} 🔥",85
        if cl<e9 and e9<e21 and 25<=r<=52: return "put",f"📉 DOWN E9 {round(e9,5)} < E21 {round(e21,5)} RSI {round(r,1)} 🔥",85
        return None,f"⏳ RSI {round(r,1)}",0
    except Exception as e:
        return None,f"Err {e}",0

@app.route('/')
def home():
    try: b=PO_CLIENT.balance() if PO_CLIENT else 0
    except: b=0
    return f"DEMO ONLINE Bal {b} Next ${cur_amt}"

@app.route(f'/{TOKEN}', methods=['POST'])
def wh():
    try: bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('UTF-8'))])
    except: pass
    return "OK",200

@bot.message_handler(commands=['start'])
def st(m):
    global OWNER_ID
    OWNER_ID=m.chat.id
    bot.send_message(m.chat.id,"🔌 Connecting 15s...")
    ok=po_connect()
    try: bal=PO_CLIENT.balance() if ok else "?"
    except: bal="?"
    if ok: bot.send_message(m.chat.id,f"⚡ AUTO ✅\n🧪 DEMO\n💼 ${bal}\n💵 Next ${cur_amt}\nAuto ON")
    else: bot.send_message(m.chat.id,f"❌ Fail - check Render Build logs not Runtime logs\nBal {bal}")

@bot.message_handler(commands=['balance','pause','resume'])
def cm(m):
    global SCANNING,cur_amt,mart_lv,NEXT_SCAN,OWNER_ID
    OWNER_ID=m.chat.id
    t=m.text.lower()
    if '/pause' in t: SCANNING=False; bot.send_message(m.chat.id,"⏸️ PAUSED")
    elif '/resume' in t: SCANNING=True; NEXT_SCAN=time.time()+10; bot.send_message(m.chat.id,"▶️ RESUMED")
    elif '/balance' in t:
        try: bal=PO_CLIENT.balance(); bot.send_message(m.chat.id,f"💰 ${round(bal,2)} Next ${cur_amt} 🏆 {DWIN} 📉 {DLOSS}")
        except: bot.send_message(m.chat.id,"❌ /start")

def loop():
    global NEXT_SCAN,cur_amt,mart_lv,DLOSS,DWIN
    while True:
        time.sleep(3)
        if not OWNER_ID or not SCANNING or time.time()<NEXT_SCAN: continue
        if PO_CLIENT is None and not po_connect():
            NEXT_SCAN=time.time()+SCAN_INTERVAL; continue
        pairs=PAIRS[:]; random.shuffle(pairs)
        traded=False
        for pair in pairs:
            d,rs,conf=analyze(pair)
            if d and conf>=75:
                traded=True
                try:
                    msg=bot.send_message(OWNER_ID,f"🚀 {conf}% {pair} {d.upper()} ${cur_amt}\n{rs}\nPlacing...")
                    tid,_=PO_CLIENT.buy(cur_amt,pair,d,EXPIRY)
                    bot.edit_message_text(f"✅ PLACED {pair} {d.upper()} ${cur_amt}\n{rs}\n⌛ 70s...",OWNER_ID,msg.message_id)
                    time.sleep(70)
                    res=PO_CLIENT.check_win(tid)
                    prof=res if isinstance(res,(int,float)) else res.get('profit',0) if isinstance(res,dict) else 0
                    win=prof>0
                    bal=PO_CLIENT.balance()
                    if win:
                        DWIN+=1; mart_lv=0; cur_amt=MARTINGALE[0]
                        bot.edit_message_text(f"💰✅ WIN +${round(prof,2)} 💼 ${round(bal,2)} Next ${cur_amt}",OWNER_ID,msg.message_id)
                    else:
                        DLOSS+=1; mart_lv+=1
                        if mart_lv>=MAX_M: mart_lv=0; cur_amt=MARTINGALE[0]
                        else: cur_amt=MARTINGALE[mart_lv]
                        bot.edit_message_text(f"📉❌ LOSS 💼 ${round(bal,2)} Next ${cur_amt} Lvl {mart_lv+1}",OWNER_ID,msg.message_id)
                    NEXT_SCAN=time.time()+SCAN_INTERVAL
                    break
                except Exception as e: print(f"Trade err {e}",flush=True); continue
        if not traded: NEXT_SCAN=time.time()+SCAN_INTERVAL

threading.Thread(target=loop,daemon=True).start()

if __name__=="__main__":
    try:
        bot.remove_webhook(); time.sleep(1)
        ext=os.getenv("RENDER_EXTERNAL_URL")
        if ext: bot.set_webhook(url=f"{ext}/{TOKEN}")
    except: pass
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
