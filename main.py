# FAST FOREX V4 - FIX BALANCE + STABLE_API + DEMO AUTO + EMOJI EDIT
import os, time, threading, random, requests
from flask import Flask, request
import telebot

print("=== FAST AUTO DEMO EMOJI V4 FIX ===", flush=True)
app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PO_EMAIL = os.getenv("PO_EMAIL")
PO_PASSWORD = os.getenv("PO_PASSWORD")

# ===== SETTINGS =====
USE_DEMO = True # True = DEMO 🧪
BASE_AMOUNT = 1
MARTINGALE_AMOUNTS = [1, 2, 4]
MAX_MARTINGALE = 3
SCAN_INTERVAL = 25
EXPIRY = 60
FAST_PAIRS = ["EURUSD","GBPUSD","USDJPY","EURJPY","AUDUSD","USDCAD"]

OWNER_ID = None
PO_CLIENT = None
SCANNING = True
NEXT_SCAN_AT = time.time() + 20
current_amount = 1
martingale_level = 0
DAILY_LOSS = 0
DAILY_WIN = 0

bot = telebot.TeleBot(TOKEN)

def get_ema(closes, p):
    ema=closes[0]; k=2/(p+1)
    for c in closes[1:]: ema=c*k+ema*(1-k)
    return ema

def get_rsi(closes, period=7):
    gains=[]; losses=[]
    for i in range(1,len(closes)):
        d=closes[i]-closes[i-1]
        gains.append(max(d,0)); losses.append(max(-d,0))
    if len(gains)<period: return 50
    ag=sum(gains[-period:])/period; al=sum(losses[-period:])/period
    if al==0: return 70
    return 100-(100/(1+ag/al))

def po_connect():
    global PO_CLIENT
    try:
        print("🔌 Trying PO connect...", flush=True)
        # TRY 1: stable_api (new ChipaDev)
        try:
            from pocketoptionapi.stable_api import PocketOption as POStable
            print(f"Using stable_api with demo={USE_DEMO}", flush=True)
            client = POStable(PO_EMAIL, PO_PASSWORD)
            # some versions need demo flag in connect
            try:
                connected = client.connect()
            except:
                connected = client.connect()
            print(f"Stable connect raw: {connected}", flush=True)
            time.sleep(5)
            # switch to DEMO
            if USE_DEMO:
                try:
                    client.change_balance("DEMO")
                    print("Switched to DEMO", flush=True)
                    time.sleep(2)
                except Exception as e:
                    print(f"change_balance DEMO fail {e}", flush=True)
            bal = client.get_balance()
            print(f"✅ STABLE CONNECTED Bal {bal}", flush=True)
            # wrap to keep old interface
            class Wrapper:
                def __init__(self, c): self.c=c
                def balance(self):
                    try: return self.c.get_balance()
                    except: return 0
                def get_candles(self, pair, tf, count):
                    try: return self.c.get_candles(pair, tf, count)
                    except: return self.c.get_candles(pair, count)
                def buy(self, amount, pair, direction, expiry):
                    try:
                        # stable_api buy returns tuple or dict
                        res = self.c.buy(amount, pair, direction, expiry)
                        # normalize to trade_id
                        if isinstance(res, tuple):
                            return res[0], res[1] if len(res)>1 else None
                        return res, None
                    except Exception as e:
                        print(f"buy err {e}", flush=True)
                        raise e
                def check_win(self, trade_id):
                    try:
                        res = self.c.check_win(trade_id)
                        return res
                    except:
                        return -1
            PO_CLIENT = Wrapper(client)
            return True
        except Exception as e:
            print(f"Stable fail: {e}", flush=True)

        # TRY 2: ssid old api
        try:
            from pocketoptionapi import PocketOption
            s=requests.Session()
            r=s.post("https://api.pocketoption.com/login", json={"email":PO_EMAIL,"password":PO_PASSWORD}, timeout=15)
            print(f"Login status {r.status_code}", flush=True)
            ssid=s.cookies.get_dict().get('ssid')
            if ssid:
                try:
                    PO_CLIENT=PocketOption(ssid, demo=USE_DEMO)
                except:
                    PO_CLIENT=PocketOption(ssid)
                time.sleep(3)
                try: PO_CLIENT.change_balance("DEMO")
                except: pass
                b=PO_CLIENT.balance()
                print(f"✅ SSID CONNECTED Bal {b}", flush=True)
                return True
        except Exception as e:
            print(f"SSID login fail: {e}", flush=True)

        # TRY 3: direct old api
        try:
            from pocketoptionapi import PocketOption
            try:
                PO_CLIENT=PocketOption(PO_EMAIL, PO_PASSWORD, demo=USE_DEMO)
            except:
                PO_CLIENT=PocketOption(PO_EMAIL, PO_PASSWORD)
            time.sleep(3)
            try: PO_CLIENT.change_balance("DEMO")
            except: pass
            b=PO_CLIENT.balance()
            print(f"✅ DIRECT CONNECTED Bal {b}", flush=True)
            return True
        except Exception as e:
            print(f"Direct fail: {e}", flush=True)
            return False

    except Exception as e:
        print(f"PO FAIL ALL: {e}", flush=True)
        return False

