import os
import logging
from dotenv import load_dotenv
from uuid import uuid4
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ParseMode,
)
from telegram.ext import (
    Updater,
    MessageHandler,
    CallbackQueryHandler,
    Filters,
    CallbackContext,
)

# --- 1. TOKEN yuklash ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- 2. Logging ---
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 3. Ma'lumotlar ---
POLLS = {}
USER_STATE = {}


# --- 4. Poll klassi ---
class Poll:
    def __init__(self, creator_id, chat_id, question, options, is_quiz=False, correct_index=-1):
        self.id = str(uuid4())
        self.creator_id = creator_id
        self.chat_id = chat_id
        self.question = question
        self.options = options
        self.votes = {i: 0 for i in range(len(options))}
        self.voters = {}
        self.is_quiz = is_quiz
        self.correct_index = correct_index
        self.is_closed = False
        self.message_id = None

    def get_text(self):
        total = sum(self.votes.values()) or 1
        text = f"*{self.question}*\n\n"
        for i, opt in enumerate(self.options):
            percent = (self.votes[i] / total) * 100
            text += f"{opt} — {self.votes[i]} ovoz ({percent:.1f}%)\n"
        return text

    def get_keyboard(self):
        if self.is_closed:
            return None
        buttons = [[InlineKeyboardButton(opt, callback_data=f"vote_{self.id}_{i}")]
                   for i, opt in enumerate(self.options)]
        return InlineKeyboardMarkup(buttons)


# --- 5. Asosiy keyboard ---
def main_menu():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🗳 So‘rov yaratish"), KeyboardButton("🧠 Kviz yaratish")],
            [KeyboardButton("📋 So‘rovlarni boshqarish"), KeyboardButton("❌ Bekor qilish")],
        ],
        resize_keyboard=True
    )


# --- 6. Start ---
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "👋 Salom! Quyidagi tugmalardan birini tanlang 👇",
        reply_markup=main_menu()
    )


# --- 7. So‘rov yaratish ---
def create_poll(update: Update, context: CallbackContext):
    USER_STATE[update.effective_user.id] = "poll"
    update.message.reply_text(
        "🗳 So‘rovnoma yaratish uchun yozing:\n\n"
        "Savol\nVariant 1\nVariant 2\nVariant 3\n...",
        reply_markup=main_menu()
    )


# --- 8. Kviz yaratish ---
def create_quiz(update: Update, context: CallbackContext):
    USER_STATE[update.effective_user.id] = "quiz"
    update.message.reply_text(
        "🧠 Kviz yaratish uchun yozing:\n\n"
        "Savol\nTo‘g‘ri javob\nVariant 2\nVariant 3\n...",
        reply_markup=main_menu()
    )


# --- 9. Bekor qilish ---
def cancel(update: Update, context: CallbackContext):
    USER_STATE.pop(update.effective_user.id, None)
    updat
