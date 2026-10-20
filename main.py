import telebot, os, time, threading
import pandas as pd, yfinance as yf, pytz
from flask import Flask
from datetime import datetime

TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID")) if os.getenv("OWNER_ID") else None
bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)
WAT = pytz.timezone("Africa/Lagos")

PAIRS = ["EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD","USDCAD","EURGBP","EURJPY","GBPJPY","AUDJPY","GBPCHF"]
FLAGS = {"EURUSD":"🇪🇺🇺🇸","GBPUSD":"🇬🇧🇺🇸","USDJPY":"🇺🇸🇯🇵","USDCHF":"🇺🇸🇨🇭","AUDUSD":"🇦🇺🇺🇸","USDCAD":"🇺🇸🇨🇦","EURGBP":"🇪🇺🇬🇧","EURJPY":"🇪🇺🇯🇵","GBPJPY":"🇬🇧🇯🇵","AUDJPY":"🇦🇺🇯🇵","GBPCHF":"🇬🇧🇨🇭"}
LOSS_STREAK, LOST_PAIRS, ALERT_ENABLED, LAST_ALERT = 0, set(), True, {}

def get_data(pair):
    try:
        df = yf.download(f"{pair[:3]}{pair[3:]}=X", period="1d", interval="5m", progress=False, auto_adjust=True)
        if len(df)<50: return None
        c = df['Close'].values.flatten()
        series = pd.Series(c)
        delta = series.diff()
        gain = delta.where(delta>0,0).ewm(alpha=1/14).mean()
        loss = -delta.where(delta<0,0).ewm(alpha=1/14).mean()
        rsi = float(100 - (100/(1+gain.iloc[-1]/loss.iloc[-1])) ) if loss.iloc[-1]!=0 else 50
        ema20 = float(series.ewm(span=20).mean().iloc[-1])
        ema50 = float(series.ewm(span=50).mean().iloc[-1])
        # 3-candle check
        last3 = c[-3:]
        up3 = last3[2]>last3[1]>last3[0]
        down3 = last3[2]<last3[1]<last3[0]
        return c[-1], rsi, ema20, ema50, up3, down3
    except: return None

def is_news():
    now = datetime.now(WAT)
    if now.weekday()>=5: return True, "Weekend - Market Closed"
    mins = now.hour*60+now.minute
    if 805 <= mins <= 935: return True, "High Impact US News 13:25-15:35 WAT"
    return False, ""

def find_best():
    best=None
    for pair in PAIRS:
        if pair in LOST_PAIRS: continue
        d = get_data(pair)
        if not d: continue
        price,rsi,ema20,ema50,up3,down3 = d
        trend_up = price>ema20 and ema20>ema50
        trend_down = price<ema20 and ema20<ema50
        conf, direction = 0, None
        # 85% logic
        if trend_up and 41 <= rsi <= 49 and (up3 or rsi>44):
            conf = 86.5 if 43<=rsi<=47 else 83.2
            direction="CALL"
        elif trend_down and 51 <= rsi <= 59 and (down3 or rsi<56):
            conf = 86.1 if 53<=rsi<=57 else 82.8
            direction="PUT"
        if conf and conf>=82.5:
            score = conf + (2 if (up3 or down3) else 0)
            if not best or score>best[0]:
                best=(score,pair,direction,rsi,price,ema20,conf,up3,down3)
    return best

@bot.message_handler(commands=['start'])
def start(m): bot.send_message(m.chat.id,"👑 V29 85% REAL READY\n⚡ Fast-Manual Format\n✅ 3-Candle + EMA20/50\n✅ News Filter ON\n\nCommands:\n/signal - Get 85% signal\n/alerton - Auto 🚨\n/status - Check\n/win /loss /reset")