def analyze_fast(pair):
    try:
        candles=PO_CLIENT.get_candles(pair,60,50)
        closes=[]
        for c in candles:
            if isinstance(c, dict):
                closes.append(c.get('close', c.get('price',0)))
            elif isinstance(c, (list,tuple)):
                closes.append(c[2] if len(c)>2 else c[0])
            else:
                closes.append(float(c))
        if len(closes)<30: return None,"No candles",0
        ema9=get_ema(closes[-20:],9); ema21=get_ema(closes,21); rsi=get_rsi(closes,7)
        close=closes[-1]
        if close>ema9 and ema9>ema21 and 48<=rsi<=75:
            return "call",f"📈 FAST UP | EMA9 {round(ema9,5)} > EMA21 {round(ema21,5)} | RSI {round(rsi,1)} 🔥",85
        if close<ema9 and ema9<ema21 and 25<=rsi<=52:
            return "put",f"📉 FAST DOWN | EMA9 {round(ema9,5)} < EMA21 {round(ema21,5)} | RSI {round(rsi,1)} 🔥",85
        return None,f"⏳ WAIT RSI {round(rsi,1)}",0
    except Exception as e:
        return None,f"Err {e}",0

@app.route('/')
def home():
    try: b=PO_CLIENT.balance() if PO_CLIENT else 0
    except: b=0
    mode="DEMO 🧪" if USE_DEMO else "REAL 💸"
    return f"AUTO {mode} ONLINE Bal {b} Next ${current_amount} Lvl {martingale_level+1}"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try: bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('UTF-8'))])
    except: pass
    return "OK",200

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID
    OWNER_ID=m.chat.id
    bot.send_message(m.chat.id, "🔌 Connecting to PocketOption DEMO... wait 10s")
    ok = po_connect()
    try: bal=PO_CLIENT.balance() if ok else "?"
    except: bal="?"
    mode="DEMO 🧪" if USE_DEMO else "REAL 💸"
    if ok:
        bot.send_message(m.chat.id, f"⚡🤖 FAST FOREX AUTO-TRADER ✅\n🧪 Mode: {mode}\n💼 Bal: ${bal}\n💵 Next Trade: ${current_amount} (Lvl {martingale_level+1})\n🎯 Auto Place: ON\n\n📋 Commands:\n/balance\n/pause ⏸️\n/resume ▶️\n/reset 🔄\n/scan 🔍")
    else:
        bot.send_message(m.chat.id, f"❌ PO Login Failed\nCheck logs in Render. Make sure 2FA OFF and email/pass correct.\nBal: {bal}")

@bot.message_handler(commands=['balance','pause','resume','scan','reset'])
def cmds(m):
    global SCANNING, current_amount, martingale_level, NEXT_SCAN_AT, OWNER_ID
    OWNER_ID=m.chat.id
    txt=m.text.lower()
    if '/pause' in txt:
        SCANNING=False; bot.send_message(m.chat.id,"⏸️ Trading PAUSED")
    elif '/resume' in txt:
        SCANNING=True; NEXT_SCAN_AT=time.time()+10; bot.send_message(m.chat.id,"▶️ Trading RESUMED - Auto ON 🔥 DEMO 🧪")
    elif '/balance' in txt:
        try:
            bal=PO_CLIENT.balance()
            mode="DEMO 🧪" if USE_DEMO else "REAL 💸"
            bot.send_message(m.chat.id,f"🧪 Mode: {mode}\n💰 Balance: ${round(bal,2)}\n💵 Next: ${current_amount} Lvl {martingale_level+1}\n🏆 Wins: {DAILY_WIN} | 📉 Losses: {DAILY_LOSS}")
        except:
            bot.send_message(m.chat.id,"❌ PO not connected - send /start")
    elif '/reset' in txt:
        martingale_level=0; current_amount=BASE_AMOUNT; bot.send_message(m.chat.id,f"🔄 Reset to ${BASE_AMOUNT} ✨")
    elif '/scan' in txt:
        bot.send_message(m.chat.id,"🔍 Scanning now...")

