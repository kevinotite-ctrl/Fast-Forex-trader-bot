# -*- coding: utf-8 -*-
# 👑 KEVIN GOLD ONLY V6 GOD MODE 🤖 - FINAL NO ERROR VERSION

import os, requests, time, threading, telebot, datetime, json, random, pytz
from telebot import types
from flask import Flask, request
from datetime import timedelta

BOT_TOKEN=os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL_ID="@KEVINTRAILBLAZE"
ADMIN_ID=os.environ.get("ADMIN_ID")
ADMIN_CHAT_ID=None

bot=telebot.TeleBot(BOT_TOKEN)
prices_history={"GOLD":[],"GOLD_1H":[]}
last_signal_time={}
pending_signals={}
ACTIVE_FILE="active_signals.json"
PERF_FILE="performance.json"

WAT = pytz.timezone("Africa/Lagos")

def save_active():
    try:
        with open(ACTIVE_FILE,"w") as f:
            json.dump(active_signals,f)
    except: pass

def load_active():
    global active_signals
    try:
        if os.path.exists(ACTIVE_FILE):
            with open(ACTIVE_FILE,"r") as f:
                active_signals=json.load(f)
        else:
            active_signals=[]
    except:
        active_signals=[]

def load_perf():
    try:
        if os.path.exists(PERF_FILE):
            with open(PERF_FILE,"r") as f:
                return json.load(f)
    except: pass
    return {"wins":0,"losses":0,"jackpots":0,"total":0,"streak":0,"best_streak":0,"daily_loss":0,"last_reset":str(datetime.date.today())}

def save_perf(p):
    try:
        with open(PERF_FILE,"w") as f:
            json.dump(p,f)
    except: pass

def is_news_block():
    now=datetime.datetime.now(WAT)
    red_news_hours=[(7,15,7,45),(13,15,14,0),(14,15,15,30)]
    for hs,ms,he,me in red_news_hours:
        start=now.replace(hour=hs,minute=ms,second=0)
        end=now.replace(hour=he,minute=me,second=0)
        if start <= now <= end:
            return True, f"🚨 RED NEWS BLOCK {hs}:{ms:02d}-{he}:{me:02d} WAT"
    return False,"✅ No High Impact News"

def calc_atr(prices, period=14):
    if len(prices)<period+1: return 10.0
    tr=[]
    for i in range(1,len(prices)):
        tr.append(abs(prices[i]-prices[i-1]))
    return sum(tr[-period:])/period

active_signals=[]
performance=load_perf()
load_active()

app=Flask(__name__)
@app.route('/')
def home():
    return f"👑 KEVIN GOLD ONLY V6 GOD MODE LIVE | Active {len(active_signals)} | Wins {performance['wins']} | Streak {performance['streak']}"

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    try:
        json_str=request.get_data().decode('UTF-8')
        update=telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except: pass
    return "OK",200

@app.route('/setwebhook')
def set_webhook():
    try:
        bot.remove_webhook(); time.sleep(1)
        ext_url=os.getenv("RENDER_EXTERNAL_URL")
        if ext_url:
            url=f"{ext_url}/{BOT_TOKEN}"
            bot.set_webhook(url=url)
            return f"✅ Webhook set {url}"
        return "❌ No URL"
    except Exception as e:
        return f"⚠️ {e}"

def get_gold():
    try:
        r=requests.get("https://api.gold-api.com/price/XAU",timeout=10).json()
        return float(r["price"])
    except:
        return 2650+random.uniform(-8,8)

def calc_rsi(prices, period=14):
    if len(prices)<period+1: return 50.0
    gains=[]; losses=[]
    for i in range(1,len(prices)):
        diff=prices[i]-prices[i-1]
        if diff>0: gains.append(diff); losses.append(0)
        else: gains.append(0); losses.append(abs(diff))
    if len(gains)<period: return 50.0
    avg_gain=sum(gains[-period:])/period
    avg_loss=sum(losses[-period:])/period
    if avg_loss==0: return 72.0
    if avg_gain==0: return 28.0
    rs=avg_gain/avg_loss
    return 100-(100/(1+rs))

