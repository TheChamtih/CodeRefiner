from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler, CommandHandler, MessageHandler, Filters, CallbackQueryHandler
from database import init_db, get_admin_ids, add_admin, get_locations, get_location_by_id
from config import MAIN_ADMIN_ID
import re
from datetime import datetime
import psycopg2
from psycopg2.extras import DictCursor
import os
from typing import List, Dict
import math

# Добавим новые функции для работы с рекомендациями
def calculate_course_score(user_age: int, user_interests: str, course: Dict) -> float:
    """Вычисляет релевантность курса для пользователя."""
    # Базовый скор
    score = 1.0

    # Вес по возрасту (чем ближе к середине возрастного диапазона, тем лучше)
    age_range_center = (course['min_age'] + course['max_age']) / 2
    age_distance = abs(user_age - age_range_center)
    age_score = 1.0 / (1 + age_distance)
    score *= age_score

    # Вес по интересам
    user_interests_list = set(user_interests.lower().split())
    course_tags = get_course_tags(course['id'])
    matching_interests = len(user_interests_list.intersection(course_tags))
    interest_score = 1.0 + (matching_interests * 0.5)
    score *= interest_score

    return score

def get_course_tags(course_id: int) -> List[str]:
    """Получает теги курса из базы данных."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT tag FROM course_tags WHERE course_id = %s', (course_id,))
    tags = [row[0].lower() for row in cursor.fetchall()]
    conn.close()
    return tags

# Состояния для ConversationHandler
NAME, AGE, INTERESTS, PARENT_NAME, PHONE, COURSE_SELECTION, LOCATION_SELECTION, CONFIRMATION = range(8)

def is_valid_phone(phone: str) -> bool:
    """Проверяет, начинается ли номер на +7 или 8."""
    return re.match(r'^(\+7|8)[\s\-]?(\d{3})[\s\-]?(\d{3})[\s\-]?(\d{2})[\s\-]?(\d{2})$', phone) is not None

def notify_admins(context: CallbackContext, message: str):
    """Отправляет уведомление всем администраторам."""
    admins = get_admin_ids()
    for admin in admins:
        try:
            context.bot.send_message(chat_id=admin, text=message)
        except Exception as e:
            print(f"Failed to send message to admin {admin}: {e}")

def clear_user_data(context: CallbackContext):
    """Очищает данные пользователя."""
    context.user_data.clear()

def start(update: Update, context: CallbackContext) -> int:
    """Начало диалога для записи на пробное занятие."""
    update.message.reply_text("Привет! Давайте подберем курс для вашего ребенка. Как зовут вашего ребенка?")
    return NAME

def get_name(update: Update, context: CallbackContext) -> int:
    """Получение имени ребенка."""
    user_name = update.message.text
    context.user_data['child_name'] = user_name
    update.message.reply_text(f"Отлично, {user_name}! Сколько лет вашему ребенку?")
    return AGE

def get_age(update: Update, context: CallbackContext) -> int:
    """Получение возраста ребенка."""
    try:
        user_age = int(update.message.text)
        if user_age < 6 or user_age > 18:
            update.message.reply_text("Возраст должен быть от 6 до 18 лет. Пожалуйста, введите корректный возраст.")
            return AGE
    except ValueError:
        update.message.reply_text("Пожалуйста, введите число.")
        return AGE

    context.user_data['child_age'] = user_age
    update.message.reply_text("Чем увлекается ваш ребенок? (например, программирование, дизайн, математика и т.д.)")
    return INTERESTS

def get_interests(update: Update, context: CallbackContext) -> int:
    """Получение интересов ребенка."""
    user_interests = update.message.text
    context.user_data['child_interests'] = user_interests
    update.message.reply_text("Как вас зовут? (Имя родителя)")
    return PARENT_NAME

def get_parent_name(update: Update, context: CallbackContext) -> int:
    """Получение имени родителя."""
    parent_name = update.message.text
    context.user_data['parent_name'] = parent_name
    update.message.reply_text("Укажите ваш номер телефона для связи (начинается на +7 или 8):")
    return PHONE

def get_phone(update: Update, context: CallbackContext) -> int:
    phone = update.message.text
    if not is_valid_phone(phone):
        update.message.reply_text("Номер телефона должен начинаться на +7 или 8. Пожалуйста, введите корректный номер.")
        return PHONE

    context.user_data['phone'] = phone

    # Получаем курсы, подходящие по возрасту
    child_age = context.user_data['child_age']
    child_interests = context.user_data['child_interests'].lower()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, name, description, min_age, max_age 
        FROM courses 
        WHERE min_age <= %s AND max_age >= %s
    ''', (child_age, child_age))
    courses = cursor.fetchall()
    conn.close()

    if not courses:
        update.message.reply_text("К сожалению, для вашего возраста нет доступных курсов.")
        return ConversationHandler.END

    # Вычисляем релевантность каждого курса
    scored_courses = []
    for course in courses:
        course_dict = {
            'id': course[0],
            'name': course[1],
            'description': course[2],
            'min_age': course[3],
            'max_age': course[4]
        }
        score = calculate_course_score(child_age, child_interests, course_dict)
        scored_courses.append((course, score))

    # Сортируем курсы по релевантности
    scored_courses.sort(key=lambda x: x[1], reverse=True)

    # Создаем клавиатуру с курсами, начиная с самых релевантных
    keyboard = []
    for course, score in scored_courses:
        button_text = f"📚 {course[1]}"
        if score > 1.5:  # Если курс особенно релевантен
            button_text = "⭐ " + button_text
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"course_{course[0]}")])

    keyboard.append([InlineKeyboardButton("❌ Выйти", callback_data="exit")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    recommendation_text = "На основе ваших интересов, мы подобрали следующие курсы:"
    update.message.reply_text(recommendation_text, reply_markup=reply_markup)
    return COURSE_SELECTION

def select_course(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()

    if query.data == "exit":
        query.edit_message_text("Диалог завершен. Если хотите начать заново, напишите /start.")
        clear_user_data(context)
        return ConversationHandler.END

    course_id = int(query.data.split("_")[1])
    context.user_data['selected_course'] = course_id

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.name, c.description, c.min_age, c.max_age,
               string_agg(ct.tag, ', ') as tags
        FROM courses c
        LEFT JOIN course_tags ct ON c.id = ct.course_id
        WHERE c.id = %s
        GROUP BY c.id, c.name, c.description, c.min_age, c.max_age
    ''', (course_id,))
    course = cursor.fetchone()
    conn.close()

    course_info = (
        f"📚 Курс: {course[0]}\n\n"
        f"📝 Описание: {course[1]}\n\n"
        f"👶 Возраст: {course[2]}-{course[3]} лет\n"
        f"🏷️ Теги: {course[4] if course[4] else 'не указаны'}\n\n"
        "Хотите записаться на пробное занятие?"
    )

    keyboard = [
        [InlineKeyboardButton("Да ✅", callback_data="confirm_yes"),
         InlineKeyboardButton("Нет ❌", callback_data="confirm_no")],
        [InlineKeyboardButton("❌ Выйти", callback_data="exit")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    query.edit_message_text(text=course_info, reply_markup=reply_markup)
    return CONFIRMATION


def confirm_signup(update: Update, context: CallbackContext) -> int:
    """Обработчик записи на курс."""
    query = update.callback_query
    query.answer()

    if query.data == "exit":
        query.edit_message_text("Диалог завершен. Если хотите начать заново, напишите /start.")
        clear_user_data(context)
        return ConversationHandler.END

    if query.data == "confirm_yes":
        conn = get_connection()
        cursor = conn.cursor()

        # Сохраняем данные пользователя
        cursor.execute('''
            INSERT INTO users (chat_id, parent_name, phone, child_name, child_age, child_interests)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            query.message.chat_id,
            context.user_data['parent_name'],
            context.user_data['phone'],
            context.user_data['child_name'],
            context.user_data['child_age'],
            context.user_data['child_interests']
        ))
        user_id = cursor.fetchone()[0]

        # Получаем информацию о курсе
        cursor.execute('SELECT name, description FROM courses WHERE id = %s', (context.user_data['selected_course'],))
        course = cursor.fetchone()

        # Записываем на пробное занятие
        cursor.execute('''
            INSERT INTO trial_lessons (user_id, course_id, date, confirmed)
            VALUES (%s, %s, %s, FALSE)
        ''', (user_id, context.user_data['selected_course'], datetime.now()))

        conn.commit()

        # Уведомляем администраторов
        admin_message = (
            f"Новая запись на пробное занятие:\n\n"
            f"Родитель: {context.user_data['parent_name']}\n"
            f"Телефон: {context.user_data['phone']}\n"
            f"Ребенок: {context.user_data['child_name']} ({context.user_data['child_age']} лет)\n"
            f"Интересы: {context.user_data['child_interests']}\n"
            f"Выбранный курс: {course[0]}\n"
            f"Описание курса: {course[1]}\n"
            f"Дата записи: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        notify_admins(context, admin_message)

        query.edit_message_text("Спасибо! Мы свяжемся с вами для уточнения деталей.")
        conn.close()
    else:
        query.edit_message_text("Хорошо, если передумаете, всегда можете вернуться и записаться позже.")

    clear_user_data(context)
    return ConversationHandler.END

def get_connection():
    """Gets a connection to the PostgreSQL database."""
    return psycopg2.connect(os.environ['DATABASE_URL'], cursor_factory=DictCursor)

def get_conversation_handler():
    return ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            NAME: [MessageHandler(Filters.text & ~Filters.command, get_name)],
            AGE: [MessageHandler(Filters.text & ~Filters.command, get_age)],
            INTERESTS: [MessageHandler(Filters.text & ~Filters.command, get_interests)],
            PARENT_NAME: [MessageHandler(Filters.text & ~Filters.command, get_parent_name)],
            PHONE: [MessageHandler(Filters.text & ~Filters.command, get_phone)],
            COURSE_SELECTION: [CallbackQueryHandler(select_course, pattern="^course_|^exit$")],
            CONFIRMATION: [CallbackQueryHandler(confirm_signup, pattern="^confirm_yes$|^confirm_no$|^exit$")],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

def cancel(update: Update, context: CallbackContext) -> int:
    """Отмена диалога."""
    update.message.reply_text("Диалог прерван. Если хотите начать заново, напишите /start.")
    clear_user_data(context)
    return ConversationHandler.END

def help_command(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    admins = get_admin_ids()

    help_text = """
    Список доступных команд:

    Для пользователей:
    /start - Начать диалог для подбора курса
    /courses - Показать список всех доступных курсов
    /help - Показать список всех команд
    /about - Информация о школе
    /cancel - Отменить текущий диалог
    /list_locations - Показать список всех адресов школы
    """

    if user_id in admins:
        help_text += """
        Для администраторов:
        /add_admin - Добавить нового администратора
        /delete_course - Удалить курс
        /edit_course - Редактировать курс
        /view_trials - Показать все записи на пробные занятия
        /filter_trials - Показать неподтвержденные записи
        /clear_trials - Очистить все неподтвержденные записи
        /confirm_trial - Подтвердить запись на пробное занятие
        /create_course - Создать новый курс
        /add_location - Добавить новый адрес школы
        /delete_location - Удалить адрес школы
        """

    update.message.reply_text(help_text)

def list_courses(update: Update, context: CallbackContext):
    """Показывает список всех доступных курсов."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM courses')
    courses = cursor.fetchall()
    conn.close()

    if not courses:
        update.message.reply_text("На данный момент курсов нет.")
        return

    courses_list = "\n\n".join([
        f"📚 {course[1]}\n"
        f"📝 {course[2]}\n"
        f"👶 Возраст: {course[3]}-{course[4]} лет"
        for course in courses
    ])
    update.message.reply_text(f"Доступные курсы:\n\n{courses_list}")

