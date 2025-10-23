import logging
import csv
import os
from io import StringIO
from uuid import uuid4
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    Filters,
    CallbackContext,
)

# --- Konfiguratsiya va Sozlash ---

# .env faylini yuklash
load_dotenv()
# TOKENni .env faylidan olish
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Mock Database (In-Memory Storage) ---
# Eslatma: Ushbu lug'atlar bot o'chirilganda ma'lumotlarni yo'qotadi.
# Doimiy saqlash uchun Firestore kabi DB dan foydalaning.
POLLS = {}
USER_STATE = {}
TEMP_POLLS = {}

class Poll:
    """Represents a Poll or Quiz object with advanced features."""
    def __init__(self, creator_id: int, chat_id: int, question: str, options: list, is_quiz: bool = False, correct_answer_index: int = -1):
        self.poll_id = str(uuid4())
        self.creator_id = creator_id
        self.chat_id = chat_id
        self.question = question
        self.options = options
        self.is_quiz = is_quiz
        self.is_closed = False
        self.is_multi_choice = False 
        self.is_anonymous_results = False 
        
        self.correct_answer_index = correct_answer_index
        # Ovozlar: {variant_index: ovoz_soni}
        self.votes = {i: 0 for i in range(len(options))}
        # Ovoz beruvchilar: {user_id: [tanlangan_variant_indekslari]}
        self.voters = {}
        self.message_id = None

    def get_results_summary(self, user_id: int = None) -> str:
        """Generates the formatted results string for the poll message."""
        total_voters_count = len(self.voters)
        total_vote_selections = sum(self.votes.values())
        
        status_parts = []
        if self.is_closed:
            status_parts.append("*[ SO'ROVNOMA YOPIQ ]*")
        if self.is_multi_choice:
            status_parts.append("*(Ko'p tanlov ruxsat etilgan)*")
        if self.is_anonymous_results:
            status_parts.append("*(Natijalar anonim)*")

        status_line = "\n".join(status_parts) + "\n\n" if status_parts else ""
        
        summary = f"{status_line}*{self.question}*\n\n"

        for i, option in enumerate(self.options):
            count = self.votes.get(i, 0)
            percentage = (count / total_vote_selections * 100) if total_vote_selections > 0 else 0
            
            line = f"*{option}* - {count} ovoz ({percentage:.1f}%)"

            if user_id in self.voters and not self.is_anonymous_results:
                is_user_voted = i in self.voters[user_id]
                
                if is_user_voted:
                    line += " *[Sizning tanlovingiz]*"
                
                if self.is_quiz and self.is_closed:
                     is_correct = (i == self.correct_answer_index)
                     if is_correct:
                        line += " ✅ *(To'g'ri javob)*"
                     elif is_user_voted:
                        line += " ❌ *(Noto'g'ri)*"
            
            summary += f"{line}\n"

        if total_voters_count > 0:
            summary += f"\nJami Ishtirokchilar: {total_voters_count}"
        
        return summary
    
    def get_keyboard(self, user_id: int = None) -> InlineKeyboardMarkup | None:
        """Generates the Inline Keyboard for voting."""
        if self.is_closed:
            return None
            
        keyboard = []
        
        for i, option in enumerate(self.options):
            button_text = option
            if self.is_multi_choice and user_id in self.voters and i in self.voters[user_id]:
                button_text = f"✅ {option}"
            
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"vote_{self.poll_id}_{i}")])

        if self.is_multi_choice and user_id in self.voters:
            # Ko'p tanlov uchun ovoz berishni tugatish tugmasi
            keyboard.append([InlineKeyboardButton("🗳️ Ovoz Berish Tayyor / Natijalarni ko'rish", callback_data=f"vote_done_{self.poll_id}")])

        return InlineKeyboardMarkup(keyboard)

# --- Utility Functions ---

