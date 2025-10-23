import os
import logging
from dotenv import load_dotenv
from uuid import uuid4
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    Filters,
    CallbackContext,
)

# .env fayldan token olish
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Logger sozlamasi
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Ma'lumotlar bazasi sifatida oddiy dict ishlatiladi
POLLS = {}
USER_STATE = {}

# Poll obyekt klassi
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


# /start
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "👋 Assalomu alaykum!\n\n"
        "Quyidagi buyruqlardan foydalaning:\n"
        "/create_poll — oddiy so‘rovnoma yaratish\n"
        "/create_quiz — kviz (to‘g‘ri javob bilan)\n"
        "/manage_polls — so‘rovlarni boshqarish\n"
        "/cancel — bekor qilish"
    )


# /create_poll
def create_poll(update: Update, context: CallbackContext):
    USER_STATE[update.effective_user.id] = "poll"
    update.message.reply_text(
        "🗳 So‘rovnoma yaratish uchun quyidagicha yozing:\n\n"
        "Savol\nVariant 1\nVariant 2\nVariant 3\n..."
    )


# /create_quiz
def create_quiz(update: Update, context: CallbackContext):
    USER_STATE[update.effective_user.id] = "quiz"
    update.message.reply_text(
        "🧠 Kviz yaratish uchun quyidagicha yozing:\n\n"
        "Savol\nTo‘g‘ri javob\nVariant 2\nVariant 3\n..."
    )


# /cancel
def cancel(update: Update, context: CallbackContext):
    USER_STATE.pop(update.effective_user.id, None)
    update.message.reply_text("❌ Amal bekor qilindi.")


# /manage_polls
def manage_polls(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user_polls = [p for p in POLLS.values() if p.creator_id == user_id]

    if not user_polls:
        update.message.reply_text("Sizda yaratilgan so‘rovnoma yo‘q.")
        return

    buttons = [
        [InlineKeyboardButton(p.question[:30], callback_data=f"manage_{p.id}")]
        for p in user_polls
    ]
    update.message.reply_text("📋 Sizning so‘rovnomalaringiz:", reply_markup=InlineKeyboardMarkup(buttons))


# Poll yoki quiz yaratish
def handle_text(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in USER_STATE:
        return

    lines = update.message.text.strip().split("\n")
    if len(lines) < 3:
        update.message.reply_text("Iltimos, kamida 1 savol va 2 ta variant kiriting.")
        return

    mode = USER_STATE[user_id]
    question = lines[0]
    options = lines[1:]
    is_quiz = (mode == "quiz")
    correct = 0 if is_quiz else -1

    poll = Poll(user_id, update.effective_chat.id, question, options, is_quiz, correct)
    POLLS[poll.id] = poll

    msg = update.message.reply_text(
        poll.get_text(),
        reply_markup=poll.get_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    poll.message_id = msg.message_id
    USER_STATE.pop(user_id, None)


# Ovoz berish
def vote(update: Update, context: CallbackContext):
    query = update.callback_query
    _, poll_id, opt_index = query.data.split("_")
    opt_index = int(opt_index)
    user_id = query.from_user.id

    poll = POLLS.get(poll_id)
    if not poll or poll.is_closed:
        query.answer("Bu so‘rov yopilgan yoki topilmadi.")
        return

    old_vote = poll.voters.get(user_id)
    if old_vote is not None:
        poll.votes[old_vote] -= 1
    poll.voters[user_id] = opt_index
    poll.votes[opt_index] += 1

    query.answer("✅ Ovozingiz qabul qilindi.")
    query.edit_message_text(
        poll.get_text(),
        reply_markup=poll.get_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )


# Poll boshqaruvi
def manage_action(update: Update, context: CallbackContext):
    query = update.callback_query
    _, poll_id = query.data.split("_")
    poll = POLLS.get(poll_id)

    if not poll:
        query.answer("So‘rov topilmadi.")
        return

    buttons = [
        [InlineKeyboardButton("❌ O‘chirish", callback_data=f"delete_{poll_id}")],
        [InlineKeyboardButton("📊 Natijani ko‘rish", callback_data=f"result_{poll_id}")],
        [InlineKeyboardButton("🔒 Yopish", callback_data=f"close_{poll_id}")],
    ]
    query.edit_message_text(
        f"🗳 {poll.question}\n\nBoshqaruv menyusi:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


def manage_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    action, poll_id = query.data.split("_")
    poll = POLLS.get(poll_id)

    if not poll:
        query.answer("Topilmadi.")
        return

    if action == "delete":
        del POLLS[poll_id]
        query.edit_message_text("🗑 So‘rov o‘chirildi.")
    elif action == "result":
        query.edit_message_text(poll.get_text(), parse_mode=ParseMode.MARKDOWN)
    elif action == "close":
        poll.is_closed = True
        query.edit_message_text("🔒 So‘rov yopildi.")


# Botni ishga tushurish
def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN topilmadi! .env faylni tekshiring.")
        return

    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("create_poll", create_poll))
    dp.add_handler(CommandHandler("create_quiz", create_quiz))
    dp.add_handler(CommandHandler("cancel", cancel))
    dp.add_handler(CommandHandler("manage_polls", manage_polls))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
    dp.add_handler(CallbackQueryHandler(vote, pattern=r"^vote_"))
    dp.add_handler(CallbackQueryHandler(manage_action, pattern=r"^manage_"))
    dp.add_handler(CallbackQueryHandler(manage_callback, pattern=r"^(delete|result|close)_"))

    print("🤖 Bot started...")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