def about(update: Update, context: CallbackContext):
    """Показывает информацию о школе."""
    message = (
        "🎓 О школе Алгоритмика:\n\n"
        "Мы - международная школа программирования для детей и подростков.\n\n"
        "📚 Наши курсы охватывают:\n"
        "• Программирование\n"
        "• Создание игр\n"
        "• Разработку сайтов\n"
        "• Дизайн\n"
        "• Математику\n\n"
        "👨‍🏫 Опытные преподаватели\n"
        "🎯 Индивидуальный подход\n"
        "📝 Современная программа обучения\n\n"
        "Чтобы записаться на пробное занятие, используйте команду /start"
    )
    update.message.reply_text(message)

def view_trials(update: Update, context: CallbackContext):
    """Показывает все записи на пробные занятия."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 
            trial_lessons.id,
            users.child_name,
            users.parent_name,
            users.phone,
            courses.name,
            trial_lessons.date
        FROM trial_lessons
        JOIN users ON trial_lessons.user_id = users.id
        JOIN courses ON trial_lessons.course_id = courses.id
    ''')
    trials = cursor.fetchall()
    conn.close()

    if not trials:
        update.message.reply_text("На данный момент записей на пробные занятия нет.")
        return

    trials_list = []
    for trial in trials:
        trial_info = (
            f"🔖 ID записи: {trial[0]}\n"
            f"👶 Ребенок: {trial[1]}\n"
            f"👤 Родитель: {trial[2]}\n"
            f"📱 Телефон: {trial[3]}\n"
            f"📚 Курс: {trial[4]}\n"
            f"📅 Дата записи: {trial[5].strftime('%d.%m.%Y %H:%M')}\n"
            f"{'=' * 30}"
        )
        trials_list.append(trial_info)

    message = "📋 Записи на пробные занятия:\n\n"
    for trial in trials_list:
        if len(message + trial) > 4096:  # Максимальная длина сообщения в Telegram
            update.message.reply_text(message)
            message = trial
        else:
            message += trial + "\n"

    if message:
        update.message.reply_text(message)

def add_admin_command(update: Update, context: CallbackContext):
    """Добавляет администратора."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return

    try:
        admin_chat_id = int(context.args[0])
        add_admin(admin_chat_id)
        update.message.reply_text(f"Администратор {admin_chat_id} успешно добавлен.")
    except (IndexError, ValueError):
        update.message.reply_text("Использование: /add_admin <chat_id>")