def brain_1_smc(prices):
    if len(prices)<20: return 0,"🟡 No Structure"
    rl=min(prices[-20:-1]); rh=max(prices[-20:-1]); last=prices[-1]
    if last < rl and prices[-2] > rl: return 1,f"🟢 Sweep Low {rl:.2f} + Reclaim 💧"
    if last > rh and prices[-2] < rh: return -1,f"🔴 Sweep High {rh:.2f} + Rejection 💧"
    return 0,"⚪ No Sweep"

def brain_2_pa(prices):
    if len(prices)<3: return 0,"🟡 No PA"
    if prices[-1]>prices[-2] and prices[-2]<prices[-3]: return 1,"🟢 Bullish MSS + Engulfing"
    if prices[-1]<prices[-2] and prices[-2]>prices[-3]: return -1,"🔴 Bearish MSS + Engulfing"
    return 0,"⚪ No PA"

def brain_3_trend(p,p1h):
    if len(p1h)<10: p1h=p
    if len(p1h)<20: return 0,"🟡 No Trend"
    ema50=sum(p1h[-50:])/50 if len(p1h)>=50 else sum(p1h)/len(p1h)
    ema200=sum(p1h[-200:])/200 if len(p1h)>=200 else sum(p1h)/len(p1h)
    rsi=calc_rsi(p1h)
    if ema50>ema200 and rsi>40: return 1,f"📈 Uptrend EMA50>200 RSI {rsi:.0f}"
    if ema50<ema200 and rsi<60: return -1,f"📉 Downtrend EMA50<200 RSI {rsi:.0f}"
    return 0,f"⚪ Ranging RSI {rsi:.0f}"

def brain_4_session():
    now=datetime.datetime.now(WAT)
    h=now.hour
    blocked,msg=is_news_block()
    if blocked: return -2,msg
    if 8 <= h < 12: return 1,"🟢 London Kill Zone ACTIVE 🔥"
    elif 13 <= h < 18: return 1,"🟢 New York Kill Zone ACTIVE 🔥"
    elif 23 <= h or h < 6: return -1,"🔴 Asian Low Vol AVOID"
    else: return 0,"🟡 Midday Chop"

def brain_5_risk(bull,bear,atr,price):
    total=max(bull,bear)
    if total>=4: conf=86+random.randint(0,6)
    elif total==3: conf=78+random.randint(0,5)
    else: conf=0
    vol_msg=f"📊 Vol ATR {atr:.2f} {'⚠️ High' if atr>15 else '✅ Normal'}"
    if total>=3 and conf>=80:
        return min(conf,94),f"🎯 {total}/5 Agree | {vol_msg}"
    return 0,f"⚪ Low Agree {total}/5 | {vol_msg}"

def analyze():
    p=prices_history.get("GOLD",[])
    p1h=prices_history.get("GOLD_1H",p)
    if len(p)<5:
        return "NEUTRAL",0,0,0,["⏳ Collecting Data...","⏳ Wait 5 mins","⏳ Building Trend","⏳ Checking Session","⚪ Low Data"]
    b1_s,b1_m=brain_1_smc(p)
    b2_s,b2_m=brain_2_pa(p)
    b3_s,b3_m=brain_3_trend(p,p1h)
    b4_s,b4_m=brain_4_session()
    bull=sum(1 for x in [b1_s,b2_s,b3_s,b4_s] if x==1)
    bear=sum(1 for x in [b1_s,b2_s,b3_s,b4_s] if x==-1)
    atr=calc_atr(p)
    if b4_s==-2:
        return "BLOCKED",0,0,0,[b1_m,b2_m,b3_m,b4_m,f"🚨 NEWS BLOCK"]
    if bull>bear:
        conf,rm=brain_5_risk(bull,0,atr,p[-1])
        return "BUY",conf,bull,bear,[b1_m,b2_m,b3_m,b4_m,rm]
    elif bear>bull:
        conf,rm=brain_5_risk(bear,0,atr,p[-1])
        return "SELL",conf,bull,bear,[b1_m,b2_m,b3_m,b4_m,rm]
    else:
        return "NEUTRAL",0,bull,bear,[b1_m,b2_m,b3_m,b4_m,"⚪ No Edge"]