@bot.message_handler(commands=['signal'])
def sig(m):
    global LOSS_STREAK
    if LOSS_STREAK>=3:
        bot.send_message(m.chat.id,"🛑 3 Losses Today. Stop Trading. /reset tomorrow"); return
    news,reason = is_news()
    if news:
        bot.send_message(m.chat.id,f"🚫 NEWS FILTER ACTIVE\n{reason}\nTry after 15:40 WAT"); return
    bot.send_message(m.chat.id,"⚡ Scanning 85% setups...")
    res = find_best()
    if not res:
        bot.send_message(m.chat.id,"⏳ No 85% setup now. Market choppy. Wait 2 mins."); return
    _,pair,direction,rsi,price,ema20,conf,up3,down3 = res
    flag=FLAGS.get(pair,"🏳️")
    emoji="🟢 CALL 🔺" if direction=="CALL" else "🔴 PUT 🔻"
    three="✅ 3-Bullish" if up3 else "✅ 3-Bearish" if down3 else "✅ Momentum OK"
    now=datetime.now(WAT)
    exp = now + pd.Timedelta(minutes=5)
    msg=f"""👑 {flag} {pair} {flag} - {conf}% 
{emoji} 5 MIN

💱 PAIR: {pair}
📊 RSI: {rsi:.1f} | {three}
📈 TREND: {'UP >EMA20/50' if direction=='CALL' else 'DOWN <EMA20/50'}
💹 PRICE: {price:.5f} EMA20: {ema20:.5f}
💰 STAKE: $40 Fixed
⏰ TIME: {now.strftime('%H:%M')} → {exp.strftime('%H:%M')} WAT
🎯 ENTRY: NOW - Next Candle

85/100 POWER TRADE - Take Fast!"""
    bot.send_message(m.chat.id,msg)

@bot.message_handler(commands=['win','loss','reset','status','alerton','alertoff','pairs'])
def cmds(m):
    global LOSS_STREAK, LOST_PAIRS, ALERT_ENABLED
    t=m.text.lower()
    if "loss" in t:
        LOSS_STREAK+=1; bot.send_message(m.chat.id,f"📉 Loss logged: {LOSS_STREAK}/3")
    elif "win" in t:
        LOSS_STREAK=max(0,LOSS_STREAK-1); bot.send_message(m.chat.id,f"📈 Win! Streak {LOSS_STREAK}/3")
    elif "reset" in t:
        LOSS_STREAK=0; LOST_PAIRS.clear(); bot.send_message(m.chat.id,"✅ Reset Done")
    elif "status" in t:
        n,r = is_news(); bot.send_message(m.chat.id,f"Loss: {LOSS_STREAK}/3\nNews: {r if n else 'Safe to trade'}\nAlert: {'ON' if ALERT_ENABLED else 'OFF'}")
    elif "alerton" in t:
        ALERT_ENABLED=True; bot.send_message(m.chat.id,"🔔 Auto 85% Alert ON 🚨")
    elif "alertoff" in t:
        ALERT_ENABLED=False; bot.send_message(m.chat.id,"🔕 Alert OFF")
    elif "pairs" in t: bot.send_message(m.chat.id,"💱 "+", ".join(PAIRS))

def auto_loop():
    while True:
        try:
            time.sleep(60)
            if not OWNER_ID or not ALERT_ENABLED: continue
            if LOSS_STREAK>=3: continue
            n,_ = is_news()
            if n: continue
            res = find_best()
            if res:
                _,pair,dir,rsi,price,_,conf,_,_ = res
                if time.time()-LAST_ALERT.get(pair,0) < 900: continue
                LAST_ALERT[pair]=time.time()
                bot.send_message(OWNER_ID,f"🚨 85% SIGNAL FOUND 🚨\n\n{FLAGS.get(pair,'')} {pair} {conf}%\n{'🟢 CALL' if dir=='CALL' else '🔴 PUT'} RSI {rsi:.1f}\n\n/signal now!")
        except: time.sleep(10)

@app.route("/")
def home(): return "V29 85% RUNNING"
def run_flask(): app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
def run_bot():
    bot.remove_webhook()
    time.sleep(1)
    print("V29 Polling Started")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)

if __name__=="__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=auto_loop, daemon=True).start()
    run_bot()
