# task_manager.py
# -*- coding: utf-8 -*-

from datetime import datetime
from db import Task, get_session
from ai_service import parse_task_with_ai
import dateparser
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

scheduler = BackgroundScheduler()
scheduler.start()

# Helper for priority sorting (map string priorities to sortable numbers)
PRIORITY_ORDER = {'high': 3, 'medium': 2, 'low': 1}

# Функция для добавления напоминания в планировщик
def schedule_reminder(bot_app, chat_id, task_id, task_text, due_date):
    if due_date:
        job_id = f"reminder_{task_id}"
        scheduler.add_job(
            send_reminder_message,
            'date',
            run_date=due_date,
            args=[bot_app, chat_id, task_id, task_text],
            id=job_id,
            replace_existing=True
        )
        print(f"Напоминание для задачи {task_id} запланировано на {due_date}")

# Function that will send a reminder
async def send_reminder_message(bot_app, chat_id, task_id, task_text):
    # Get a new session for this async function
    session = get_session()
    try:
        task = session.query(Task).filter_by(id=task_id).first()
        if task and task.status == 'pending': # Send only if task is still pending
            now_utc = datetime.now(pytz.utc)
            # Ensure the scheduled task hasn't been completed or passed long ago
            if task.due_date and task.due_date <= now_utc:
                await bot_app.send_message(chat_id, f"Привет! 👋 Просто напоминаю, что у тебя есть задача: *{task_text}*! Давай ее сделаем?")
                # Optional: You might want to update task status to 'overdue' here
    except Exception as e:
        print(f"Ошибка при отправке напоминания для задачи {task_id}: {e}")
    finally:
        session.close()


def add_task(user_id: int, raw_task_text: str) -> str:
    session = get_session()
    try:
        default_timezone = pytz.utc

        parsed_data = parse_task_with_ai(raw_task_text, user_id)
        task_text = parsed_data.get('task_text')
        due_date_str = parsed_data.get('due_date')
        priority = parsed_data.get('priority', 'medium').lower()
        category = parsed_data.get('category', None) # <-- НОВОЕ: Получаем категорию

        # Validate priority (остается как было)
        if priority not in PRIORITY_ORDER:
            priority = 'medium'

        if not task_text:
            return "Я не смог понять, что это за задача. Пожалуйста, попробуй сформулировать яснее."

        # ... (парсинг due_date_str - без изменений) ...
        due_date = None
        if due_date_str:
            try:
                due_date = dateparser.parse(
                    due_date_str,
                    settings={
                        'TIMEZONE': default_timezone.tzname(datetime.now()),
                        'PREFER_DATES_FROM': 'future',
                        'RELATIVE_BASE': datetime.now(default_timezone)
                    }
                )
                if due_date and due_date.tzinfo is None:
                    due_date = default_timezone.localize(due_date)
            except Exception as e:
                print(f"Ошибка парсинга due_date_str через dateparser: {e}")
                try:
                    due_date = datetime.strptime(due_date_str, '%Y-%m-%d %H:%M:%S')
                    due_date = default_timezone.localize(due_date)
                except ValueError:
                    pass

        if not due_date and ("напомни" in raw_task_text.lower() or "завтра" in raw_task_text.lower() or "послезавтра" in raw_task_text.lower() or "в среду" in raw_task_text.lower()):
            due_date = dateparser.parse(
                raw_task_text,
                settings={
                    'PREFER_DATES_FROM': 'future',
                    'RELATIVE_BASE': datetime.now(default_timezone),
                    'TIMEZONE': default_timezone.tzname(datetime.now())
                }
            )
            if due_date and due_date.tzinfo is None:
                 due_date = default_timezone.localize(due_date)

        # <-- НОВОЕ: Передаем category в конструктор Task
        new_task = Task(user_id=user_id, task_text=task_text, due_date=due_date, priority=priority, category=category)
        session.add(new_task)
        session.commit()

        response_message = f"Отлично! Я записал задачу: *{new_task.task_text}*."
        if new_task.due_date:
            display_due_date = new_task.due_date.astimezone(pytz.timezone('Europe/Amsterdam'))
            response_message += f"\nНапомню тебе {display_due_date.strftime('%Y-%m-%d в %H:%M')} ({display_due_date.tzinfo.tzname(display_due_date)})."
        response_message += f"\nПриоритет: *{priority.capitalize()}*."
        if new_task.category: # <-- НОВОЕ: Добавляем категорию в ответ
            response_message += f"\nКатегория: *{new_task.category.capitalize()}*."
        
               # Schedule reminder immediately after task addition
        if new_task.due_date:
            # You need to pass `context.application.bot` from main.py
            # This is handled in main.py's add_task_command where `schedule_reminder` is called.
            pass # No need to call here, main.py will handle it

        return response_message
    except Exception as e:
        session.rollback()
        print(f"Ошибка при добавлении задачи: {e}")
        return "Извини, что-то пошло не так при добавлении задачи."
    finally:
        session.close()