def auto_trade_loop():
    global NEXT_SCAN_AT, current_amount, martingale_level, DAILY_LOSS, DAILY_WIN
    while True:
        time.sleep(2)
        if not OWNER_ID or not SCANNING or time.time()<NEXT_SCAN_AT:
            continue
        if PO_CLIENT is None and not po_connect():
            NEXT_SCAN_AT=time.time()+SCAN_INTERVAL; continue
        pairs=FAST_PAIRS[:]; random.shuffle(pairs)
        traded=False
        for pair in pairs:
            direction, reason, conf = analyze_fast(pair)
            if direction and conf>=75:
                traded=True
                try:
                    msg = bot.send_message(OWNER_ID, f"🚀 SIGNAL FOUND {conf}%\n💱 {pair} | {direction.upper()} 🔥\n💵 Amount: ${current_amount} (Lvl {martingale_level+1})\n🧪 DEMO\n📊 {reason}\n⏳ Placing trade...")
                    try:
                        trade_id, _ = PO_CLIENT.buy(current_amount, pair, direction, EXPIRY)
                    except Exception as e:
                        bot.edit_message_text(f"❌ Trade failed {pair}: {e}", OWNER_ID, msg.message_id)
                        continue
                    bot.edit_message_text(f"✅ TRADE PLACED 🚀\n💱 {pair} | {direction.upper()} | ${current_amount}\n🧪 DEMO\n⏱️ Expiry: {EXPIRY}s | Conf: {conf}%\n📊 {reason}\n⌛ Waiting result...", OWNER_ID, msg.message_id)
                    time.sleep(70)
                    try:
                        res=PO_CLIENT.check_win(trade_id)
                        if isinstance(res, dict):
                            profit=res.get('profit',0)
                        elif isinstance(res,(int,float)):
                            profit=res
                        else:
                            profit=0
                        win=profit>0
                    except:
                        profit=-current_amount; win=False
                    try: bal=PO_CLIENT.balance()
                    except: bal=0
                    if win:
                        DAILY_WIN+=1
                        martingale_level=0
                        current_amount=MARTINGALE_AMOUNTS[0]
                        bot.edit_message_text(f"💰✅ WIN ✅💰\n💱 {pair} | {direction.upper()}\n💵 Profit: +${round(profit,2)} 🤑\n💼 Balance: ${round(bal,2)}\n🧪 DEMO\n🏆 Wins Today: {DAILY_WIN} 🎉\n💵 Next: ${current_amount}", OWNER_ID, msg.message_id)
                    else:
                        DAILY_LOSS+=1
                        martingale_level+=1
                        if martingale_level>=MAX_MARTINGALE:
                            martingale_level=0; current_amount=MARTINGALE_AMOUNTS[0]
                            bot.edit_message_text(f"📉❌ LOSS ❌📉\n💱 {pair} | {direction.upper()}\n💸 Lost: -${MARTINGALE_AMOUNTS[-1]} 😢\n💼 Balance: ${round(bal,2)}\n🧪 DEMO\n🔄 RESET to ${current_amount}\n📊 Losses: {DAILY_LOSS}", OWNER_ID, msg.message_id)
                        else:
                            current_amount=MARTINGALE_AMOUNTS[martingale_level]
                            bot.edit_message_text(f"📉❌ LOSS ❌📉\n💱 {pair} | {direction.upper()}\n💸 Lost 😢\n💼 Balance: ${round(bal,2)}\n🧪 DEMO\n➡️ Next: ${current_amount} (Lvl {martingale_level+1}) 🔁\n📊 Losses: {DAILY_LOSS}", OWNER_ID, msg.message_id)
                    NEXT_SCAN_AT=time.time()+SCAN_INTERVAL
                    break
                except Exception as e:
                    print(f"Trade err {e}", flush=True)
                    continue
        if not traded:
            NEXT_SCAN_AT=time.time()+SCAN_INTERVAL

threading.Thread(target=auto_trade_loop, daemon=True).start()

if __name__=="__main__":
    try:
        bot.remove_webhook(); time.sleep(1)
        ext=os.getenv("RENDER_EXTERNAL_URL")
        if ext: bot.set_webhook(url=f"{ext}/{TOKEN}")
    except: pass
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