def confirm_trial(update: Update, context: CallbackContext):
    """Подтверждает или отклоняет запись на пробное занятие."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return

    try:
        trial_id = int(context.args[0])
        conn = get_connection()
        cursor = conn.cursor()

        # Получаем информацию о записи
        cursor.execute('''
            SELECT 
                trial_lessons.id,
                users.child_name,
                users.parent_name,
                users.phone,
                courses.name as course_name,
                trial_lessons.date,
                trial_lessons.confirmed
            FROM trial_lessons
            JOIN users ON trial_lessons.user_id = users.id
            JOIN courses ON trial_lessons.course_id = courses.id
            WHERE trial_lessons.id = %s
        ''', (trial_id,))
        trial = cursor.fetchone()
        conn.close()

        if not trial:
            update.message.reply_text("❌ Запись с таким ID не найдена.")
            return

        # Создаем клавиатуру с кнопками подтверждения/отклонения
        keyboard = [
            [
                InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_trial_{trial_id}_yes"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"confirm_trial_{trial_id}_no")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Формируем сообщение с информацией о записи
        message = (
            f"📝 Запись на пробное занятие:\n\n"
            f"👶 Ребенок: {trial[1]}\n"
            f"👤 Родитель: {trial[2]}\n"
            f"📱 Телефон: {trial[3]}\n"
            f"📚 Курс: {trial[4]}\n"
            f"📅 Дата записи: {trial[5].strftime('%d.%m.%Y %H:%M')}\n"
            f"✅ Статус: {'Подтверждено' if trial[6] else 'Не подтверждено'}\n\n"
            f"Выберите действие:"
        )

        update.message.reply_text(message, reply_markup=reply_markup)

    except (IndexError, ValueError):
        update.message.reply_text("Использование: /confirm_trial <ID записи>")

def handle_confirm_trial(update: Update, context: CallbackContext) -> int:
    """Обработчик подтверждения/отклонения записи."""
    query = update.callback_query
    query.answer()

    if not query.data.startswith("confirm_trial_"):
        return ConversationHandler.END

    # Получаем ID записи и действие из callback_data
    _, _, trial_id, action = query.data.split("_")
    trial_id = int(trial_id)

    conn = get_connection()
    cursor = conn.cursor()

    # Обновляем статус записи
    cursor.execute('''
        UPDATE trial_lessons 
        SET confirmed = %s 
        WHERE id = %s
        RETURNING id, 
            (SELECT users.phone FROM users WHERE users.id = trial_lessons.user_id) as phone,
            (SELECT courses.name FROM courses WHERE courses.id = trial_lessons.course_id) as course_name
    ''', (action == "yes", trial_id))

    result = cursor.fetchone()
    conn.commit()
    conn.close()

    if result:
        status = "✅ подтверждена" if action == "yes" else "❌ отклонена"
        query.edit_message_text(f"Запись на пробное занятие {status}.")

        # Здесь можно добавить отправку уведомления пользователю
        if action == "yes":
            notify_admins(context, f"Запись на курс '{result[2]}' подтверждена.\nТелефон для связи: {result[1]}")
    else:
        query.edit_message_text("❌ Ошибка при обновлении записи.")

    return ConversationHandler.END

def get_confirm_trial_handler():
    """Возвращает обработчик подтверждения записи."""
    return CallbackQueryHandler(
        handle_confirm_trial,
        pattern="^confirm_trial_[0-9]+_(yes|no)$"
    )

def filter_trials(update: Update, context: CallbackContext):
    """Фильтрация записей на пробные занятия."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT trial_lessons.id, users.child_name, users.parent_name, users.phone, courses.name, trial_lessons.date, trial_lessons.confirmed
        FROM trial_lessons
        JOIN users ON trial_lessons.user_id = users.id
        JOIN courses ON trial_lessons.course_id = courses.id
        WHERE trial_lessons.confirmed = FALSE
        ORDER BY trial_lessons.date DESC
    ''')
    trials = cursor.fetchall()
    conn.close()

    if not trials:
        update.message.reply_text("На данный момент нет неподтвержденных записей на пробные занятия.")
        return

    trials_list = []
    for trial in trials:
        trial_info = (
            f"🔖 ID записи: {trial[0]}\n"
            f"👶 Ребенок: {trial[1]}\n"
            f"👤 Родитель: {trial[2]}\n"
            f"📱 Телефон: {trial[3]}\n"
            f"📚 Курс: {trial[4]}\n"
            f"📅 Дата записи: {trial[5].strftime('%d.%m.%Y %H:%M')}\n"
            f"{'=' * 30}"
        )
        trials_list.append(trial_info)

    message = "📋 Неподтвержденные записи на пробные занятия:\n\n"
    for trial in trials_list:
        if len(message + trial) > 4096:  # Максимальная длина сообщения в Telegram
            update.message.reply_text(message)
            message = trial
        else:
            message += trial + "\n"

    if message:
        update.message.reply_text(message)

def delete_course(update: Update, context: CallbackContext):
    """Удаляет курс."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return

    try:
        course_id = int(context.args[0])
        conn = get_connection()
        cursor = conn.cursor()

        # Проверяем существование курса
        cursor.execute('SELECT name FROM courses WHERE id = %s', (course_id,))
        course = cursor.fetchone()

        if not course:
            update.message.reply_text("❌ Курс с таким ID не найден.")
            conn.close()
            return

        # Удаляем связанные теги
        cursor.execute('DELETE FROM course_tags WHERE course_id = %s', (course_id,))

        # Удаляем сам курс
        cursor.execute('DELETE FROM courses WHERE id = %s', (course_id,))
        conn.commit()
        conn.close()

        update.message.reply_text(f"✅ Курс '{course[0]}' успешно удален.")
    except (IndexError, ValueError):
        update.message.reply_text("Использование: /delete_course <ID курса>")

def clear_trials(update: Update, context: CallbackContext):
    """Очищает все неподтвержденные записи на пробные занятия."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return

    # Запрашиваем подтверждение
    keyboard = [
        [InlineKeyboardButton("Да ✅", callback_data="clear_trials_confirm")],
        [InlineKeyboardButton("Нет ❌", callback_data="clear_trials_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text(
        "⚠️ Вы уверены, что хотите удалить все неподтвержденные записи на пробные занятия?",
        reply_markup=reply_markup
    )

def handle_clear_trials(update: Update, context: CallbackContext):
    """Обработчик подтверждения очистки записей."""
    query = update.callback_query
    query.answer()

    if query.data == "clear_trials_confirm":
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM trial_lessons WHERE confirmed = FALSE')
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        query.edit_message_text(f"✅ Удалено {deleted_count} неподтвержденных записей.")
    else:
        query.edit_message_text("❌ Операция отменена.")


# Состояния для ConversationHandler редактирования курса
EDIT_COURSE_ID, EDIT_COURSE_NAME, EDIT_COURSE_DESCRIPTION, EDIT_COURSE_MIN_AGE, EDIT_COURSE_MAX_AGE = range(5)

def get_edit_course_handler():
    """Возвращает обработчик для редактирования курса."""
    return ConversationHandler(
        entry_points=[CommandHandler('edit_course', start_edit_course)],
        states={
            EDIT_COURSE_ID: [MessageHandler(Filters.text & ~Filters.command, get_course_id_to_edit)],
            EDIT_COURSE_NAME: [
                CommandHandler('skip', lambda u, c: get_course_name_to_edit(u, c, skip=True)),
                MessageHandler(Filters.text & ~Filters.command, get_course_name_to_edit)
            ],
            EDIT_COURSE_DESCRIPTION: [
                CommandHandler('skip', lambda u, c: get_course_description_to_edit(u, c, skip=True)),
                MessageHandler(Filters.text & ~Filters.command, get_course_description_to_edit)
            ],
            EDIT_COURSE_MIN_AGE: [
                CommandHandler('skip', lambda u, c: get_course_min_age_to_edit(u, c, skip=True)),
                MessageHandler(Filters.text & ~Filters.command, get_course_min_age_to_edit)
            ],
            EDIT_COURSE_MAX_AGE: [
                CommandHandler('skip', lambda u, c: get_course_max_age_to_edit(u, c, skip=True)),
                MessageHandler(Filters.text & ~Filters.command, get_course_max_age_to_edit)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

def start_edit_course(update: Update, context: CallbackContext) -> int:
    """Начинает процесс редактирования курса."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return ConversationHandler.END

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM courses')
    courses = cursor.fetchall()
    conn.close()

    if not courses:
        update.message.reply_text("Нет доступных курсов для редактирования.")
        return ConversationHandler.END

    courses_list = "\n".join([f"ID: {course[0]} - {course[1]}" for course in courses])
    update.message.reply_text(
        f"Доступные курсы:\n\n{courses_list}\n\n"
        "Введите ID курса, который хотите отредактировать:"
    )
    return EDIT_COURSE_ID

def get_course_id_to_edit(update: Update, context: CallbackContext) -> int:
    """Получает ID курса для редактирования."""
    try:
        course_id = int(update.message.text)
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM courses WHERE id = %s', (course_id,))
        course = cursor.fetchone()
        conn.close()

        if not course:
            update.message.reply_text("Курс с таким ID не найден. Попробуйте снова.")
            return EDIT_COURSE_ID

        context.user_data['course_id'] = course_id
        context.user_data['current_course'] = course
        update.message.reply_text(
            f"Текущее название курса: {course[1]}\n"
            "Введите новое название курса (или /skip, чтобы оставить текущее):"
        )
        return EDIT_COURSE_NAME
    except ValueError:
        update.message.reply_text("Пожалуйста, введите число.")
        return EDIT_COURSE_ID

def get_course_name_to_edit(update: Update, context: CallbackContext, skip=False) -> int:
    """Получает новое название курса."""
    if skip:
        current_course = context.user_data['current_course']
        context.user_data['course_name'] = current_course[1]
    else:
        context.user_data['course_name'] = update.message.text

    update.message.reply_text(
        f"Текущее описание курса: {context.user_data['current_course'][2]}\n"
        "Введите новое описание курса (или /skip, чтобы оставить текущее):"
    )
    return EDIT_COURSE_DESCRIPTION

def get_course_description_to_edit(update: Update, context: CallbackContext, skip=False) -> int:
    """Получает новое описание курса."""
    if skip:
        current_course = context.user_data['current_course']
        context.user_data['course_description'] = current_course[2]
    else:
        context.user_data['course_description'] = update.message.text

    update.message.reply_text(
        f"Текущий минимальный возраст: {context.user_data['current_course'][3]}\n"
        "Введите новый минимальный возраст (или /skip, чтобы оставить текущий):"
    )
    return EDIT_COURSE_MIN_AGE

def get_course_min_age_to_edit(update: Update, context: CallbackContext, skip=False) -> int:
    """Получает новый минимальный возраст."""
    if skip:
        current_course = context.user_data['current_course']
        context.user_data['course_min_age'] = current_course[3]
    else:
        try:
            min_age = int(update.message.text)
            if min_age < 0:
                update.message.reply_text("Возраст должен быть положительным числом. Попробуйте снова.")
                return EDIT_COURSE_MIN_AGE
            context.user_data['course_min_age'] = min_age
        except ValueError:
            update.message.reply_text("Пожалуйста, введите число.")
            return EDIT_COURSE_MIN_AGE

    update.message.reply_text(
        f"Текущий максимальный возраст: {context.user_data['current_course'][4]}\n"
        "Введите новый максимальный возраст (или /skip, чтобы оставить текущий):"
    )
    return EDIT_COURSE_MAX_AGE

def get_course_max_age_to_edit(update: Update, context: CallbackContext, skip=False) -> int:
    """Получает новый максимальный возраст и сохраняет изменения."""
    if skip:
        current_course = context.user_data['current_course']
        context.user_data['course_max_age'] = current_course[4]
    else:
        try:
            max_age = int(update.message.text)
            if max_age <= context.user_data.get('course_min_age', 0):
                update.message.reply_text("Максимальный возраст должен быть больше минимального. Попробуйте снова.")
                return EDIT_COURSE_MAX_AGE
            context.user_data['course_max_age'] = max_age
        except ValueError:
            update.message.reply_text("Пожалуйста, введите число.")
            return EDIT_COURSE_MAX_AGE

    # Сохраняем изменения в базе данных
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE courses 
        SET name = %s, description = %s, min_age = %s, max_age =%s 
        WHERE id = %s
    ''', (
        context.user_data['course_name'],
        context.user_data['course_description'],
        context.user_data['course_min_age'],
        context.user_data['course_max_age'],
        context.user_data['course_id']
    ))
    conn.commit()
    conn.close()

    update.message.reply_text(f"✅ Курс успешно обновлен!")
    clear_user_data(context)
    return ConversationHandler.END

