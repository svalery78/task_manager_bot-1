# main.py
# -*- coding: utf-8 -*-
from datetime import datetime
import pytz
from telegram import Update, ForceReply
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import logging
from config import TELEGRAM_BOT_TOKEN
from task_manager import add_task, get_user_tasks, mark_task_as_done, update_task_text, add_task_note, set_task_priority, schedule_reminder, scheduler
import db # Импортируем db для доступа к Task модели
from ai_service import generate_ai_response

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    ai_greeting = generate_ai_response(f"Пользователь {user.full_name} только что начал диалог с ботом. Приветствуй его как дружелюбный AI-ассистент, расскажи, что ты умеешь (помогать с задачами, напоминать, мотивировать).", user.id)
    await update.message.reply_html(
        rf"Привет, {user.mention_html()}! {ai_greeting}",
        reply_markup=ForceReply(selective=True),
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "Привет! Я твой личный AI-ассистент по задачам! Вот что я умею:\n\n"
        "*/add <текст задачи> [дата/время] [приоритет] [#категория]* - Добавить новую задачу "
        "(например, `/add Купить молоко завтра в 18:00 high #покупки`). "
        "Приоритет может быть `high`, `medium` или `low` (по умолчанию `medium`). "
        "Категория указывается со знаком `#`.\n" # <-- ОБНОВЛЕНО описание /add
        "*/list [категория]* - Показать все твои активные задачи, отсортированные по приоритету. "
        "Опционально можно указать категорию (например, `/list покупки`).\n" # <-- ОБНОВЛЕНО описание /list
        "*/done <номер задачи>* - Отметить задачу как выполненную.\n"
        "*/edit <номер задачи> <новый текст>* - Изменить текст существующей задачи.\n"
        "*/note <номер задачи> <текст заметки>* - Добавить заметку или уточнение к задаче.\n"
        "*/set_priority <номер задачи> <high|medium|low>* - Изменить приоритет существующей задачи. \n"
        "*/help* - Показать это сообщение.\n\n"
        "Просто напиши мне задачу, и я постараюсь ее понять!"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def add_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not context.args:
        ai_response = generate_ai_response(f"Пользователь {user_id} ввел /add без текста задачи. Попроси его ввести текст задачи.", user_id)
        await update.message.reply_text(ai_response)
        return

    raw_task_text = " ".join(context.args)
    response_message = add_task(user_id, raw_task_text)
    await update.message.reply_text(response_message)

    # Если задача была успешно добавлена и у нее есть время, запланировать напоминание
    if "Напомню тебе" in response_message:
        session = db.get_session()
        task = session.query(db.Task).filter_by(user_id=user_id, task_text=raw_task_text).order_by(db.Task.created_at.desc()).first()
        if task and task.due_date:
            schedule_reminder(context.application.bot, update.effective_chat.id, task.id, task.task_text, task.due_date)
        session.close()

async def list_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    category_filter = None
    if context.args: # Если есть аргументы, считаем это категорией
        category_filter = context.args[0].lower() # Категория в нижнем регистре для поиска

    tasks = get_user_tasks(user_id, category=category_filter) # <-- НОВОЕ: Передаем категорию в get_user_tasks

    if not tasks:
        if category_filter:
            ai_response = generate_ai_response(f"Пользователь {user_id} запросил список задач по категории '{category_filter}', но задач нет. Предложи добавить.", user_id)
        else:
            ai_response = generate_ai_response(f"Пользователь {user_id} запросил список задач, но у него их нет. Предложи добавить.", user_id)
        await update.message.reply_text(ai_response)
        return

    message = "Твои текущие задачи:\n\n"
    if category_filter:
        message = f"Твои задачи в категории *{category_filter.capitalize()}*:\n\n"

    for task in tasks: # Итерируемся по task, а не enumerate, чтобы использовать task.id
        due_date_str = ""
        if task.due_date:
            display_tz = pytz.timezone('Europe/Amsterdam')
            display_due_date = task.due_date.astimezone(display_tz)
            due_date_str = f" (до {display_due_date.strftime('%Y-%m-%d %H:%M')})"

        notes_str = f" _(Заметки: {task.notes})_" if task.notes else ""

        priority_display = ""
        if task.priority == 'high':
            priority_display = " 🔥*Высокий приоритет*🔥"
        elif task.priority == 'medium':
            priority_display = " 🟡Средний приоритет"
        elif task.priority == 'low':
            priority_display = " 🟢Низкий приоритет"

        category_display = ""
        if task.category: # <-- НОВОЕ: Отображаем категорию
            category_display = f" #{task.category}"

        message += f"*{task.id}.* {task.task_text}{due_date_str}{notes_str}{priority_display}{category_display}\n"
    await update.message.reply_text(message, parse_mode='Markdown')

async def done_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not context.args or not context.args[0].isdigit():
        ai_response = generate_ai_response(f"Пользователь {user_id} ввел /done без номера задачи или с неверным номером. Попроси ввести номер.", user_id)
        await update.message.reply_text(ai_response)
        return

    task_id = int(context.args[0])
    response_message = mark_task_as_done(user_id, task_id)
    await update.message.reply_text(response_message)

async def edit_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if len(context.args) < 2 or not context.args[0].isdigit():
        ai_response = generate_ai_response(f"Пользователь {user_id} ввел /edit без номера задачи или нового текста. Попроси ввести корректно.", user_id)
        await update.message.reply_text(ai_response)
        return

    task_id = int(context.args[0])
    new_text = " ".join(context.args[1:])
    response_message = update_task_text(user_id, task_id, new_text)
    await update.message.reply_text(response_message)

async def add_note_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if len(context.args) < 2 or not context.args[0].isdigit():
        ai_response = generate_ai_response(f"Пользователь {user_id} ввел /note без номера задачи или текста заметки. Попроси ввести корректно.", user_id)
        await update.message.reply_text(ai_response)
        return

    task_id = int(context.args[0])
    note_text = " ".join(context.args[1:])
    response_message = add_task_note(user_id, task_id, note_text)
    await update.message.reply_text(response_message)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    text = update.message.text

    # Попытка добавить задачу, если это не команда
    if not text.startswith('/'):
        response_message = add_task(user_id, text)
        await update.message.reply_text(response_message)

        # Если задача была успешно добавлена и у нее есть время, запланировать напоминание
        if "Напомню тебе" in response_message:
            session = db.get_session()
            task = session.query(db.Task).filter_by(user_id=user_id, task_text=text).order_by(db.Task.created_at.desc()).first()
            if task and task.due_date:
                schedule_reminder(context.application.bot, update.effective_chat.id, task.id, task.task_text, task.due_date)
            session.close()

    else:
        # Для других сообщений, которые не являются командами
        ai_response = generate_ai_response(f"Пользователь {user_id} написал: '{text}'. Ответь ему как дружелюбный AI-ассистент.", user_id)
        await update.message.reply_text(ai_response)

async def set_priority_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    # Expects /set_priority <task_id> <priority>
    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text("Пожалуйста, используйте формат: `/set_priority <номер задачи> <high|medium|low>`", parse_mode='Markdown')
        return

    task_id = int(context.args[0])
    new_priority = context.args[1].lower() # Ensure it's lowercase for validation

    response_message = set_task_priority(user_id, task_id, new_priority)
    await update.message.reply_text(response_message, parse_mode='Markdown')


def main() -> None:
    # ... (application setup - без изменений) ...
    print("Запуск бота...")
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    print("Бот тестовый принт.")

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add", add_task_command))
    application.add_handler(CommandHandler("list", list_tasks_command)) # <-- Обновлен
    application.add_handler(CommandHandler("done", done_task_command))
    application.add_handler(CommandHandler("edit", edit_task_command))
    application.add_handler(CommandHandler("note", add_note_command))
    application.add_handler(CommandHandler("set_priority", set_priority_command))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
   
    print("Бот запущен. Нажмите Ctrl+C для остановки.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    import db # Импортируем db для создания таблиц при запуске
    main()