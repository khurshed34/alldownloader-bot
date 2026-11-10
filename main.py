
import os
import re
import telebot
import yt_dlp

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN is missing")

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(
        message,
        "👋 Салом! Хуш омадед ба TurboSave!\n\n"
        "🔗 Ссылкаи видео ё аксро фиристед.\n"
        "📥 Ман манбаъҳои дастгиришавандаро месанҷам."
    )

@bot.message_handler(func=lambda m: bool(m.text))
def receive_link(message):
    url = message.text.strip()

    if not re.match(r"^https?://", url):
        bot.reply_to(message, "❌ Лутфан ссылкаи дуруст фиристед.")
        return

    bot.reply_to(
        message,
        "🔎 Ссылка қабул шуд!\n\n"
        "Платформаро месанҷем...\n"
        "Ин манбаъ бояд барои зеркашӣ дастгирӣ шавад."
    )

print("TurboSave bot started...")
bot.infinity_polling(skip_pending=True)