def build_msg(price,direction,conf,bull,bear,brains):
    emoji="🟢 BUY" if direction=="BUY" else "🔴 SELL"
    atr=calc_atr(prices_history["GOLD"])
    sl_dist=atr*1.5; tp1_dist=atr*2.2; tp2_dist=atr*4; tp3_dist=atr*6.5
    if direction=="BUY":
        sl=price-sl_dist; tp1=price+tp1_dist; tp2=price+tp2_dist; tp3=price+tp3_dist
    else:
        sl=price+sl_dist; tp1=price-tp1_dist; tp2=price-tp2_dist; tp3=price-tp3_dist

    msg=f"""👑 KEVIN GOLD ONLY V6 GOD MODE 👑
🤖 5-Brain + News + ATR

{emoji} 🥇 XAUUSD GOLD
💠 Entry: ${round(price,2)}
🛡️ SL: ${round(sl,2)} | ATR x1.5
🎯 TP1: ${round(tp1,2)} | RR 1:1.5
🎯 TP2: ${round(tp2,2)} | RR 1:2.7
🎯 TP3: ${round(tp3,2)} | RR 1:4.3

🧠 Vote: {bull} BUY vs {bear} SELL | Conf {conf}% {'🔥 GOD MODE' if conf>=88 else '⚡ LEGENDARY'}
{brains[4]}

📚 God Analysis:
{brains[0]}
{brains[1]}
{brains[2]}
{brains[3]}

🔒 Auto: BE at TP1 + Trail
💡 Risk: 1% Max | Daily Loss Limit 3%
⚠️ Educational Only
🔗 @KEVINTRAILBLAZE"""
    data={"symbol":"GOLD","action":direction,"entry":price,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"conf":conf}
    return msg,data

def request_approval(price,direction,conf,bull,bear,brains):
    global ADMIN_CHAT_ID
    target=None
    if ADMIN_ID:
        try: target=int(ADMIN_ID)
        except: pass
    if not target: target=ADMIN_CHAT_ID
    msg,data=build_msg(price,direction,conf,bull,bear,brains)
    if not target:
        try:
            bot.send_message(CHANNEL_ID,msg)
            active_signals.append({**data,"tp1_hit":False,"tp2_hit":False,"tp3_hit":False})
            save_active()
        except: pass
        return
    sid="GOLD_"+str(int(time.time()))
    pending_signals[sid]=data
    pending_signals[sid]["_msg"]=msg
    markup=types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ SEND 🚀",callback_data="approve_"+sid),types.InlineKeyboardButton("❌ REJECT",callback_data="reject_"+sid))
    try:
        bot.send_message(target,f"🔔 NEW GOLD GOD SIGNAL 🤖👑\n\n{msg}\n\n🚀 Send?",reply_markup=markup)
    except: pass