def edit_course(update:Update, context:CallbackContext):
    pass

def create_course(update:Update, context:CallbackContext):
    pass

def add_location(update: Update, context: CallbackContext):
    """Добавляет новый район и адрес."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return

    try:
        # Ожидаем формат: /add_location "Район" "Адрес"
        text = " ".join(context.args)
        district, address = text.split('"')[1::2]  # Разделяем по кавычкам

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO locations (district, address) VALUES (%s, %s) RETURNING id',
            (district, address)
        )
        location_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()

        update.message.reply_text(
            f"✅ Добавлен новый адрес:\n"
            f"ID: {location_id}\n"
            f"Район: {district}\n"
            f"Адрес: {address}"
        )
    except (IndexError, ValueError):
        update.message.reply_text(
            'Использование: /add_location "Название района" "Полный адрес"\n'
            'Пример: /add_location "Центральный" "ул. Ленина, 1"'
        )

def list_locations(update: Update, context: CallbackContext):
    """Показывает список всех районов и адресов."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, district, address FROM locations ORDER BY district')
    locations = cursor.fetchall()
    conn.close()

    if not locations:
        update.message.reply_text("📍 Адреса еще не добавлены.")
        return

    message = "📍 Список районов и адресов:\n\n"
    current_district = None

    for loc in locations:
        if loc[1] != current_district:
            current_district = loc[1]
            message += f"\n🏢 {current_district}:\n"
        message += f"  • {loc[2]} (ID: {loc[0]})\n"

    update.message.reply_text(message)

