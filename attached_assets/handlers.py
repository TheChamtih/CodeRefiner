# handlers.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler, CommandHandler, MessageHandler, Filters, CallbackQueryHandler
from database import init_db, get_admin_ids, add_admin
from config import MAIN_ADMIN_ID
import re
from datetime import datetime
import sqlite3

# Состояния для ConversationHandler
NAME, AGE, INTERESTS, PARENT_NAME, PHONE, COURSE_SELECTION, CONFIRMATION = range(7)

# Добавьте эти состояния в handlers.py
COURSE_NAME, COURSE_DESCRIPTION, COURSE_MIN_AGE, COURSE_MAX_AGE = range(4)

# Состояния для ConversationHandler
EDIT_COURSE_ID, EDIT_COURSE_NAME, EDIT_COURSE_DESCRIPTION, EDIT_COURSE_MIN_AGE, EDIT_COURSE_MAX_AGE = range(5)

# Проверка номера телефона
def is_valid_phone(phone: str) -> bool:
    """Проверяет, начинается ли номер на +7 или 8."""
    return re.match(r'^(\+7|8)[\s\-]?(\d{3})[\s\-]?(\d{3})[\s\-]?(\d{2})[\s\-]?(\d{2})$', phone)  is not None

# Уведомление администраторов
def notify_admins(context: CallbackContext, message: str):
    """Отправляет уведомление всем администраторам."""
    admins = get_admin_ids()
    for admin in admins:
        context.bot.send_message(chat_id=admin, text=message)

# Очистка данных пользователя
def clear_user_data(context: CallbackContext):
    """Очищает данные пользователя."""
    context.user_data.clear()