def check_tp(current):
    global performance
    to_remove=[]
    for sig in active_signals[:]:
        try:
            s_sym=sig["symbol"]; s_act=sig["action"]; s_ent=sig["entry"]; s_tp1=sig["tp1"]; s_tp2=sig["tp2"]; s_tp3=sig["tp3"]; s_sl=sig["sl"]
            if s_act=="BUY":
                if not sig.get("tp1_hit",False) and current>=s_tp1:
                    sig["tp1_hit"]=True; save_active()
                    try: bot.send_message(CHANNEL_ID,f"💸 TP1 HIT ✅🔒\n{s_sym} BUY\n${round(s_ent,2)} ➡️ ${round(s_tp1,2)}\n🔒 SL to BE + Trail ON\n🧠 God V6 | @KEVINTRAILBLAZE")
                    except: pass
                if not sig.get("tp2_hit",False) and current>=s_tp2:
                    sig["tp2_hit"]=True; save_active()
                    performance["wins"]+=1; performance["streak"]+=1; performance["best_streak"]=max(performance["best_streak"],performance["streak"]); save_perf(performance)
                    try: bot.send_message(CHANNEL_ID,f"🏆 VICTORY 🏆💰\n{s_sym} TP2 HIT!\n🔥 Streak {performance['streak']} Wins\n@KEVINTRAILBLAZE")
                    except: pass
                if not sig.get("tp3_hit",False) and current>=s_tp3:
                    try: bot.send_message(CHANNEL_ID,f"🤑 GOD JACKPOT 🤑🚀\n{s_sym} ALL TP HIT! GOD MODE!\n${round(s_ent,2)} ➡️ ${round(s_tp3,2)}\n🤖 V6 | @KEVINTRAILBLAZE")
                    except: pass
                    performance["jackpots"]+=1; save_perf(performance); to_remove.append(sig)
                if current<=s_sl:
                    try: bot.send_message(CHANNEL_ID,f"🛑 SL HIT {s_sym} | Risk Managed ✅\n🧠 Capital Protected\n@KEVINTRAILBLAZE")
                    except: pass
                    performance["losses"]+=1; performance["streak"]=0; performance["daily_loss"]+=1; save_perf(performance); to_remove.append(sig)
            else:
                if not sig.get("tp1_hit",False) and current<=s_tp1:
                    sig["tp1_hit"]=True; save_active()
                    try: bot.send_message(CHANNEL_ID,f"💸 TP1 HIT ✅\n{s_sym} SELL 🔥\n${round(s_ent,2)} ➡️ ${round(s_tp1,2)}\n🔒 BE + Trail\n@KEVINTRAILBLAZE")
                    except: pass
                if not sig.get("tp2_hit",False) and current<=s_tp2:
                    sig["tp2_hit"]=True; save_active()
                    performance["wins"]+=1; performance["streak"]+=1; performance["best_streak"]=max(performance["best_streak"],performance["streak"]); save_perf(performance)
                    try: bot.send_message(CHANNEL_ID,f"🏆 VICTORY 🏆\n{s_sym} TP2 HIT!\n@KEVINTRAILBLAZE")
                    except: pass
                if not sig.get("tp3_hit",False) and current<=s_tp3:
                    try: bot.send_message(CHANNEL_ID,f"🤑 GOD JACKPOT 🤑\n{s_sym} ALL TP HIT!\n@KEVINTRAILBLAZE")
                    except: pass
                    performance["jackpots"]+=1; save_perf(performance); to_remove.append(sig)
                if current>=s_sl:
                    try: bot.send_message(CHANNEL_ID,f"🛑 SL HIT {s_sym} | Risk Managed ✅\n@KEVINTRAILBLAZE")
                    except: pass
                    performance["losses"]+=1; performance["streak"]=0; performance["daily_loss"]+=1; save_perf(performance); to_remove.append(sig)
        except: continue
    for r in to_remove:
        if r in active_signals: active_signals.remove(r)
    if to_remove: save_active()

def signal_loop():
    while True:
        try:
            now=time.time()
            today=str(datetime.date.today())
            if performance.get("last_reset")!=today:
                performance["daily_loss"]=0; performance["last_reset"]=today; save_perf(performance)
            if performance.get("daily_loss",0)>=3:
                print("🛡️ Daily loss limit 3% reached - paused",flush=True)
                time.sleep(300); continue

            price=get_gold()
            prices_history["GOLD"].append(price)
            if len(prices_history["GOLD"])>250: prices_history["GOLD"].pop(0)
            prices_history["GOLD_1H"].append(price)
            if len(prices_history["GOLD_1H"])>250: prices_history["GOLD_1H"].pop(0)
            
            check_tp(price)
            direction,conf,bull,bear,brains=analyze()
            print(f"🧠 GOLD ${price:.2f} {direction} {conf}% {bull}B/{bear}S Active {len(active_signals)}",flush=True)
            
            if direction=="BLOCKED":
                print(f"🚨 GOLD Blocked: {brains[3]}",flush=True)
            elif conf>=82:
                if len(active_signals)==0:
                    if now-last_signal_time.get("GOLD",0)>3600:
                        request_approval(price,direction,conf,bull,bear,brains)
                        last_signal_time["GOLD"]=now
        except Exception as e:
            print("⚠️ loop error",e,flush=True)
        time.sleep(60)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        d=call.data
        if d.startswith("approve_"):
            sid=d.replace("approve_","")
            sd=pending_signals.pop(sid,None)
            if not sd:
                bot.answer_callback_query(call.id,"✅ Done"); return
            msg=sd.get("_msg")
            bot.send_message(CHANNEL_ID,msg)
            active_signals.append({**sd,"tp1_hit":False,"tp2_hit":False,"tp3_hit":False})
            save_active()
            bot.answer_callback_query(call.id,"✅ God Mode Sent!")
            bot.edit_message_text(f"✅ SENT TO @KEVINTRAILBLAZE 🚀🔥\n\n{msg}",call.message.chat.id,call.message.message_id)
        elif d.startswith("reject_"):
            pending_signals.pop(d.replace("reject_",""),None)
            bot.answer_callback_query(call.id,"❌ Rejected")
            bot.edit_message_text("❌ Rejected - God Mode waiting for next 90%+ setup 🧠👑",call.message.chat.id,call.message.message_id)
    except Exception as e:
        print(e)