def delete_location(update: Update, context: CallbackContext):
    """Удаляет район и адрес."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return

    try:
        location_id = int(context.args[0])
        conn = get_connection()
        cursor = conn.cursor()

        # Проверяем существование адреса
        cursor.execute('SELECT district, address FROM locations WHERE id = %s', (location_id,))
        location = cursor.fetchone()

        if not location:
            update.message.reply_text("❌ Адрес с таким ID не найден.")
            conn.close()
            return

        # Удаляем адрес
        cursor.execute('DELETE FROM locations WHERE id = %s', (location_id,))
        conn.commit()
        conn.close()

        update.message.reply_text(
            f"✅ Удален адрес:\n"
            f"Район: {location[0]}\n"
            f"Адрес: {location[1]}"
        )
    except (IndexError, ValueError):
        update.message.reply_text("Использование: /delete_location <ID адреса>")

def handle_clear_trials(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()

    if query.data== "clear_trials_confirm":
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM trial_lessons WHERE confirmed = FALSE')
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        query.edit_message_text(f"✅ Удалено {deleted_count} неподтвержденных записей.")
    else:
        query.edit_message_text("❌ Операция отменена.")

def get_clear_trials_handler():
    return CallbackQueryHandler(handle_clear_trials, pattern="^clear_trials_confirm$|^clear_trials_cancel$")

def get_all_handlers():
    return [
        get_conversation_handler(),
        CommandHandler('help', help_command),
        CommandHandler('courses', list_courses),
        CommandHandler('about', about),
        CommandHandler('view_trials', view_trials),
        CommandHandler('add_admin', add_admin_command),
        CommandHandler('delete_course', delete_course),
        CommandHandler('clear_trials', clear_trials),
        get_clear_trials_handler(),
        get_edit_course_handler(),
        CommandHandler('add_location', add_location),
        CommandHandler('list_locations', list_locations),
        CommandHandler('delete_location', delete_location),
        CommandHandler('confirm_trial', confirm_trial),
        get_confirm_trial_handler(),
        CommandHandler('filter_trials', filter_trials)
    ]