# Обработчик команды /start
def start(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("Привет! Давайте подберем курс для вашего ребенка. Как зовут вашего ребенка?")
    return NAME

# Обработчик для получения имени ребенка
def get_name(update: Update, context: CallbackContext) -> int:
    user_name = update.message.text
    context.user_data['child_name'] = user_name
    update.message.reply_text(f"Отлично, {user_name}! Сколько лет вашему ребенку?")
    return AGE

# Обработчик для получения возраста ребенка
def get_age(update: Update, context: CallbackContext) -> int:
    user_age = update.message.text
    try:
        user_age = int(user_age)
        if user_age < 6 or user_age > 18:
            update.message.reply_text("Возраст должен быть от 6 до 18 лет. Пожалуйста, введите корректный возраст.")
            return AGE
    except ValueError:
        update.message.reply_text("Пожалуйста, введите число.")
        return AGE

    context.user_data['child_age'] = user_age
    update.message.reply_text("Чем увлекается ваш ребенок? (например, программирование, дизайн, математика и т.д.)")
    return INTERESTS

# Обработчик для получения интересов ребенка
def get_interests(update: Update, context: CallbackContext) -> int:
    user_interests = update.message.text
    context.user_data['child_interests'] = user_interests
    update.message.reply_text("Как вас зовут? (Имя родителя)")
    return PARENT_NAME

# Обработчик для получения имени родителя
def get_parent_name(update: Update, context: CallbackContext) -> int:
    parent_name = update.message.text
    context.user_data['parent_name'] = parent_name
    update.message.reply_text("Укажите ваш номер телефона для связи (начинается на +7 или 8):")
    return PHONE

# Обработчик для получения номера телефона
SYNONYMS = {
    "программирование": ["кодирование", "разработка", "программировать", "код", "алгоритмы", "python", "javascript"],
    "дизайн": ["графика", "рисование", "креатив", "арт", "иллюстрация", "фотошоп", "веб-дизайн"],
    "математика": ["алгебра", "геометрия", "математик", "цифры", "логика", "уравнения", "статистика"],
    "робототехника": ["роботы", "робот", "механика", "электроника", "автоматизация", "arduino", "микроконтроллеры"],
    "блогинг": ["видео", "ютуб", "контент", "медиа", "соцсети", "видеомонтаж", "продвижение"],
    "игры": ["геймдизайн", "игростроение", "игровая индустрия", "игровые миры", "unity", "unreal engine"],
    "предпринимательство": ["бизнес", "стартап", "финансы", "маркетинг", "управление", "экономика", "продажи"],
}

def get_synonyms(keyword):
    """Возвращает список синонимов для ключевого слова."""
    return SYNONYMS.get(keyword, []) + [keyword]

def get_phone(update: Update, context: CallbackContext) -> int:
    phone = update.message.text

    if not is_valid_phone(phone):
        update.message.reply_text("Номер телефона должен начинаться на +7 или 8. Пожалуйста, введите корректный номер.")
        return PHONE

    context.user_data['phone'] = phone

    # Подбираем курсы на основе интересов и возраста
    child_age = context.user_data['child_age']
    child_interests = context.user_data['child_interests'].lower()

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM courses')
    all_courses = cursor.fetchall()
    conn.close()

    # Фильтруем курсы по возрасту (включая случаи, когда возраст равен максимальному)
    age_appropriate_courses = [course for course in all_courses if course[3] <= child_age <= course[4]]

    # Фильтруем курсы по интересам
    recommended_courses = []
    for course in age_appropriate_courses:
        course_name = course[1].lower()
        course_description = course[2].lower()

        # Проверяем, есть ли ключевые слова из интересов или их синонимы в названии или описании курса
        for keyword in child_interests.split():
            synonyms = get_synonyms(keyword)
            if any(synonym in course_name or synonym in course_description for synonym in synonyms):
                recommended_courses.append(course)
                break  # Если курс подходит по одному из ключевых слов, добавляем его и переходим к следующему курсу

    # Если есть курсы по интересам, показываем их
    if recommended_courses:
        update.message.reply_text("Вот курсы, которые подходят по интересам вашего ребенка:")
        keyboard = [
            [InlineKeyboardButton(course[1], callback_data=f"course_{course[0]}")]
            for course in recommended_courses
        ]
        # Добавляем кнопку "Выбрать курс самостоятельно"
        keyboard.append([InlineKeyboardButton("Выбрать курс самостоятельно", callback_data="choose_manually")])
    else:
        # Если нет курсов по интересам, показываем все курсы, подходящие по возрасту
        update.message.reply_text("К сожалению, для ваших интересов нет подходящих курсов. Вот все курсы, доступные для вашего возраста:")
        keyboard = [
            [InlineKeyboardButton(course[1], callback_data=f"course_{course[0]}")]
            for course in age_appropriate_courses
        ]

    keyboard.append([InlineKeyboardButton("❌ Выйти", callback_data="exit")])  # Кнопка для выхода
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text("Выберите курс, который вам интересен:", reply_markup=reply_markup)
    return COURSE_SELECTION

# Обработчик для подтверждения записи
# Уведомление администраторов
def notify_admins(context: CallbackContext, message: str):
    """Отправляет уведомление всем администраторам."""
    admins = get_admin_ids()
    for admin in admins:
        context.bot.send_message(chat_id=admin, text=message)

# Обработчик подтверждения записи
def confirm_signup(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()

    if query.data == "exit":
        query.edit_message_text("Диалог завершен. Если хотите начать заново, напишите /start.")
        clear_user_data(context)  # Очищаем данные
        return ConversationHandler.END

    if query.data == "confirm_yes":
        # Сохраняем данные пользователя в базу данных
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (chat_id, parent_name, phone, child_name, child_age, child_interests)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            query.message.chat_id,
            context.user_data['parent_name'],
            context.user_data['phone'],
            context.user_data['child_name'],
            context.user_data['child_age'],
            context.user_data['child_interests']
        ))
        user_id = cursor.lastrowid

        # Сохраняем выбранный курс
        course_id = context.user_data['selected_course']
        cursor.execute('SELECT name, description, min_age, max_age FROM courses WHERE id = ?', (course_id,))
        course = cursor.fetchone()
        course_name = course[0]
        course_description = course[1]
        course_min_age = course[2]
        course_max_age = course[3]

        cursor.execute('''
            INSERT INTO trial_lessons (user_id, course_id, date, confirmed)
            VALUES (?, ?, ?, FALSE)
        ''', (user_id, course_id, datetime.now().strftime("%Y-%m-%d")))

        conn.commit()
        conn.close()

        # Уведомление администраторов
        message = (
            f"Новая запись на пробное занятие:\n\n"
            f"Родитель: {context.user_data['parent_name']}\n"
            f"Телефон: {context.user_data['phone']}\n"
            f"Ребенок: {context.user_data['child_name']} ({context.user_data['child_age']} лет)\n"
            f"Интересы: {context.user_data['child_interests']}\n"
            f"Выбранный курс: {course_name}\n"
            f"Описание курса: {course_description}\n"
            f"Возрастные ограничения курса: {course_min_age}-{course_max_age} лет\n"
            f"Дата записи: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        )
        notify_admins(context, message)

        query.edit_message_text("Спасибо! Мы свяжемся с вами для уточнения деталей.")
    else:
        query.edit_message_text("Хорошо, если передумаете, всегда можете вернуться и записаться позже.")

    clear_user_data(context)  # Очищаем данные
    return ConversationHandler.END

# Обработчик для отмены диалога
def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("Диалог прерван. Если хотите начать заново, напишите /start.")
    clear_user_data(context)  # Очищаем данные
    return ConversationHandler.END

# Обработчик команды /add_admin
def add_admin_command(update: Update, context: CallbackContext):
    """Добавляет администратора."""
    if update.message.chat_id != MAIN_ADMIN_ID:
        update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return

    try:
        admin_chat_id = int(context.args[0])
        add_admin(admin_chat_id)
        update.message.reply_text(f"Администратор {admin_chat_id} успешно добавлен.")
    except (IndexError, ValueError):
        update.message.reply_text("Использование: /add_admin <chat_id>")

def select_course(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()

    if query.data == "exit":
        query.edit_message_text("Диалог завершен. Если хотите начать заново, напишите /start.")
        clear_user_data(context)  # Очищаем данные
        return ConversationHandler.END

    if query.data == "choose_manually":
        # Показываем все курсы, доступные для возраста пользователя
        child_age = context.user_data['child_age']
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM courses WHERE min_age <= ? AND max_age >= ?', (child_age, child_age))
        age_appropriate_courses = cursor.fetchall()
        conn.close()

        if not age_appropriate_courses:
            query.edit_message_text("К сожалению, для вашего возраста нет доступных курсов.")
            return ConversationHandler.END

        keyboard = [
            [InlineKeyboardButton(course[1], callback_data=f"course_{course[0]}")]
            for course in age_appropriate_courses
        ]
        keyboard.append([InlineKeyboardButton("❌ Выйти", callback_data="exit")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        query.edit_message_text("Вот все курсы, доступные для вашего возраста:", reply_markup=reply_markup)
        return COURSE_SELECTION

    # Обработка выбора курса
    course_id = int(query.data.split("_")[1])
    context.user_data['selected_course'] = course_id

    # Получаем информацию о выбранном курсе
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name, description FROM courses WHERE id = ?', (course_id,))
    course = cursor.fetchone()
    conn.close()

    # Показываем информацию о курсе и запрашиваем подтверждение
    query.edit_message_text(text=f"Вы выбрали курс:\n\n{course[0]}: {course[1]}\n\nХотите записаться на пробное занятие?",
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("Да", callback_data="confirm_yes")],
                                [InlineKeyboardButton("Нет", callback_data="confirm_no")],
                                [InlineKeyboardButton("❌ Выйти", callback_data="exit")]
                            ]))
    return CONFIRMATION

# Создание ConversationHandler
def get_conversation_handler():
    return ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            NAME: [MessageHandler(Filters.text & ~Filters.command, get_name)],
            AGE: [MessageHandler(Filters.text & ~Filters.command, get_age)],
            INTERESTS: [MessageHandler(Filters.text & ~Filters.command, get_interests)],
            PARENT_NAME: [MessageHandler(Filters.text & ~Filters.command, get_parent_name)],
            PHONE: [MessageHandler(Filters.text & ~Filters.command, get_phone)],
            COURSE_SELECTION: [CallbackQueryHandler(select_course, pattern="^course_|^choose_manually$|^exit$")],  # Добавлен choose_manually
            CONFIRMATION: [CallbackQueryHandler(confirm_signup, pattern="^(confirm_yes|confirm_no|exit)$")],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

def list_courses(update: Update, context: CallbackContext):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM courses')
    courses = cursor.fetchall()
    conn.close()

    if not courses:
        update.message.reply_text("На данный момент курсов нет.")
        return

    courses_list = "\n".join([f"{course[1]} (возраст: {course[3]}-{course[4]} лет)" for course in courses])
    update.message.reply_text(f"Доступные курсы:\n\n{courses_list}")

def view_trials(update: Update, context: CallbackContext):
    """Показывает все записи на пробные занятия с информацией о пользователях."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT trial_lessons.id, users.child_name, users.parent_name, users.phone, courses.name, trial_lessons.date, trial_lessons.confirmed
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
            f"ID записи: {trial[0]}\n"
            f"Ребенок: {trial[1]}\n"
            f"Родитель: {trial[2]}\n"
            f"Телефон: {trial[3]}\n"
            f"Курс: {trial[4]}\n"
            f"Дата записи: {trial[5]}\n"
            f"Подтверждено: {'✅' if trial[6] else '❌'}\n"
        )
        trials_list.append(trial_info)

    update.message.reply_text("Записи на пробные занятия:\n\n" + "\n".join(trials_list))

def filter_trials(update: Update, context: CallbackContext):
    """Фильтрация записей на пробные занятия."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT trial_lessons.id, users.child_name, users.parent_name, users.phone, courses.name, trial_lessons.date, trial_lessons.confirmed
        FROM trial_lessons
        JOIN users ON trial_lessons.user_id = users.id
        JOIN courses ON trial_lessons.course_id = courses.id
        WHERE trial_lessons.confirmed = ?
    ''', (False,))
    trials = cursor.fetchall()
    conn.close()

    if not trials:
        update.message.reply_text("На данный момент нет неподтвержденных записей на пробные занятия.")
        return

    trials_list = []
    for trial in trials:
        trial_info = (
            f"ID записи: {trial[0]}\n"
            f"Ребенок: {trial[1]}\n"
            f"Родитель: {trial[2]}\n"
            f"Телефон: {trial[3]}\n"
            f"Курс: {trial[4]}\n"
            f"Дата записи: {trial[5]}\n"
            f"Подтверждено: {'✅' if trial[6] else '❌'}\n"
        )
        trials_list.append(trial_info)

    update.message.reply_text("Неподтвержденные записи на пробные занятия:\n\n" + "\n".join(trials_list))

def confirm_trial(update: Update, context: CallbackContext):
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return

    try:
        trial_id = int(context.args[0])
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM trial_lessons WHERE id = ?', (trial_id,))
        trial = cursor.fetchone()
        conn.close()

        if not trial:
            update.message.reply_text("Запись с таким ID не найдена.")
            return

        keyboard = [
            [InlineKeyboardButton("Подтвердить", callback_data=f"confirm_trial_{trial_id}_yes")],
            [InlineKeyboardButton("Отменить", callback_data=f"confirm_trial_{trial_id}_no")],
            [InlineKeyboardButton("❌ Выйти", callback_data="exit")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        update.message.reply_text(
            f"Запись на пробное занятие:\n\n"
            f"ID записи: {trial[0]}\n"
            f"Ребенок: {trial[1]}\n"
            f"Родитель: {trial[2]}\n"
            f"Телефон: {trial[3]}\n"
            f"Курс: {trial[4]}\n"
            f"Дата записи: {trial[5]}\n"
            f"Подтверждено: {'✅' if trial[6] else '❌'}",
            reply_markup=reply_markup
        )
    except (IndexError, ValueError):
        update.message.reply_text("Использование: /confirm_trial <ID>")
def handle_confirm_trial(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()

    if query.data == "exit":
        query.edit_message_text("Диалог завершен. Если хотите начать заново, напишите /start.")
        return ConversationHandler.END

    data_parts = query.data.split("_")
    trial_id = int(data_parts[2])
    action = data_parts[3]

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    if action == "yes":
        cursor.execute('UPDATE trial_lessons SET confirmed = TRUE WHERE id = ?', (trial_id,))
        query.edit_message_text(f"Запись на пробное занятие с ID {trial_id} подтверждена.")
    elif action == "no":
        cursor.execute('UPDATE trial_lessons SET confirmed = FALSE WHERE id = ?', (trial_id,))
        query.edit_message_text(f"Подтверждение записи на пробное занятие с ID {trial_id} отменено.")
    conn.commit()
    conn.close()

    return ConversationHandler.END

def get_confirm_trial_handler():
    return ConversationHandler(
        entry_points=[CommandHandler('confirm_trial', confirm_trial)],
        states={
            0: [CallbackQueryHandler(handle_confirm_trial, pattern=r"^confirm_trial_\d+_(yes|no)$|^exit$")],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

def help_command(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    admins = get_admin_ids()

    help_text = """
    Список доступных команд:

    Для пользователей:
    /start - Начать диалог для подбора курса.
    /courses - Показать список всех доступных курсов.
    /help - Показать список всех команд.
    /about - Информация о школе Алгоритмика.
    """

    if user_id in admins:
        help_text += """
        Для администраторов:
        /add_admin - Добавить нового администратора.
        /delete_course - Удалить курс.
        /edit_course - Редактировать курс.
        /view_trials - Показать все записи на пробные занятия.
        /filter_trials - Показать неподтвержденные записи на пробные занятия.
        /clear_trials - Очистить все записи на пробные занятия.
        /confirm_trial - Подтвердить запись на пробное занятие.
        /create_course - Создать новый курс.
        """

    update.message.reply_text(help_text)

def delete_course(update: Update, context: CallbackContext):
    if update.message.chat_id != MAIN_ADMIN_ID:
        update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return

    try:
        course_id = int(context.args[0])
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM courses WHERE id = ?', (course_id,))
        conn.commit()
        conn.close()
        update.message.reply_text(f"Курс с ID {course_id} успешно удален.")
    except (IndexError, ValueError):
        update.message.reply_text("Использование: /delete_course <course_id>")

# Создание курса.
def start_create_course(update: Update, context: CallbackContext) -> int:
    """Начинает процесс создания курса."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return ConversationHandler.END

    update.message.reply_text("Введите название курса:")
    return COURSE_NAME

def get_course_name(update: Update, context: CallbackContext) -> int:
    """Получает название курса."""
    context.user_data['course_name'] = update.message.text
    update.message.reply_text("Введите описание курса:")
    return COURSE_DESCRIPTION

def get_course_description(update: Update, context: CallbackContext) -> int:
    """Получает описание курса."""
    context.user_data['course_description'] = update.message.text
    update.message.reply_text("Введите минимальный возраст для курса:")
    return COURSE_MIN_AGE

def get_course_min_age(update: Update, context: CallbackContext) -> int:
    """Получает минимальный возраст для курса."""
    try:
        min_age = int(update.message.text)
        if min_age < 0:
            update.message.reply_text("Возраст должен быть положительным числом. Попробуйте снова.")
            return COURSE_MIN_AGE
        context.user_data['course_min_age'] = min_age
        update.message.reply_text("Введите максимальный возраст для курса:")
        return COURSE_MAX_AGE
    except ValueError:
        update.message.reply_text("Пожалуйста, введите число.")
        return COURSE_MIN_AGE

def get_course_max_age(update: Update, context: CallbackContext) -> int:
    """Получает максимальный возраст для курса."""
    try:
        max_age = int(update.message.text)
        if max_age <= context.user_data['course_min_age']:
            update.message.reply_text("Максимальный возраст должен быть больше минимального. Попробуйте снова.")
            return COURSE_MAX_AGE
        context.user_data['course_max_age'] = max_age

        # Сохраняем курс в базу данных
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO courses (name, description, min_age, max_age)
            VALUES (?, ?, ?, ?)
        ''', (
            context.user_data['course_name'],
            context.user_data['course_description'],
            context.user_data['course_min_age'],
            context.user_data['course_max_age']
        ))
        conn.commit()
        conn.close()

        update.message.reply_text(f"Курс '{context.user_data['course_name']}' успешно создан!")
        clear_user_data(context)  # Очищаем данные
        return ConversationHandler.END
    except ValueError:
        update.message.reply_text("Пожалуйста, введите число.")
        return COURSE_MAX_AGE

