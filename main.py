import os, telebot, time
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 8659453018

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

print(f"BOT_TOKEN exists: {bool(BOT_TOKEN)}")
print(f"OWNER_ID: {OWNER_ID}")

@bot.message_handler(commands=['start','balance','mode','results','test'])
def hello(m):
    print(f"Got message from {m.from_user.id} : {m.text}")
    # Reply to EVERYONE for test
    bot.send_message(m.chat.id, f"✅ BOT WORKING! Your ID is {m.from_user.id}\nYou typed: {m.text}\nOWNER_ID set to {OWNER_ID}")

@bot.message_handler(func=lambda m: True)
def echo(m):
    print(f"Echo from {m.from_user.id}: {m.text}")
    bot.send_message(m.chat.id, f"Echo: {m.text} | Your ID: {m.from_user.id}")

if __name__ == "__main__":
    try:
        bot.remove_webhook()
        time.sleep(1)
        print("Webhook deleted, starting polling TEST BOT")
    except Exception as e:
        print(f"remove webhook error {e}")
    bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=True)