def get_config_keyboard(poll_id: str, is_quiz: bool) -> InlineKeyboardMarkup:
    """Generates the configuration keyboard for a newly created poll/quiz."""
    poll = TEMP_POLLS[poll_id]
    
    multi_choice_text = "✅ Ko'p tanlov" if poll.is_multi_choice else "❌ Yagona tanlov"
    anonymous_text = "✅ Anonim Natijalar" if poll.is_anonymous_results else "❌ Ochiq Natijalar"
    
    keyboard = []
    if not is_quiz:
        # Kvizlar uchun ko'p tanlovni o'chiramiz
        keyboard.append([InlineKeyboardButton(multi_choice_text, callback_data=f"config_multi_{poll_id}")])
    
    keyboard.append([InlineKeyboardButton(anonymous_text, callback_data=f"config_anon_{poll_id}")])
    keyboard.append([InlineKeyboardButton("🚀 So'rovnomani Nashr Qilish!", callback_data=f"config_publish_{poll_id}")])
    
    return InlineKeyboardMarkup([row for row in keyboard if row])

def generate_export_csv(poll: Poll) -> str:
    """Generates a simple text/CSV representation of the results."""
    output = StringIO()
    writer = csv.writer(output, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    
    # 1. Umumiy Natijalar Sarlavhasi
    header = ["Tanlov", "Ovozlar", "Foiz"]
    if poll.is_quiz:
        header.append("To'g'ri javob")
    writer.writerow(header)
    
    total_vote_selections = sum(poll.votes.values())
    
    # 2. Variant Natijalari
    for i, option in enumerate(poll.options):
        count = poll.votes.get(i, 0)
        percentage = (count / total_vote_selections * 100) if total_vote_selections > 0 else 0
        
        row = [option, count, f"{percentage:.1f}%"]
        if poll.is_quiz:
            row.append("Ha" if i == poll.correct_answer_index else "Yo'q")
        writer.writerow(row)
    
    # 3. Agar anonim bo'lmasa, batafsil ovoz beruvchi ma'lumotlari
    if not poll.is_anonymous_results:
        writer.writerow([])
        writer.writerow(["--- Batafsil Ovoz Beruvchi Ma'lumotlari ---"])
        writer.writerow(["Foydalanuvchi ID", "Tanlangan variant(lar)"])
        
        for user_id, choices in poll.voters.items():
            choice_names = ", ".join([poll.options[index] for index in choices])
            writer.writerow([user_id, choice_names])

    return output.getvalue()

# --- Command Handlers ---

def start(update: Update, context: CallbackContext) -> None:
    """Sends a welcome message and explains the commands."""
    help_message = (
        "*Hammasi Birida So'rovnoma & Kviz Botiga Xush Kelibsiz!* 🗳️🧠\n\n"
        "Siz foydalanishingiz mumkin bo'lgan buyruqlar:\n"
        "1.  `/create_poll` - Oddiy so'rovnoma yaratishni boshlash.\n"
        "2.  `/create_quiz` - To'g'ri javobli kviz yaratishni boshlash.\n"
        "3.  `/manage_polls` - O'zingizning faol so'rovnomangizni boshqarish (Yopish/Eksport qilish).\n"
        "4.  `/cancel` - Joriy yaratish jarayonini to'xtatish.\n\n"
        "Ularni istalgan guruh yoki shaxsiy chatda ishlating!"
    )
    update.message.reply_text(help_message, parse_mode=ParseMode.MARKDOWN)

def create_prompt(update: Update, context: CallbackContext, is_quiz: bool) -> None:
    """Prompts the user to input the poll/quiz data."""
    user_id = update.effective_user.id
    
    if user_id in USER_STATE:
        update.message.reply_text("Siz allaqachon so'rovnoma yaratmoqdasiz. Iltimos, avval tugating yoki `/cancel` dan foydalaning.")
        return

    USER_STATE[user_id] = 'awaiting_data'
    context.user_data['is_quiz'] = is_quiz

    poll_type = "KVIZ" if is_quiz else "SO'ROVNOMA"
    example_text = (
        "Kviz uchun misol:\nFransiyaning poytaxti qayer?\Parij\nLondon\nBerlin" if is_quiz 
        else "So'rovnoma uchun misol:\nQaysi lazzat yaxshi?\nShokolad\nVannil\nQulupnay"
    )
    
    prompt = (
        f"*{poll_type} Yaratish Rejimi*\n\n"
        "Iltimos, savolni yuboring, keyin esa javob variantlarini, har birini yangi qatordan.\n"
        f"_(Kviz uchun, birinchi variant *albatta* to'g'ri javob bo'lishi kerak.)_\n\n"
        f"{example_text}\n\n"
        "To'xtatish uchun `/cancel` dan foydalaning."
    )
    
    update.message.reply_text(prompt, parse_mode=ParseMode.MARKDOWN)

def create_poll_command(update: Update, context: CallbackContext) -> None:
    """Handler for the /create_poll command."""
    create_prompt(update, context, is_quiz=False)

def create_quiz_command(update: Update, context: CallbackContext) -> None:
    """Handler for the /create_quiz command."""
    create_prompt(update, context, is_quiz=True)

def cancel_command(update: Update, context: CallbackContext) -> None:
    """Allows the user to cancel the current poll/quiz creation process."""
    user_id = update.effective_user.id
    if user_id in USER_STATE:
        if user_id in TEMP_POLLS:
            del TEMP_POLLS[user_id]
            
        del USER_STATE[user_id]
        context.user_data.clear()
        update.message.reply_text("✅ So'rovnoma/Kviz yaratish bekor qilindi.")
    else:
        update.message.reply_text("Siz hozirda yaratish jarayonida emassiz.")

def handle_text_input(update: Update, context: CallbackContext) -> None:
    """Processes the text input for creating the poll/quiz and initiates configuration."""
    user_id = update.effective_user.id
    
    if user_id not in USER_STATE or USER_STATE[user_id] != 'awaiting_data':
        return

    is_quiz = context.user_data.get('is_quiz', False)
    
    try:
        lines = [line.strip() for line in update.message.text.split('\n') if line.strip()]
        
        if len(lines) < 3:
            update.message.reply_text(
                "❌ Xatolik: Siz savol va kamida ikkita variantni taqdim etishingiz kerak. Iltimos, qayta urinib ko'ring yoki `/cancel` dan foydalaning."
            )
            return

        question = lines[0]
        options = lines[1:]
        correct_answer_index = 0 if is_quiz else -1 

        temp_poll = Poll(
            creator_id=user_id,
            chat_id=update.effective_chat.id,
            question=question,
            options=options,
            is_quiz=is_quiz,
            correct_answer_index=correct_answer_index
        )
        
        # Vaqtinchalik so'rovnomani saqlash
        TEMP_POLLS[user_id] = temp_poll
        
        USER_STATE[user_id] = 'awaiting_config'
        
        keyboard = get_config_keyboard(user_id, is_quiz)
        update.message.reply_text(
            "*Konfiguratsiya Bosqichi*\n\n"
            "Iltimos, nashr qilishdan oldin so'rovnoma/kvizingiz uchun opsiyalarni tanlang:",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:
        logger.error(f"Error processing text input: {e}")
        update.message.reply_text("Matn kiritishni qayta ishlashda kutilmagan xatolik yuz berdi. Iltimos, qayta urinib ko'ring yoki `/cancel` dan foydalaning.")

# --- Callback Query Handlers (Configuration) ---

def handle_configuration(update: Update, context: CallbackContext) -> None:
    """Handles the configuration button presses (multi-choice, anonymous, publish)."""
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in USER_STATE or USER_STATE[user_id] != 'awaiting_config':
        query.answer("❌ Bu konfiguratsiya sessiyasi muddati tugagan.", show_alert=True)
        return
        
    _, action, _ = query.data.split('_')
    
    poll = TEMP_POLLS.get(user_id)
    if not poll:
        query.answer("❌ Poll ma'lumotlari topilmadi. Iltimos, /create_poll buyrug'ini qayta sinab ko'ring.", show_alert=True)
        return
    
    is_quiz = poll.is_quiz

    if action == 'multi':
        if not is_quiz:
            poll.is_multi_choice = not poll.is_multi_choice
            query.answer(f"Ko'p tanlov o'rnatildi: {'Yoqilgan' if poll.is_multi_choice else 'O'chirilgan'}")
        else:
            query.answer("Ko'p tanlov kvizlar uchun qo'llab-quvvatlanmaydi.", show_alert=True)

    elif action == 'anon':
        poll.is_anonymous_results = not poll.is_anonymous_results
        query.answer(f"Anonim Natijalar o'rnatildi: {'Yoqilgan' if poll.is_anonymous_results else 'O'chirilgan'}")

    elif action == 'publish':
        poll.poll_id = str(uuid4())
        POLLS[poll.poll_id] = poll
        
        summary = poll.get_results_summary(user_id)
        keyboard = poll.get_keyboard(user_id)
        
        try:
            sent_message = context.bot.send_message(
                chat_id=poll.chat_id,
                text=summary,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )

            poll.message_id = sent_message.message_id
            
            # Vaqtinchalik ma'lumotlarni tozalash
            del TEMP_POLLS[user_id]
            del USER_STATE[user_id]
            context.user_data.clear()

            poll_type = "Kviz" if poll.is_quiz else "So'rovnoma"
            query.edit_message_text(
                f"✅ Muvaffaqiyat! Sizning {poll_type}ingiz chatda nashr etildi. "
                "Uni yopish yoki natijalarni eksport qilish uchun `/manage_polls` dan foydalaning."
            )
            query.answer("So'rovnoma Nashr Etildi!")
            return

        except Exception as e:
            logger.error(f"So'rovnomani nashr qilishda xatolik: {e}")
            query.edit_message_text("❌ Nashr qilishda xatolik yuz berdi.")
            # Xatolik yuz berganda ham vaqtinchalik ma'lumotlarni tozalash
            del TEMP_POLLS[user_id]
            del USER_STATE[user_id]

    # Konfiguratsiya tugmalarini yangilash
    keyboard = get_config_keyboard(user_id, is_quiz)
    query.edit_message_reply_markup(reply_markup=keyboard)

# --- Callback Query Handlers (Voting) ---

def handle_vote(update: Update, context: CallbackContext) -> None:
    """Handles the inline keyboard button presses for voting."""
    query = update.callback_query
    user = query.from_user
    
    # O'rnatilgan format: vote_pollid_optionindex
    _, poll_id, option_index_str = query.data.split('_')
    option_index = int(option_index_str)
    
    if poll_id not in POLLS:
        query.answer(text="❌ Bu so'rovnoma endi mavjud emas.", show_alert=True)
        query.edit_message_text("❌ Bu so'rovnoma endi mavjud emas.", reply_markup=None, parse_mode=ParseMode.MARKDOWN)
        return

    poll = POLLS[poll_id]
    
    if poll.is_closed:
        query.answer(text="❌ Bu so'rovnoma yopiq.", show_alert=True)
        return

    current_choices = poll.voters.get(user.id, [])

    if poll.is_multi_choice:
        # Ko'p tanlov rejimi
        if option_index in current_choices:
            current_choices.remove(option_index)
            poll.votes[option_index] -= 1
            query.answer(text="Tanlov bekor qilindi.")
        else:
            current_choices.append(option_index)
            poll.votes[option_index] += 1
            query.answer(text="Tanlandi.")
            
        poll.voters[user.id] = current_choices
        
    else:
        # Yagona tanlov rejimi
        old_index = current_choices[0] if current_choices else None
        
        if old_index == option_index:
            query.answer(text="Ovoz saqlandi!")
            # Agar ovoz o'zgarmasa, xabarni tahrirlashga urinmaslik uchun tez chiqib ketish
            try:
                query.edit_message_text(
                    poll.get_results_summary(user.id), 
                    reply_markup=poll.get_keyboard(user.id), 
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                pass
            return
            
        # Oldingi ovozni olib tashlash
        if old_index is not None:
            poll.votes[old_index] -= 1
            
        # Yangi ovozni qo'shish
        poll.votes[option_index] += 1
        poll.voters[user.id] = [option_index]
        
        query.answer(text="Ovoz saqlandi!")

    new_summary = poll.get_results_summary(user.id)
    new_keyboard = poll.get_keyboard(user.id)
    
    try:
        query.edit_message_text(
            new_summary,
            reply_markup=new_keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.debug(f"Could not edit message: {e}")

def handle_vote_done(update: Update, context: CallbackContext) -> None:
    """Handles the 'Done Voting' button for multi-choice polls."""
    query = update.callback_query
    user_id = query.from_user.id
    
    _, _, poll_id = query.data.split('_')
    
    poll = POLLS.get(poll_id)
    if not poll or not poll.is_multi_choice:
        query.answer("So'rovni qayta ishlashda xatolik.", show_alert=True)
        return

    # Bu tugma bosilganda faqat natijalarni yangilash kerak, ovoz berish jarayoni o'zgarmaydi
    new_summary = poll.get_results_summary(user_id)
    new_keyboard = poll.get_keyboard(user_id)

    query.answer("Natijalar yangilandi.")
    try:
        query.edit_message_text(
            new_summary,
            reply_markup=new_keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.debug(f"Could not edit message after done voting: {e}")

# --- Callback Query Handlers (Management) ---

def manage_polls_command(update: Update, context: CallbackContext) -> None:
    """Lists active polls created by the user and provides options to close/export them."""
    user_id = update.effective_user.id
    
    # Faqat joriy foydalanuvchi yaratgan so'rovnomalarni olish
    user_polls = [
        poll for poll in POLLS.values() 
        if poll.creator_id == user_id
    ]

    if not user_polls:
        update.message.reply_text("Sizda boshqarish uchun faol yoki yopiq so'rovnomalar mavjud emas.")
        return

    keyboard = []
    for poll in user_polls:
        status = "✅ FAOLL" if not poll.is_closed else "🛑 YOPIQ"
        poll_type = "KVIZ" if poll.is_quiz else "SO'ROVNOMA"
        question_preview = poll.question[:30] + ('...' if len(poll.question) > 30 else '')
        
        keyboard.append([
            InlineKeyboardButton(f"[{status} {poll_type}] {question_preview}", 
                                 callback_data=f"manage_view_{poll.poll_id}")
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(
        "*Boshqarish uchun so'rovnomani tanlang:*\n\n"
        "_Bu yerda siz So'rovnomani Yopishingiz, Eksport Qilishingiz yoki O'chirishingiz mumkin._",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

def handle_management_view(update: Update, context: CallbackContext) -> None:
    """Displays the action buttons (Close, Export, Delete) for a selected poll."""
    query = update.callback_query
    user_id = query.from_user.id
    
    _, _, poll_id = query.data.split('_')
    poll = POLLS.get(poll_id)

    if not poll or poll.creator_id != user_id:
        query.answer("❌ So'rovnoma topilmadi yoki siz yaratuvchi emassiz.", show_alert=True)
        return

    close_button = InlineKeyboardButton(
        "🛑 So'rovnomani Yopish", 
        callback_data=f"manage_close_{poll_id}"
    )
    open_button = InlineKeyboardButton(
        "▶️ So'rovnomani Qayta Ochish", 
        callback_data=f"manage_open_{poll_id}"
    )

    action_keyboard = [
        [close_button] if not poll.is_closed else [open_button],
        [InlineKeyboardButton("📊 Natijalarni Eksport Qilish (CSV)", callback_data=f"manage_export_{poll_id}")],
        [InlineKeyboardButton("🗑️ So'rovnomani O'chirish (Doimiy)", callback_data=f"manage_delete_{poll_id}")],
        [InlineKeyboardButton("🔙 Ro'yxatga Qaytish", callback_data="manage_back_list")]
    ]
    
    status = "YOPIQ" if poll.is_closed else "FAOL"
    
    query.edit_message_text(
        f"*So'rovnomani boshqarish: {poll.question[:50]}...*\nHolat: *{status}*",
        reply_markup=InlineKeyboardMarkup(action_keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    query.answer()

def handle_management_action(update: Update, context: CallbackContext) -> None:
    """Handles Close, Open, Export, Delete actions."""
    query = update.callback_query
    user_id = query.from_user.id
    
    _, action, poll_id = query.data.split('_')
    poll = POLLS.get(poll_id)

    if not poll or poll.creator_id != user_id:
        query.answer("❌ So'rovnoma topilmadi yoki siz yaratuvchi emassiz.", show_alert=True)
        return

    if action in ['close', 'open']:
        # So'rovnomani yopish/ochish
        poll.is_closed = (action == 'close')
        
        try:
            # Asosiy xabarni tahrirlash (natijalarni yangilash va tugmalarni olib tashlash/qo'shish)
            context.bot.edit_message_text(
                chat_id=poll.chat_id,
                message_id=poll.message_id,
                text=poll.get_results_summary(user_id),
                reply_markup=poll.get_keyboard(user_id),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.warning(f"Asosiy so'rovnoma xabarini tahrirlashda xatolik {poll.message_id}: {e}")

        status_msg = "yopildi" if poll.is_closed else "qayta ochildi"
        query.answer(f"✅ So'rovnoma muvaffaqiyatli {status_msg}!")
        
        # Boshqarish menyusini yangilash
        query.data = f"manage_view_{poll_id}"
        handle_management_view(update, context)
        
    elif action == 'export':
        # Natijalarni CSV sifatida eksport qilish
        csv_data = generate_export_csv(poll)
        
        context.bot.send_document(
            chat_id=user_id, # Faqat yaratuvchiga yuborish
            document=StringIO(csv_data),
            filename=f"poll_results_{poll_id}.csv",
            caption=f"Natijalar: *{poll.question[:50]}...*",
            parse_mode=ParseMode.MARKDOWN
        )
        query.answer("📊 Natijalar faylga eksport qilindi!")
        
    elif action == 'delete':
        # So'rovnomani butunlay o'chirish
        try:
            context.bot.edit_message_text(
                chat_id=poll.chat_id,
                message_id=poll.message_id,
                text=f"*[ O'CHIRILGAN ]* Bu so'rovnoma yaratuvchi tomonidan butunlay olib tashlandi.",
                reply_markup=None,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            pass
            
        del POLLS[poll_id]
        query.answer("🗑️ So'rovnoma butunlay o'chirildi!", show_alert=True)
        
        # Ro'yxatga qaytish
        query.data = "manage_back_list"
        handle_management_action(update, context)

    elif action == 'back_list':
        # Ro'yxatga qaytish tugmasini bosish
        query.answer()
        manage_polls_command(update, context)

def main() -> None:
    """Start the bot."""
    # BOT_TOKEN .env faylidan yuklanadi
    if not BOT_TOKEN:
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("XATOLIK: BOT_TOKEN o'rnatilmagan. Iltimos, .env faylini tekshiring.")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        return

    updater = Updater(BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    # --- Buyruqlar Boshqaruvchilari ---
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("create_poll", create_poll_command))
    dispatcher.add_handler(CommandHandler("create_quiz", create_quiz_command))
    dispatcher.add_handler(CommandHandler("manage_polls", manage_polls_command))
    dispatcher.add_handler(CommandHandler("cancel", cancel_command)) 
    
    # --- Matn Kiritish Boshqaruvchisi (so'rovnoma/kviz yaratish uchun) ---
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text_input))

    # --- Callback Query Boshqaruvchilari ---
    dispatcher.add_handler(CallbackQueryHandler(handle_configuration, pattern='^config_'))
    # Ovoz berish tugmalari uchun (vote_pollid_optionindex)
    dispatcher.add_handler(CallbackQueryHandler(handle_vote, pattern='^vote_[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}_\d+$'))
    # Ko'p tanlov uchun "Tayyor" tugmasi
    dispatcher.add_handler(CallbackQueryHandler(handle_vote_done, pattern='^vote_done_'))
    # Boshqaruv menyusini ko'rish
    dispatcher.add_handler(CallbackQueryHandler(handle_management_view, pattern='^manage_view_'))
    # Boshqaruv harakatlari (yopish, eksport, o'chirish, qaytish)
    dispatcher.add_handler(CallbackQueryHandler(handle_management_action, pattern='^manage_(close|open|export|delete|back_list)_'))

    # Botni ishga tushirish
    updater.start_polling()

    # Ctrl-C bosilguncha botni ishlatish
    updater.idle()

if __name__ == '__main__':
    main()