def cancel_create_course(update: Update, context: CallbackContext) -> int:
    """Отменяет процесс создания курса."""
    update.message.reply_text("Создание курса отменено.")
    clear_user_data(context)  # Очищаем данные
    return ConversationHandler.END

def get_create_course_handler():
    return ConversationHandler(
        entry_points=[CommandHandler('create_course', start_create_course)],
        states={
            COURSE_NAME: [MessageHandler(Filters.text & ~Filters.command, get_course_name)],
            COURSE_DESCRIPTION: [MessageHandler(Filters.text & ~Filters.command, get_course_description)],
            COURSE_MIN_AGE: [MessageHandler(Filters.text & ~Filters.command, get_course_min_age)],
            COURSE_MAX_AGE: [MessageHandler(Filters.text & ~Filters.command, get_course_max_age)],
        },
        fallbacks=[CommandHandler('cancel', cancel_create_course)],
    )

# Редактирование курса.

def start_edit_course(update: Update, context: CallbackContext) -> int:
    """Начинает процесс редактирования курса."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return ConversationHandler.END

    update.message.reply_text("Введите ID курса, который хотите отредактировать:")
    return EDIT_COURSE_ID

def get_course_id_to_edit(update: Update, context: CallbackContext) -> int:
    """Получает ID курса для редактирования."""
    try:
        course_id = int(update.message.text)
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM courses WHERE id = ?', (course_id,))
        course = cursor.fetchone()
        conn.close()

        if not course:
            update.message.reply_text("Курс с таким ID не найден. Попробуйте снова.")
            return EDIT_COURSE_ID

        context.user_data['course_id'] = course_id
        context.user_data['current_course'] = course  # Сохраняем текущие данные курса
        update.message.reply_text(f"Текущее название курса: {course[1]}\nВведите новое название курса (или нажмите /skip, чтобы оставить текущее):")
        return EDIT_COURSE_NAME
    except ValueError:
        update.message.reply_text("Пожалуйста, введите число.")
        return EDIT_COURSE_ID

def get_course_name_to_edit(update: Update, context: CallbackContext) -> int:
    """Получает новое название курса."""
    if update.message.text == "/skip":
        update.message.reply_text("Название курса осталось без изменений.")
        current_course = context.user_data['current_course']
        context.user_data['course_name'] = current_course[1]  # Оставляем текущее название
        # Переходим к следующему этапу
        update.message.reply_text(f"Текущее описание курса: {current_course[2]}\nВведите новое описание курса (или нажмите /skip, чтобы оставить текущее):")
        return EDIT_COURSE_DESCRIPTION
    else:
        context.user_data['course_name'] = update.message.text
        update.message.reply_text(f"Текущее описание курса: {context.user_data['current_course'][2]}\nВведите новое описание курса (или нажмите /skip, чтобы оставить текущее):")
        return EDIT_COURSE_DESCRIPTION

def get_course_description_to_edit(update: Update, context: CallbackContext) -> int:
    """Получает новое описание курса."""
    if update.message.text == "/skip":
        update.message.reply_text("Описание курса осталось без изменений.")
        current_course = context.user_data['current_course']
        context.user_data['course_description'] = current_course[2]  # Оставляем текущее описание
        # Переходим к следующему этапу
        update.message.reply_text(f"Текущий минимальный возраст: {current_course[3]}\nВведите новый минимальный возраст для курса (или нажмите /skip, чтобы оставить текущий):")
        return EDIT_COURSE_MIN_AGE
    else:
        context.user_data['course_description'] = update.message.text
        update.message.reply_text(f"Текущий минимальный возраст: {context.user_data['current_course'][3]}\nВведите новый минимальный возраст для курса (или нажмите /skip, чтобы оставить текущий):")
        return EDIT_COURSE_MIN_AGE

def get_course_min_age_to_edit(update: Update, context: CallbackContext) -> int:
    """Получает новый минимальный возраст для курса."""
    if update.message.text == "/skip":
        update.message.reply_text("Минимальный возраст остался без изменений.")
        current_course = context.user_data['current_course']
        context.user_data['course_min_age'] = current_course[3]  # Оставляем текущий минимальный возраст
        # Переходим к следующему этапу
        update.message.reply_text(f"Текущий максимальный возраст: {current_course[4]}\nВведите новый максимальный возраст для курса (или нажмите /skip, чтобы оставить текущий):")
        return EDIT_COURSE_MAX_AGE
    else:
        try:
            min_age = int(update.message.text)
            if min_age < 0:
                update.message.reply_text("Возраст должен быть положительным числом. Попробуйте снова.")
                return EDIT_COURSE_MIN_AGE
            context.user_data['course_min_age'] = min_age
            update.message.reply_text(f"Текущий максимальный возраст: {context.user_data['current_course'][4]}\nВведите новый максимальный возраст для курса (или нажмите /skip, чтобы оставить текущий):")
            return EDIT_COURSE_MAX_AGE
        except ValueError:
            update.message.reply_text("Пожалуйста, введите число.")
            return EDIT_COURSE_MIN_AGE

def get_course_max_age_to_edit(update: Update, context: CallbackContext) -> int:
    """Получает новый максимальный возраст для курса."""
    if update.message.text == "/skip":
        update.message.reply_text("Максимальный возраст остался без изменений.")
        current_course = context.user_data['current_course']
        context.user_data['course_max_age'] = current_course[4]  # Оставляем текущий максимальный возраст
    else:
        try:
            max_age = int(update.message.text)
            if max_age <= context.user_data.get('course_min_age', current_course[3]):
                update.message.reply_text("Максимальный возраст должен быть больше минимального. Попробуйте снова.")
                return EDIT_COURSE_MAX_AGE
            context.user_data['course_max_age'] = max_age
        except ValueError:
            update.message.reply_text("Пожалуйста, введите число.")
            return EDIT_COURSE_MAX_AGE

    # Обновляем курс в базе данных
    course_id = context.user_data['course_id']
    current_course = context.user_data['current_course']
    course_name = context.user_data.get('course_name', current_course[1])
    course_description = context.user_data.get('course_description', current_course[2])
    course_min_age = context.user_data.get('course_min_age', current_course[3])
    course_max_age = context.user_data.get('course_max_age', current_course[4])

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Обновляем курс
    cursor.execute('''
        UPDATE courses
        SET name = ?, description = ?, min_age = ?, max_age = ?
        WHERE id = ?
    ''', (course_name, course_description, course_min_age, course_max_age, course_id))

    conn.commit()
    conn.close()

    update.message.reply_text(f"Курс с ID {course_id} успешно обновлен!")
    clear_user_data(context)  # Очищаем данные
    return ConversationHandler.END

def cancel_edit_course(update: Update, context: CallbackContext) -> int:
    """Отменяет процесс редактирования курса."""
    update.message.reply_text("Редактирование курса отменено.")
    clear_user_data(context)  # Очищаем данные
    return ConversationHandler.END

def clear_user_data(context: CallbackContext):
    """Очищает данные пользователя."""
    context.user_data.clear()

def get_edit_course_handler():
    """Возвращает ConversationHandler для редактирования курса."""
    return ConversationHandler(
        entry_points=[CommandHandler('edit_course', start_edit_course)],
        states={
            EDIT_COURSE_ID: [MessageHandler(Filters.text & ~Filters.command, get_course_id_to_edit)],
            EDIT_COURSE_NAME: [MessageHandler(Filters.text | Filters.command, get_course_name_to_edit)],  # Разрешаем команду /skip
            EDIT_COURSE_DESCRIPTION: [MessageHandler(Filters.text | Filters.command, get_course_description_to_edit)],  # Разрешаем команду /skip
            EDIT_COURSE_MIN_AGE: [MessageHandler(Filters.text | Filters.command, get_course_min_age_to_edit)],  # Разрешаем команду /skip
            EDIT_COURSE_MAX_AGE: [MessageHandler(Filters.text | Filters.command, get_course_max_age_to_edit)],  # Разрешаем команду /skip
        },
        fallbacks=[CommandHandler('cancel', cancel_edit_course)],
    )

#Удаление записи
def clear_trials(update: Update, context: CallbackContext):
    """Очищает все записи на пробные занятия."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM trial_lessons')
    conn.commit()
    conn.close()

    update.message.reply_text("Все записи на пробные занятия успешно удалены.")

def about(update: Update, context: CallbackContext):
    """Выводит информацию о школе 'Алгоритмика'."""
    about_text = """
    🏫 **Алгоритмика** — международная школа программирования и математики для детей 7-17 лет.

    Мы помогаем детям освоить навыки будущего:
    - Программирование на Python, JavaScript и других языках.
    - Разработка игр и приложений.
    - Основы математики и логики.
    - Создание веб-сайтов и мобильных приложений.
    - Изучение искусственного интеллекта и анализа данных.

    📞 **Контактные данные:**
    - Телефон: [8 (800) 555-35-35](tel:+78005553535)
    - Email: [info@algoritmika.org](mailto:info@algoritmika.org)
    - Веб-сайт: [algoritmika.org](https://algoritmika.org)
    - Адрес: Москва, ул. Ленина, д. 42 (главный офис)

    📍 **Мы работаем в более чем 20 странах мира!**

    При соединяйтесь к нам и откройте для вашего ребёнка мир программирования и математики!
    """

    update.message.reply_text(about_text, parse_mode="Markdown")