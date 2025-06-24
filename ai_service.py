# ai_service.py
# -*- coding: utf-8 -*-

import requests
import json
import re
from datetime import datetime
import pytz

from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, OPENROUTER_MODEL

def generate_ai_response(prompt: str, user_id: int, model: str = OPENROUTER_MODEL) -> str:
    # ... (оставьте эту функцию без изменений) ...
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "Task_Manager_Telegram_Bot",
        "X-Title": "Task Manager Bot"
    }
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Ты дружелюбный и полезный AI-ассистент по управлению задачами в Telegram. Твоя цель - помогать пользователю быть продуктивным, напоминать о задачах, мотивировать и общаться в живом, поддерживающем стиле."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 200
    }

    try:
        response = requests.post(OPENROUTER_BASE_URL, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        response_data = response.json()
        return response_data['choices'][0]['message']['content'].strip()
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе к OpenRouter: {e}")
        return "Извини, я сейчас не могу связаться со своим мозгом. Попробуй позже."
    except KeyError:
        print(f"Неожиданный формат ответа от OpenRouter: {response.text}")
        return "Ой, что-то пошло не так с ответом. Могу ли я чем-то еще помочь?"

def parse_task_with_ai(task_text: str, user_id: int) -> dict:
    now_utc = datetime.now(pytz.utc)
    current_date_str = now_utc.strftime('%Y-%m-%d')

    # --- ОБНОВЛЕННЫЙ ПРОМПТ ДЛЯ AI с полем 'category' ---
    prompt = (
        f"Пользователь '{user_id}' хочет добавить задачу: '{task_text}'. "
        f"Текущая дата (UTC): {current_date_str}. "
        "Извлеки из текста задачи:\n"
        "1. **task_text**: Сама суть задачи (например, 'Купить молоко', 'Позвонить другу').\n"
        "2. **due_date**: Дата и время в формате `YYYY-MM-DD HH:MM:SS` или `null`, если не указано.\n"
        "3. **priority**: Приоритет задачи. Должен быть одним из: 'high', 'medium', 'low'. "
        "Если приоритет явно указан в тексте (например, 'высокий', 'low', 'средний'), используй его. "
        "Если не указан, используй 'medium'.\n"
        "4. **category**: Категория задачи. Может быть любой строкой (например, 'Работа', 'Личное', 'Покупки', 'Спорт'). "
        "Если категория указана в тексте (например, 'задача #работа', 'купить молоко #покупки'), извлеки её. "
        "Если не указана, используй `null`.\n" # <-- Изменено: теперь 'null' для отсутствующей категории
        "**Обязательно** возвращай JSON-объект, содержащий *все четыре* поля: `task_text`, `due_date`, `priority`, `category`.\n"
        "Если не можешь понять, что задача, установи `task_text` в `null`."
        "\nПримеры:\n"
        " - 'Купить хлеб завтра в 18:00 high #покупки' -> `{{\"task_text\": \"Купить хлеб\", \"due_date\": \"{tomorrow_date} 18:00:00\", \"priority\": \"high\", \"category\": \"покупки\"}}`\n"
        " - 'Заплатить по счету low #финансы' -> `{{\"task_text\": \"Заплатить по счету\", \"due_date\": null, \"priority\": \"low\", \"category\": \"финансы\"}}`\n"
        " - 'Позвонить другу' -> `{{\"task_text\": \"Позвонить другу\", \"due_date\": null, \"priority\": \"medium\", \"category\": null}}`\n"
        " - 'Тренировка в зале #спорт' -> `{{\"task_text\": \"Тренировка в зале\", \"due_date\": null, \"priority\": \"medium\", \"category\": \"спорт\"}}`\n"
        "Твой ответ должен быть *только* JSON-объектом, без лишнего текста или форматирования (например, ```json)."
    )
    # --- КОНЕЦ ОБНОВЛЕННОГО ПРОМПТА ---

    ai_response = generate_ai_response(prompt, user_id)

    # --- Начало блока отладки (оставьте как есть для отладки) ---
    print(f"\n--- Отладочный вывод ai_service.py ---")
    print(f"Исходный raw_task_text: '{task_text}'")
    print(f"Промпт, отправленный AI:\n{prompt}")
    print(f"Сырой ответ AI: '{ai_response}'")
    # --- Конец блока отладки ---

    try:
        match = re.search(r'\{.*\}', ai_response, re.DOTALL)
        if match:
            json_string = match.group(0)
            parsed_data = json.loads(json_string)

            # --- Отладочный вывод распарсенных данных ---
            print(f"Извлеченная JSON-строка: '{json_string}'")
            print(f"Распарсенные данные (до валидации): {parsed_data}")
            # --- Конец отладки ---

            # --- Валидация и fallback для полей ---
            # Priority validation (остается как было)
            ai_priority = parsed_data.get('priority', 'medium').lower()
            if ai_priority not in ['high', 'medium', 'low']:
                print(f"AI вернул невалидный приоритет '{ai_priority}', используя 'medium'.")
                ai_priority = 'medium'
            parsed_data['priority'] = ai_priority

            # Category validation and fallback (НОВОЕ)
            ai_category = parsed_data.get('category', None) # Получаем категорию, по умолчанию None
            if isinstance(ai_category, str): # Если AI вернул строку, делаем её lowercase и обрезаем пробелы
                ai_category = ai_category.strip().lower()
                if not ai_category: # Если строка пустая после обрезки, считаем null
                    ai_category = None
            else: # Если AI вернул не строку (например, пустой массив, число, или отсутствовало поле)
                ai_category = None
            parsed_data['category'] = ai_category


            # Task_text fallback (остается как было)
            if 'task_text' not in parsed_data or parsed_data['task_text'] is None:
                parsed_data['task_text'] = task_text

            print(f"Финальные распарсенные данные (после валидации): {parsed_data}")
            return parsed_data
        else:
            print(f"Не удалось найти JSON-объект в ответе AI: '{ai_response}'")
            return {"task_text": task_text, "due_date": None, "priority": "medium", "category": None}

    except json.JSONDecodeError as e:
        print(f"Ошибка JSONDecodeError при парсинге очищенного ответа AI: {e}. Ответ: '{ai_response}'")
        return {"task_text": task_text, "due_date": None, "priority": "medium", "category": None}
    except Exception as e:
        print(f"Непредвиденная ошибка в parse_task_with_ai: {e}. Ответ: '{ai_response}'")
        return {"task_text": task_text, "due_date": None, "priority": "medium", "category": None}