# --- ОБНОВЛЕННАЯ ФУНКЦИЯ get_user_tasks для фильтрации по категории ---
def get_user_tasks(user_id: int, status: str = 'pending', category: str = None) -> list[Task]:
    session = get_session()
    try:
        query = session.query(Task).filter_by(user_id=user_id)
        if status != 'all':
            query = query.filter_by(status=status)
        
        if category: # <-- НОВОЕ: фильтрация по категории
            query = query.filter_by(category=category.lower()) # Сохраняем в нижнем регистре

        tasks = query.all()
        # Sort in Python after fetching
        tasks.sort(key=lambda task: (PRIORITY_ORDER.get(task.priority, 0), task.due_date if task.due_date else datetime.max.replace(tzinfo=pytz.utc)), reverse=True)
        # We sort high, medium, low, so 'high' (3) should be at the top, hence reverse=True
        # For due_date, we want earliest first, so keep it as is if `reverse=False` on due_date part.
        # But since we're using lambda for primary sort, a bit tricky.
        # Corrected sort logic: sort by priority (desc), then by due_date (asc)
        tasks.sort(key=lambda task: (PRIORITY_ORDER.get(task.priority, 0), task.due_date if task.due_date else datetime.max.replace(tzinfo=pytz.utc)))
        tasks.reverse() # Reverse the whole list to get high priority first

        return tasks
    except Exception as e:
        print(f"Ошибка при получении задач: {e}")
        return []
    finally:
        session.close()

def mark_task_as_done(user_id: int, task_id: int) -> str:
    session = get_session()
    try:
        task = session.query(Task).filter_by(user_id=user_id, id=task_id).first()
        if task:
            task.status = 'completed'
            task.updated_at = datetime.now(pytz.utc) # Use timezone-aware datetime
            session.commit()
            return f"Поздравляю! Задача '{task.task_text}' отмечена как выполненная! 🎉 Ты просто молодец!"
        else:
            return "Задачи с таким номером не найдено или она не принадлежит тебе."
    except Exception as e:
        session.rollback()
        print(f"Ошибка при отметке задачи как выполненной: {e}")
        return "Произошла ошибка при попытке отметить задачу."
    finally:
        session.close()

def update_task_text(user_id: int, task_id: int, new_text: str) -> str:
    session = get_session()
    try:
        task = session.query(Task).filter_by(user_id=user_id, id=task_id).first()
        if task:
            task.task_text = new_text
            task.updated_at = datetime.now(pytz.utc) # Use timezone-aware datetime
            session.commit()
            return f"Текст задачи '{task_id}' обновлен на: *{new_text}*."
        else:
            return "Задачи с таким номером не найдено или она не принадлежит тебе."
    except Exception as e:
        session.rollback()
        print(f"Ошибка при обновлении текста задачи: {e}")
        return "Произошла ошибка при попытке обновить текст задачи."
    finally:
        session.close()

def add_task_note(user_id: int, task_id: int, note: str) -> str:
    session = get_session()
    try:
        task = session.query(Task).filter_by(user_id=user_id, id=task_id).first()
        if task:
            if task.notes:
                task.notes += f"\n--- Дополнение ({datetime.now(pytz.utc).strftime('%Y-%m-%d %H:%M')}): {note}" # Use timezone-aware datetime
            else:
                task.notes = f"Дополнение ({datetime.now(pytz.utc).strftime('%Y-%m-%d %H:%M')}): {note}" # Use timezone-aware datetime
            task.updated_at = datetime.now(pytz.utc) # Use timezone-aware datetime
            session.commit()
            return f"К задаче '{task.id}' добавлена заметка. Теперь она выглядит так: _{task.notes}_"
        else:
            return "Задачи с таким номером не найдено или она не принадлежит тебе."
    except Exception as e:
        session.rollback()
        print(f"Ошибка при добавлении заметки к задаче: {e}")
        return "Произошла ошибка при попытке добавить заметку."
    finally:
        session.close()

# NEW FUNCTION: Set Task Priority
def set_task_priority(user_id: int, task_id: int, new_priority: str) -> str:
    session = get_session()
    try:
        task = session.query(Task).filter_by(user_id=user_id, id=task_id).first()
        if task:
            new_priority_lower = new_priority.lower()
            if new_priority_lower in PRIORITY_ORDER:
                task.priority = new_priority_lower
                task.updated_at = datetime.now(pytz.utc) # Use timezone-aware datetime
                session.commit()
                return f"Приоритет задачи '{task.id}' изменен на *{new_priority.capitalize()}*."
            else:
                return f"Неизвестный приоритет '{new_priority}'. Используйте 'high', 'medium' или 'low'."
        else:
            return "Задачи с таким номером не найдено или она не принадлежит тебе."
    except Exception as e:
        session.rollback()
        print(f"Ошибка при изменении приоритета задачи: {e}")
        return "Произошла ошибка при попытке изменить приоритет задачи."
    finally:
        session.close()