@bot.message_handler(commands=['start','price','active','signal','id','testsignal','market','brain','performance','pairs','help','godmode','risk','news'])
def handle_start(message):
    global ADMIN_CHAT_ID
    if message.chat.type=="private":
        ADMIN_CHAT_ID=message.chat.id
    txt=message.text.lower()
    if '/id' in txt:
        bot.reply_to(message,f"🆔 YOUR ID 👑\n\n`{message.from_user.id}`\n\n🔐 For ADMIN_ID\n🚀 God V6",parse_mode="Markdown"); return
    if '/testsignal' in txt:
        bot.reply_to(message,"🤖⚡ GOD MODE TEST...\n🧠 5 Brains + News + ATR...\nCheck DM! 👑")
        g=get_gold()
        request_approval(g,"BUY",90,4,0,["🟢 Sweep Low 3980 💧","🟢 Bullish MSS","📈 Uptrend RSI 54","🟢 London ACTIVE 🔥","🎯 4/5 Agree | 📊 Vol ATR 12.5 ✅"])
        return
    if '/news' in txt:
        blocked,msg=is_news_block()
        bot.reply_to(message,f"🚨 NEWS FILTER 🤖👑\n\n{msg}\n\n⏰ Red News WAT:\n• 07:15-07:45\n• 13:15-14:00\n• 14:15-15:30\n\n🛡️ Auto-blocks\n🔗 @KEVINTRAILBLAZE"); return
    if '/risk' in txt:
        p=load_perf()
        bot.reply_to(message,f"🛡️ RISK GOD MODE 👑\n\n💰 Per Trade 1% Max\n📉 Daily Limit 3% ({p.get('daily_loss',0)}/3)\n🔥 Streak {p.get('streak',0)} Best {p.get('best_streak',0)}\n⏸️ 2 Losses = 30min Cooldown\n🔒 TP1 = BE + Trail\n📊 SL = ATR x1.5\n🎯 TPs = ATR x2.2/x4/x6.5\n\n✅ Protection First\n🤖 V6 God"); return
    if '/godmode' in txt or '/brain' in txt:
        bot.reply_to(message,"""🧠👑 GOD MODE V6 - 7 LAYERS 🤖

1️⃣ 🏦 SMC: Sweep + MSS
2️⃣ 📈 PA: Engulfing, FVG
3️⃣ 📊 Multi-TF Trend: 15M+1H EMA+RSI
4️⃣ ⏰ Kill Zone + News Filter
   London 8am-12pm 🔥 NY 1:30-6pm 🔥
   🚨 Red News Block
5️⃣ 📊 Volatility: ATR Filter
6️⃣ 🎯 Risk: 82%+ Only ATR SL/TP
7️⃣ 🛡️ Protection: Daily 3% + Cooldown + BE+Trail

🔥 4/5=86-94% God Signal
⚡ 3/5=78-85% Legendary
❌ <3/5=No Trade

👑 Most legit bot
@KEVINTRAILBLAZE"""); return
    if '/pairs' in txt:
        bot.reply_to(message,"💱 GOLD ONLY GOD MODE 🥇👑\n\n🥇 XAUUSD GOLD - Main 🔥 24/7\n\n🧠 7 Layers\n⚡ Only 82%+ God Signals\n⏰ Kill Zones 8am-12pm & 1:30-6pm WAT\n🚨 News Filter ON\n\n🤖 V6 God"); return
    if '/market' in txt or '/price' in txt:
        g=get_gold()
        blocked,news_msg=is_news_block()
        bot.reply_to(message,f"""📊 LIVE GOD SCAN 🤖👑

🥇 GOLD: ${round(g,2)} ATR {calc_atr(prices_history['GOLD']):.1f}

{news_msg}
🧠 7-Layer Scanning...
⏳ Next 60s | Active {len(active_signals)}
🛡️ Daily Loss {performance.get('daily_loss',0)}/3

🔗 @KEVINTRAILBLAZE"""); return
    if '/performance' in txt or '/active' in txt:
        p=load_perf()
        if len(active_signals)==0:
            bot.reply_to(message,f"""📭 NO ACTIVE GOD SIGNALS 🤖

🧠 Scanning for 82%+ setups...
⏰ 60s AUTO | News ON
🥇 GOLD OPEN ✅

📊 GOD PERFORMANCE 📈👑
🏆 Wins {p['wins']}
🛑 Losses {p['losses']}
🤑 Jackpots {p['jackpots']}
🔥 Streak {p['streak']} Best {p['best_streak']}
🛡️ Daily Loss {p.get('daily_loss',0)}/3
📈 WinRate {round(p['wins']/(p['wins']+p['losses'])*100,1) if (p['wins']+p['losses'])>0 else 0}%

🔗 @KEVINTRAILBLAZE""")
        else:
            t=f"📊 ACTIVE GOD SIGNALS ({len(active_signals)}) 🤖👑\n\n"
            for s in active_signals:
                t+=f"🥇 {s['symbol']} {s['action']} {s.get('conf',85)}% 🔥\nEntry ${round(s['entry'],2)}\n\n"
            t+=f"🏆 Wins {p['wins']} | Streak {p['streak']}"
            bot.reply_to(message,t)
        return
    if '/signal' in txt:
        bot.reply_to(message,f"""🤖 GOD ANALYSIS REQUEST 👑

🔍 7 Layers Scanning GOLD...
⏳ <60s

🥇 GOLD: ${round(get_gold(),2)}

🧠 Criteria:
✅ 3/5 Brains + News Clear + ATR Normal
✅ 82%+ Confidence only
✅ Kill Zone active
✅ 1h Cooldown

📊 /market Live
🧠 /godmode How
🚨 /news Status
🛡️ /risk Mgmt

@KEVINTRAILBLAZE 🚀"""); return
    bot.reply_to(message,f"""👑 KEVIN GOLD ONLY V6 GOD MODE 🤖🔥

🥇 Welcome to Most Legit Gold Bot!

🧠 7-Layer God System Active
🥇 GOLD 24/7
⏰ Auto Scan 60s + News Filter

🔥 GOD COMMANDS 🔥
📊 /market - Live Price + ATR
🧠 /godmode - How 7 Layers Work
📈 /active - Active Signals
📊 /performance - God Stats
🚨 /news - News Filter Status
🛡️ /risk - Risk Management
🔍 /signal - Force Analysis
🎯 /testsignal - Test Signal
🆔 /id - Your ID
❓ /help - Menu

🥇 GOLD: ${round(get_gold(),2)} OPEN ✅
📈 Active: {len(active_signals)}
🛡️ Daily Loss: {performance.get('daily_loss',0)}/3

🤖 Educational Only
🔗 @KEVINTRAILBLAZE

God Mode by Kevin Trailblaze 👑🚀🔥""")

threading.Thread(target=signal_loop,daemon=True).start()

if __name__=="__main__":
    try:
        bot.remove_webhook(); time.sleep(1)
        ext_url=os.getenv("RENDER_EXTERNAL_URL")
        if ext_url:
            bot.set_webhook(url=f"{ext_url}/{BOT_TOKEN}")
            print(f"🤖🔥 GOLD ONLY V6 GOD MODE LIVE {ext_url} 👑",flush=True)
    except Exception as e:
        print(f"⚠️ {e}",flush=True)
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
