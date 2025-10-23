import os
import telebot
from telebot import types
from dotenv import load_dotenv

# .env fayldan TOKEN olish
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

bot = telebot.TeleBot(TOKEN)

# Foydalanuvchi holatini saqlash
user_state = {}

# Start buyrug‘i
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("📝 So‘rov yaratish")
    btn2 = types.KeyboardButton("❓ Kviz yaratish")
    markup.add(btn1, btn2)
    bot.send_message(
        message.chat.id,
        "Salom! 😊 Quyidagi tugmalardan birini tanlang:",
        reply_markup=markup
    )

# Tugmalarni ushlash
@bot.message_handler(func=lambda msg: msg.text in ["📝 So‘rov yaratish", "❓ Kviz yaratish"])
def poll_type(message):
    is_quiz = message.text == "❓ Kviz yaratish"
    user_state[message.chat.id] = {"is_quiz": is_quiz}
    example = (
        r"Kviz uchun misol:\nFransiyaning poytaxti qayer?\nParij\nLondon\nBerlin"
        if is_quiz
        else r"So‘rov uchun misol:\nSevimli mevangiz?\nOlma\nBanan\nApelsin"
    )
    bot.send_message(
        message.chat.id,
        f"Iltimos, savol va javob variantlarini yuboring.\n\n{example}\n\n"
        "Har bir javob yangi qatorda bo‘lishi kerak.",
    )

# Foydalanuvchi javobini olish
@bot.message_handler(func=lambda msg: msg.chat.id in user_state)
def create_poll(message):
    data = user_state.pop(message.chat.id)
    lines = message.text.strip().split("\n")

    if len(lines) < 3:
        bot.send_message(message.chat.id, "Kamida 1 ta savol va 2 ta variant kiriting.")
        return

    question = lines[0]
    options = lines[1:]
    is_quiz = data["is_quiz"]

    # Kviz bo‘lsa, birinchi variant to‘g‘ri deb belgilanadi
    correct_option = 0 if is_quiz else None

    poll_msg = bot.send_poll(
        message.chat.id,
        question=question,
        options=options,
        type="quiz" if is_quiz else "regular",
        correct_option_id=correct_option,
        allows_multiple_answers=False,
        is_anonymous=True,
    )

    bot.send_message(
        message.chat.id,
        "✅ So‘rov yaratildi! Agar istasangiz, ko‘p tanlovni yoqish/o‘chirish mumkin.",
        reply_markup=generate_poll_controls(poll_msg.poll.id),
    )

# Inline tugmalar yaratish
def generate_poll_controls(poll_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🔁 Ko‘p tanlovni yoqish/o‘chirish", callback_data=f"toggle_{poll_id}")
    )
    return markup

# Callback funksiyasi
@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_"))
def toggle_multi_choice(call):
    poll_id = call.data.split("_")[1]

    # Bu yerda haqiqiy API bilan ishlash o‘rniga shunchaki xabar yuboriladi
    bot.answer_callback_query(
        call.id,
        text="Ko‘p tanlov holati o‘zgartirildi ✅"
    )
    bot.send_message(
        call.message.chat.id,
        "Ko‘p tanlov funksiyasi o‘rnatildi (bu demo rejimda)."
    )

# Xatoliklarni ushlash
@bot.message_handler(func=lambda msg: True)
def fallback(message):
    bot.send_message(message.chat.id, "Iltimos, /start buyrug‘ini boshing yoki menyudan tanlang.")

print("🤖 Bot ishga tushdi...")
bot.infinity_polling()
