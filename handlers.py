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

# Global constants
MIN_AGE = 6
MAX_AGE = 18


def is_valid_phone(phone: str) -> bool:
    """Проверяет, начинается ли номер на +7 или 8."""
    return re.match(
        r'^(\+7|8)[\s\-]?(\d{3})[\s\-]?(\d{3})[\s\-]?(\d{2})[\s\-]?(\d{2})$',
        phone) is not None


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
    if context and hasattr(context, 'user_data'):
        context.user_data.clear()


def get_connection():
    """Gets a connection to the PostgreSQL database."""
    return psycopg2.connect(os.environ['DATABASE_URL'],
                            cursor_factory=DictCursor)


def add_course_tags(cursor, course_id: int, tags: list):
    """Добавляет или обновляет теги для курса."""
    # Сначала удаляем существующие теги
    cursor.execute('DELETE FROM course_tags WHERE course_id = %s',
                   (course_id, ))

    # Добавляем новые теги
    for tag in tags:
        cursor.execute(
            'INSERT INTO course_tags (course_id, tag) VALUES (%s, %s)',
            (course_id, tag.lower().strip()))


def update_course_recommendations():
    """Обновляет теги для всех курсов."""
    conn = get_connection()
    cursor = conn.cursor()

    # Предопределенные теги для каждого типа курса
    course_tags = {
        'python':
        ['программирование', 'python', 'coding', 'алгоритмы', 'разработка'],
        'игры':
        ['программирование', 'игры', 'unity', 'геймдев', 'разработка игр'],
        'робототехника': [
            'робототехника', 'arduino', 'электроника', 'схемы',
            'конструирование'
        ],
        'дизайн': ['дизайн', 'графика', 'art', 'creative', 'photoshop'],
        'математика':
        ['математика', 'алгебра', 'логика', 'геометрия', 'числа'],
        'блогинг': ['блогинг', 'медиа', 'контент', 'youtube', 'соцсети']
    }

    # Получаем все курсы
    cursor.execute('SELECT id, name, description FROM courses')
    courses = cursor.fetchall()

    for course in courses:
        course_name = course[1].lower()
        # Определяем подходящие теги на основе названия и описания курса
        selected_tags = set()
        for key, tags in course_tags.items():
            if key in course_name or (course[2] and key in course[2].lower()):
                selected_tags.update(tags)

        if selected_tags:
            add_course_tags(cursor, course[0], list(selected_tags))

    conn.commit()
    conn.close()


def calculate_course_score(user_age: int, user_interests: str,
                           course: Dict) -> float:
    """Вычисляет релевантность курса для пользователя."""
    score = 1.0

    # Возрастной скоринг
    age_range = course['max_age'] - course['min_age']
    age_center = (course['min_age'] + course['max_age']) / 2
    age_distance = abs(user_age - age_center)
    # Нормализуем расстояние относительно диапазона возраста
    normalized_distance = age_distance / (age_range if age_range > 0 else 1)
    age_score = 1.0 / (1 + normalized_distance)
    score *= age_score

    # Скоринг по интересам
    user_interests_list = set(user_interests.lower().split())
    course_tags = set(
        course['tags'].lower().split(', ')) if 'tags' in course else set()

    # Считаем совпадения с тегами
    matching_tags = user_interests_list.intersection(course_tags)
    interest_score = 1.0 + (len(matching_tags) * 0.5)

    # Добавляем бонус за точные совпадения в названии курса
    course_name_words = set(course['name'].lower().split())
    exact_matches = user_interests_list.intersection(course_name_words)
    interest_score += len(exact_matches) * 0.3

    score *= interest_score

    return score


def get_course_tags(course_id: int) -> List[str]:
    """Получает теги курса из базы данных."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT tag FROM course_tags WHERE course_id = %s',
                   (course_id, ))
    tags = [row[0].lower() for row in cursor.fetchall()]
    conn.close()
    return tags


def validate_age(age: int) -> bool:
    """Проверяет, что возраст находится в допустимом диапазоне."""
    return MIN_AGE <= age <= MAX_AGE


# States
NAME, AGE, INTERESTS, PARENT_NAME, PHONE, COURSE_SELECTION, LOCATION_SELECTION, CONFIRMATION = range(
    8)
EDIT_COURSE_ID, EDIT_COURSE_NAME, EDIT_COURSE_DESCRIPTION, EDIT_COURSE_MIN_AGE, EDIT_COURSE_MAX_AGE = range(
    5)


def start(update: Update, context: CallbackContext) -> int:
    """Начало диалога для записи на пробное занятие."""
    update.message.reply_text(
        "Привет! Давайте подберем курс для вашего ребенка. Как зовут вашего ребенка?"
    )
    return NAME


def get_name(update: Update, context: CallbackContext) -> int:
    """Получение имени ребенка."""
    user_name = update.message.text
    if context and hasattr(context, 'user_data'):
        context.user_data['child_name'] = user_name
    update.message.reply_text(
        f"Отлично, {user_name}! Сколько лет вашему ребенку?")
    return AGE


def get_age(update: Update, context: CallbackContext) -> int:
    """Получение возраста ребенка."""
    try:
        user_age = int(update.message.text)
        if not validate_age(user_age):
            update.message.reply_text(
                f"Возраст должен быть от {MIN_AGE} до {MAX_AGE} лет. Пожалуйста, введите корректный возраст."
            )
            return AGE
    except ValueError:
        update.message.reply_text("Пожалуйста, введите число.")
        return AGE

    if context and hasattr(context, 'user_data'):
        context.user_data['child_age'] = user_age
    update.message.reply_text(
        "Чем увлекается ваш ребенок? (например, программирование, дизайн, математика и т.д.)"
    )
    return INTERESTS


def get_interests(update: Update, context: CallbackContext) -> int:
    """Получение интересов ребенка."""
    user_interests = update.message.text
    if context and hasattr(context, 'user_data'):
        context.user_data['child_interests'] = user_interests
    update.message.reply_text("Как вас зовут? (Имя родителя)")
    return PARENT_NAME


def get_parent_name(update: Update, context: CallbackContext) -> int:
    """Получение имени родителя."""
    parent_name = update.message.text
    if context and hasattr(context, 'user_data'):
        context.user_data['parent_name'] = parent_name
    update.message.reply_text(
        "Укажите ваш номер телефона для связи (начинается на +7 или 8):")
    return PHONE


def get_phone(update: Update, context: CallbackContext) -> int:
    """Получение номера телефона и подбор курсов."""
    phone = update.message.text
    if not is_valid_phone(phone):
        update.message.reply_text(
            "Номер телефона должен начинаться на +7 или 8. Пожалуйста, введите корректный номер."
        )
        return PHONE

    if context and hasattr(context, 'user_data'):
        context.user_data['phone'] = phone

    # Получаем курсы, подходящие по возрасту
    child_age = context.user_data.get('child_age')
    child_interests = context.user_data.get('child_interests', '').lower()

    if child_age is None or child_interests is None:
        update.message.reply_text(
            "Произошла ошибка. Пожалуйста, начните заново.")
        clear_user_data(context)
        return ConversationHandler.END

    conn = get_connection()
    cursor = conn.cursor()

    # Обновляем рекомендации для курсов
    update_course_recommendations()

    cursor.execute(
        '''
        SELECT DISTINCT c.id, c.name, c.description, c.min_age, c.max_age,
               string_agg(ct.tag, ', ') as tags
        FROM courses c
        LEFT JOIN course_tags ct ON c.id = ct.course_id
        WHERE c.min_age <= %s AND c.max_age >= %s
        GROUP BY c.id, c.name, c.description, c.min_age, c.max_age
    ''', (child_age, child_age))

    courses = cursor.fetchall()
    conn.close()

    if not courses:
        update.message.reply_text(
            "К сожалению, для вашего возраста нет доступных курсов.")
        return ConversationHandler.END

    # Вычисляем релевантность каждого курса
    scored_courses = []
    for course in courses:
        course_dict = {
            'id': course[0],
            'name': course[1],
            'description': course[2],
            'min_age': course[3],
            'max_age': course[4],
            'tags': course[5] or ''
        }
        score = calculate_course_score(child_age, child_interests, course_dict)
        scored_courses.append((course_dict, score))

    # Сортируем курсы по релевантности
    scored_courses.sort(key=lambda x: x[1], reverse=True)

    # Создаем клавиатуру с курсами
    keyboard = []
    recommendation_text = "🎯 На основе ваших интересов, мы подобрали следующие курсы:\n\n"

    for course, score in scored_courses:
        button_text = f"📚 {course['name']}"
        matching_tags = set(child_interests.split()).intersection(
            set(course['tags'].split(', ')))

        if score > 1.5:
            button_text = "⭐ " + button_text
            recommendation_text += (
                f"🌟 {course['name']}\n"
                f"📝 {course['description']}\n"
                f"👶 Возраст: {course['min_age']}-{course['max_age']} лет\n"
                f"🏷️ Подходящие интересы: {', '.join(matching_tags)}\n\n")
        elif score > 1.2:
            recommendation_text += (
                f"📚 {course['name']}\n"
                f"👶 Возраст: {course['min_age']}-{course['max_age']} лет\n\n")

        keyboard.append([
            InlineKeyboardButton(button_text,
                                 callback_data=f"course_{course['id']}")
        ])

    keyboard.append([InlineKeyboardButton("❌ Выйти", callback_data="exit")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text(recommendation_text, reply_markup=reply_markup)
    return COURSE_SELECTION


def select_course(update: Update, context: CallbackContext) -> int:
    """Обработчик выбора курса."""
    query = update.callback_query
    if query:
        query.answer()

    if query and query.data == "exit":
        query.edit_message_text(
            "Диалог завершен. Если хотите начать заново, напишите /start.")
        clear_user_data(context)
        return ConversationHandler.END

    if query:
        course_id = int(query.data.split("_")[1])
        if context and hasattr(context, 'user_data'):
            context.user_data['selected_course'] = course_id

        # Получаем доступные локации
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, district, address FROM locations ORDER BY district')
        locations = cursor.fetchall()
        conn.close()

        if not locations:
            query.edit_message_text(
                "К сожалению, сейчас нет доступных локаций для обучения.")
            return ConversationHandler.END

        # Группируем локации по районам
        keyboard = []
        current_district = None
        district_buttons = []

        for loc in locations:
            if current_district != loc[1]:  # Новый район
                if district_buttons:  # Добавляем кнопки предыдущего района
                    keyboard.extend(district_buttons)
                district_buttons = []
                current_district = loc[1]
                keyboard.append([
                    InlineKeyboardButton(f"📍 Район: {loc[1]}",
                                         callback_data="district_header")
                ])

            district_buttons.append([
                InlineKeyboardButton(f"🏫 {loc[2]}",
                                     callback_data=f"location_{loc[0]}")
            ])

        if district_buttons:  # Добавляем последние кнопки
            keyboard.extend(district_buttons)

        keyboard.append(
            [InlineKeyboardButton("❌ Выйти", callback_data="exit")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        query.edit_message_text(
            "Выберите удобное место обучения:\n"
            "Сначала найдите свой район, затем выберите адрес.",
            reply_markup=reply_markup)
        return LOCATION_SELECTION
    else:
        return ConversationHandler.END


def select_location(update: Update, context: CallbackContext) -> int:
    """Обработчик выбора локации."""
    query = update.callback_query
    if query:
        query.answer()

    if query and query.data == "exit":
        query.edit_message_text(
            "Диалог завершен. Если хотите начать заново, напишите /start.")
        clear_user_data(context)
        return ConversationHandler.END

    if query and query.data.startswith("district_header"):
        return LOCATION_SELECTION

    if query and query.data.startswith("location_"):
        location_id = int(query.data.split("_")[1])
        if context and hasattr(context, 'user_data'):
            context.user_data['selected_location'] = location_id

        # Получаем информацию о выбранном курсе и локации
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            '''
            SELECT c.name, c.description, l.district, l.address
            FROM courses c, locations l
            WHERE c.id = %s AND l.id = %s
        ''', (context.user_data.get('selected_course'), location_id))

        course_location = cursor.fetchone()
        conn.close()

        if not course_location:
            query.edit_message_text(
                "Произошла ошибка при выборе локации. Пожалуйста, начните заново."
            )
            return ConversationHandler.END

        confirmation_text = (f"📚 Курс: {course_location[0]}\n"
                             f"📍 Район: {course_location[2]}\n"
                             f"🏫 Адрес: {course_location[3]}\n\n"
                             "Подтвердить запись на пробное занятие?")

        keyboard = [[
            InlineKeyboardButton("Да ✅", callback_data="confirm_yes"),
            InlineKeyboardButton("Нет ❌", callback_data="confirm_no")
        ], [InlineKeyboardButton("❌ Выйти", callback_data="exit")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        query.edit_message_text(text=confirmation_text,
                                reply_markup=reply_markup)
        return CONFIRMATION

    return LOCATION_SELECTION


def confirm_signup(update: Update, context: CallbackContext) -> int:
    """Обработчик записи на курс."""
    query = update.callback_query
    if query:
        query.answer()

    if query and query.data == "exit":
        if query:
            query.edit_message_text(
                "Диалог завершен. Если хотите начать заново, напишите /start.")
        clear_user_data(context)
        return ConversationHandler.END

    if query and query.data == "confirm_yes":
        conn = get_connection()
        cursor = conn.cursor()

        # Сохраняем данные пользователя
        cursor.execute(
            '''
            INSERT INTO users (chat_id, parent_name, phone, child_name, child_age, child_interests)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (query.message.chat_id, context.user_data.get('parent_name'),
              context.user_data.get('phone'),
              context.user_data.get('child_name'),
              context.user_data.get('child_age'),
              context.user_data.get('child_interests')))
        user_id = cursor.fetchone()[0]

        # Записываем на пробное занятие
        cursor.execute(
            '''
            INSERT INTO trial_lessons (user_id, course_id, location_id, date, confirmed)
            VALUES (%s, %s, %s, %s, FALSE)
        ''', (user_id, context.user_data.get('selected_course'),
              context.user_data.get('selected_location'), datetime.now()))

        # Получаем информацию о курсе и локации для уведомления
        cursor.execute(
            '''
            SELECT c.name, c.description, l.district, l.address
            FROM courses c, locations l
            WHERE c.id = %s AND l.id = %s
        ''', (context.user_data.get('selected_course'),
              context.user_data.get('selected_location')))
        course_location = cursor.fetchone()
        conn.commit()

        # Уведомляем администраторов
        admin_message = (
            f"Новая запись на пробное занятие:\n\n"
            f"👤 Родитель: {context.user_data.get('parent_name')}\n"
            f"📱 Телефон: {context.user_data.get('phone')}\n"
            f"👶 Ребенок: {context.user_data.get('child_name')} ({context.user_data.get('child_age')} лет)\n"
            f"💡 Интересы: {context.user_data.get('child_interests')}\n"
            f"📚 Курс: {course_location[0]}\n"
            f"📝 Описание курса: {course_location[1]}\n"
            f"📍 Район: {course_location[2]}\n"
            f"🏫 Адрес: {course_location[3]}\n"
            f"📅 Дата записи: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        notify_admins(context, admin_message)

        if query:
            query.edit_message_text(
                "✅ Спасибо за запись!\n\n"
                "Мы свяжемся с вами для уточнения деталей пробного занятия.\n"
                f"📍 Адрес проведения: {course_location[3]} ({course_location[2]})"
            )
        conn.close()
    elif query:
        query.edit_message_text(
            "Хорошо, если передумаете, всегда можете вернуться и записаться позже."
        )

    clear_user_data(context)
    return ConversationHandler.END


def get_conversation_handler():
    return ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            NAME: [MessageHandler(Filters.text & ~Filters.command, get_name)],
            AGE: [MessageHandler(Filters.text & ~Filters.command, get_age)],
            INTERESTS:
            [MessageHandler(Filters.text & ~Filters.command, get_interests)],
            PARENT_NAME:
            [MessageHandler(Filters.text & ~Filters.command, get_parent_name)],
            PHONE:
            [MessageHandler(Filters.text & ~Filters.command, get_phone)],
            COURSE_SELECTION:
            [CallbackQueryHandler(select_course, pattern="^course_|^exit$")],
            LOCATION_SELECTION: [
                CallbackQueryHandler(
                    select_location,
                    pattern="^location_|^district_header$|^exit$")
            ],
            CONFIRMATION: [
                CallbackQueryHandler(
                    confirm_signup,
                    pattern="^confirm_yes$|^confirm_no$|^exit$")
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )


def cancel(update: Update, context: CallbackContext) -> int:
    """Отмена диалога."""
    update.message.reply_text(
        "Диалог прерван. Если хотите начать заново, напишите /start.")
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
        /add_tags - Добавить теги к курсу
        /delete_tags - Удалить теги у курса
        /list_courses_admin - Список курсов с ID (только для администраторов)
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
        f"👶 Возраст: {course[3]}-{course[4]} лет" for course in courses
    ])
    update.message.reply_text(f"Доступные курсы:\n\n{courses_list}")


def about(update: Update, context: CallbackContext):
    """Показывает информацию о школе."""
    message = (
        """🏫 Алгоритмика — международная школа программирования и математики для детей 7-17 лет.

        Мы помогаем детям освоить навыки будущего:
        - Программирование на Python, JavaScript и других языках.
        - Разработка игр и приложений.
        - Основы математики и логики.
        - Создание веб-сайтов и мобильных приложений.
        - Изучение искусственного интеллекта и анализа данных.

        📞 **Контактные данные:**
        - Телефон: +7 (800) 555-35-35
        - Email: info@algoritmika.org
        - Веб-сайт: [algoritmika.org](https://algoritmika.org)
        - Адрес: Москва, ул. Ленина, д. 42 (главный офис)

        📍 Мы работаем в более чем 20 странах мира!

        Присоединяйтесь к нам и откройте для вашего ребёнка мир программирования и математики!
        Чтобы записаться на пробное занятие, используйте команду /start """)
    update.message.reply_text(message, parse_mode="Markdown")


def view_trials(update: Update, context: CallbackContext):
    """Показывает все записи на пробные занятия."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text(
            "У вас нет прав для выполнения этой команды.")
        return

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 
            trial_lessons.id,
            users.child_name,
            users.parent_name,
            users.phone,
            courses.name as course_name,
            locations.district,
            locations.address,
            trial_lessons.date,
            trial_lessons.confirmed
        FROM trial_lessons
        JOIN users ON trial_lessons.user_id = users.id
        JOIN courses ON trial_lessons.course_id = courses.id
        JOIN locations ON trial_lessons.location_id = locations.id
        ORDER BY trial_lessons.date DESC
    ''')
    trials = cursor.fetchall()
    conn.close()

    if not trials:
        update.message.reply_text(
            "На данный момент записей на пробные занятия нет.")
        return

    trials_list = []
    for trial in trials:
        trial_info = (
            f"🔖 ID записи: {trial[0]}\n"
            f"👶 Ребенок: {trial[1]}\n"
            f"👤 Родитель: {trial[2]}\n"
            f"📱 Телефон: {trial[3]}\n"
            f"📚 Курс: {trial[4]}\n"
            f"📍 Район: {trial[5]}\n"
            f"🏫 Адрес: {trial[6]}\n"
            f"📅 Дата записи: {trial[7].strftime('%d.%m.%Y %H:%M')}\n"
            f"✅ Статус: {'Подтверждено' if trial[8] else 'Не подтверждено'}\n"
            f"{'=' * 30}")
        trials_list.append(trial_info)

    # Разбиваем на сообщения, если превышен лимит
    message = "📋 Записи на пробные занятия:\n\n"
    for trial in trials_list:
        if len(message +
               trial) > 4096:  # Максимальная длина сообщения в Telegram
            update.message.reply_text(message)
            message = trial
        else:
            message += trial + "\n"

    if message:
        update.message.reply_text(message)


def add_admin_command(update: Update, context: CallbackContext):
    """Добавляет администратора."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text(
            "У вас нет прав для выполнения этой команды.")
        return

    try:
        admin_chat_id = int(context.args[0])
        add_admin(admin_chat_id)
        update.message.reply_text(
            f"Администратор {admin_chat_id} успешно добавлен.")
    except (IndexError, ValueError):
        update.message.reply_text("Использование: /add_admin <chat_id>")


def confirm_trial(update: Update, context: CallbackContext):
    """Подтверждает или отклоняет запись на пробное занятие."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text(
            "У вас нет прав для выполнения этой команды.")
        return

    try:
        trial_id = int(context.args[0])
        conn = get_connection()
        cursor = conn.cursor()

        # Получаем информацию о записи
        cursor.execute(
            '''
            SELECT 
                trial_lessons.id,
                users.child_name,
                users.parent_name,
                users.phone,
                courses.name as course_name,
                trial_lessons.date,
                trial_lessons.confirmed,
                locations.address
            FROM trial_lessons
            JOIN users ON trial_lessons.user_id = users.id
            JOIN courses ON trial_lessons.course_id = courses.id
            JOIN locations ON trial_lessons.location_id = locations.id
            WHERE trial_lessons.id = %s
        ''', (trial_id, ))
        trial = cursor.fetchone()
        conn.close()

        if not trial:
            update.message.reply_text("❌ Запись с таким ID не найдена.")
            return

        # Создаем клавиатуру с кнопками подтверждения/отклонения
        keyboard = [[
            InlineKeyboardButton(
                "✅ Подтвердить",
                callback_data=f"confirm_trial_{trial_id}_yes"),
            InlineKeyboardButton("❌ Отклонить",
                                 callback_data=f"confirm_trial_{trial_id}_no")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Формируем сообщение с информацией о записи
        message = (
            f"📝 Запись на пробное занятие:\n\n"
            f"👶 Ребенок: {trial[1]}\n"
            f"👤 Родитель: {trial[2]}\n"
            f"📱 Телефон: {trial[3]}\n"
            f"📚 Курс: {trial[4]}\n"
            f"📅 Дата записи: {trial[5].strftime('%d.%m.%Y %H:%M')}\n"
            f"📍 Адрес: {trial[7]}\n"
            f"✅ Статус: {'Подтверждено' if trial[6] else 'Не подтверждено'}\n\n"
            f"Выберите действие:")

        update.message.reply_text(message, reply_markup=reply_markup)

    except (IndexError, ValueError):
        update.message.reply_text("Использование: /confirm_trial <ID записи>")


def handle_confirm_trial(update: Update, context: CallbackContext) -> int:
    """Обработчик подтверждения/отклонения записи."""
    query = update.callback_query
    if query:
        query.answer()

    if not query or not query.data.startswith("confirm_trial_"):
        return ConversationHandler.END

    # Получаем ID записи и действие из callback_data
    _, _, trial_id, action = query.data.split("_")
    trial_id = int(trial_id)

    conn = get_connection()
    cursor = conn.cursor()

    # Обновляем статус записи
    cursor.execute(
        '''
        UPDATE trial_lessons 
        SET confirmed = %s 
        WHERE id = %s
        RETURNING id, 
            (SELECT users.phone FROM users WHERE users.id = trial_lessons.user_id) as phone,
            (SELECT courses.name FROM courses WHERE courses.id = trial_lessons.course_id) as course_name,
            (SELECT locations.address FROM locations WHERE locations.id = trial_lessons.location_id) as address
    ''', (action == "yes", trial_id))

    result = cursor.fetchone()
    conn.commit()
    conn.close()

    if result:
        status = "✅ подтверждена" if action == "yes" else "❌ отклонена"
        if query:
            query.edit_message_text(f"Запись на пробное занятие {status}.")

        # Здесь можно добавить отправку уведомления пользователю
        if action == "yes":
            notify_admins(
                context,
                f"Запись на курс '{result[2]}' {status} в '{result[3]}'.\nТелефон для связи: {result[1]}"
            )
    else:
        if query:
            query.edit_message_text("❌ Ошибка при обновлении записи.")

    return ConversationHandler.END


def get_confirm_trial_handler():
    """Возвращает обработчик подтверждения записи."""
    return CallbackQueryHandler(handle_confirm_trial,
                                pattern="^confirm_trial_[0-9]+_(yes|no)$")


def filter_trials(update: Update, context: CallbackContext):
    """Фильтрация записей на пробные занятия."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text(
            "У вас нет прав для выполнения этой команды.")
        return

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 
            trial_lessons.id,
            users.child_name,
            users.parent_name,
            users.phone,
            courses.name as course_name,
            locations.district,
            locations.address,
            trial_lessons.date,
            trial_lessons.confirmed
        FROM trial_lessons
        JOIN users ON trial_lessons.user_id = users.id
        JOIN courses ON trial_lessons.course_id = courses.id
        JOIN locations ON trial_lessons.location_id = locations.id
        WHERE trial_lessons.confirmed = FALSE
        ORDER BY trial_lessons.date DESC
    ''')
    trials = cursor.fetchall()
    conn.close()

    if not trials:
        update.message.reply_text(
            "На данный момент нет неподтвержденных записей на пробные занятия."
        )
        return

    trials_list = []
    for trial in trials:
        trial_info = (f"🔖 ID записи: {trial[0]}\n"
                      f"👶 Ребенок: {trial[1]}\n"
                      f"👤 Родитель: {trial[2]}\n"
                      f"📱 Телефон: {trial[3]}\n"
                      f"📚 Курс: {trial[4]}\n"
                      f"📍 Район: {trial[5]}\n"
                      f"🏫 Адрес: {trial[6]}\n"
                      f"📅 Дата записи: {trial[7].strftime('%d.%m.%Y %H:%M')}\n"
                      f"{'=' * 30}")
        trials_list.append(trial_info)

    message = "📋 Неподтвержденные записи на пробные занятия:\n\n"
    for trial in trials_list:
        if len(message + trial) > 4096:
            update.message.reply_text(message)
            message = trial
        else:
            message += trial + "\n"

    if message:
        update.message.reply_text(message)


def delete_course(update: Update, context: CallbackContext):
    """Удаляет курс."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text(
            "У вас нет прав для выполнения этой команды.")
        return

    try:
        course_id = int(context.args[0])
        conn = get_connection()
        cursor = conn.cursor()

        # Проверяем существование курса
        cursor.execute('SELECT name FROM courses WHERE id = %s', (course_id, ))
        course = cursor.fetchone()

        if not course:
            update.message.reply_text("❌ Курс с таким ID не найден.")
            conn.close()
            return

        # Удаляем связанные теги
        cursor.execute('DELETE FROM course_tags WHERE course_id = %s',
                       (course_id, ))

        # Удаляем сам курс
        cursor.execute('DELETE FROM courses WHERE id = %s', (course_id, ))
        conn.commit()
        conn.close()

        update.message.reply_text(f"✅ Курс '{course[0]}' успешно удален.")
    except (IndexError, ValueError):
        update.message.reply_text("Использование: /delete_course <ID курса>")


def clear_trials(update: Update, context: CallbackContext):
    """Очищает все неподтвержденные записи на пробные занятия."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text(
            "У вас нет прав для выполнения этой команды.")
        return

    # Запрашиваем подтверждение
    keyboard = [[
        InlineKeyboardButton("Да ✅", callback_data="clear_trials_confirm")
    ], [InlineKeyboardButton("Нет ❌", callback_data="clear_trials_cancel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text(
        "⚠️ Вы уверены, что хотите удалить все неподтвержденные записи на пробные занятия?",
        reply_markup=reply_markup)


def handle_clear_trials(update: Update, context: CallbackContext):
    query = update.callback_query
    if query:
        query.answer()

    if query and query.data == "clear_trials_confirm":
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM trial_lessons WHERE confirmed = FALSE')
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        if query:
            query.edit_message_text(
                f"✅ Удалено {deleted_count} неподтвержденных записей.")
    elif query:
        query.edit_message_text("❌ Операция отменена.")


def get_clear_trials_handler():
    return CallbackQueryHandler(
        handle_clear_trials,
        pattern="^clear_trials_confirm$|^clear_trials_cancel$")


# Состояния для ConversationHandler редактирования курса


def get_edit_course_handler():
    """Возвращает обработчик для редактирования курса."""
    return ConversationHandler(
        entry_points=[CommandHandler('edit_course', start_edit_course)],
        states={
            EDIT_COURSE_ID: [
                MessageHandler(Filters.text & ~Filters.command,
                               get_course_id_to_edit)
            ],
            EDIT_COURSE_NAME: [
                CommandHandler(
                    'skip',
                    lambda u, c: get_course_name_to_edit(u, c, skip=True)),
                MessageHandler(Filters.text & ~Filters.command,
                               get_course_name_to_edit)
            ],
            EDIT_COURSE_DESCRIPTION: [
                CommandHandler(
                    'skip', lambda u, c: get_course_description_to_edit(
                        u, c, skip=True)),
                MessageHandler(Filters.text & ~Filters.command,
                               get_course_description_to_edit)
            ],
            EDIT_COURSE_MIN_AGE: [
                CommandHandler(
                    'skip',
                    lambda u, c: get_course_min_age_to_edit(u, c, skip=True)),
                MessageHandler(Filters.text & ~Filters.command,
                               get_course_min_age_to_edit)
            ],
            EDIT_COURSE_MAX_AGE: [
                CommandHandler(
                    'skip',
                    lambda u, c: get_course_max_age_to_edit(u, c, skip=True)),
                MessageHandler(Filters.text & ~Filters.command,
                               get_course_max_age_to_edit)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )


def start_edit_course(update: Update, context: CallbackContext) -> int:
    """Начинает процесс редактирования курса."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text(
            "У вас нет прав для выполнения этой команды.")
        return ConversationHandler.END

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM courses')
    courses = cursor.fetchall()
    conn.close()

    if not courses:
        update.message.reply_text("Нет доступных курсов для редактирования.")
        return ConversationHandler.END

    courses_list = "\n".join(
        [f"ID: {course[0]} - {course[1]}" for course in courses])
    update.message.reply_text(
        f"Доступные курсы:\n\n{courses_list}\n\n"
        "Введите ID курса, который хотите отредактировать:")
    return EDIT_COURSE_ID


def get_course_id_to_edit(update: Update, context: CallbackContext) -> int:
    """Получает ID курса для редактирования."""
    try:
        course_id = int(update.message.text)
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM courses WHERE id = %s', (course_id, ))
        course = cursor.fetchone()
        conn.close()

        if not course:
            update.message.reply_text(
                "Курс с таким ID не найден. Попробуйте снова.")
            return EDIT_COURSE_ID

        if context and hasattr(context, 'user_data'):
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


def get_course_name_to_edit(update: Update,
                            context: CallbackContext,
                            skip=False) -> int:
    """Получаетновое название курса."""
    if skip:
        current_course = context.user_data.get('current_course')
        if current_course:
            context.user_data['course_name'] = current_course[1]
    else:
        context.user_data['course_name'] = update.message.text

    update.message.reply_text(
        f"Текущее описание курса: {context.user_data.get('current_course', [None])[2]}\n"
        "Введите новое описание курса (или /skip, чтобы оставить текущее):")
    return EDIT_COURSE_DESCRIPTION


def get_course_description_to_edit(update: Update,
                                   context: CallbackContext,
                                   skip=False) -> int:
    """Получает новое описание курса."""
    if skip:
        current_course = context.user_data.get('current_course', [None])
        if current_course:
            context.user_data['course_description'] = current_course[2]
    else:
        context.user_data['course_description'] = update.message.text

    update.message.reply_text(
        f"Текущий минимальный возраст: {context.user_data.get('current_course', [None])[3]}\n"
        "Введите новый минимальный возраст (или /skip, чтобы оставить текущий):"
    )
    return EDIT_COURSE_MIN_AGE


def get_course_min_age_to_edit(update: Update,
                               context: CallbackContext,
                               skip=False) -> int:
    """Получает новый минимальный возраст."""
    if skip:
        current_course = context.user_data.get('current_course', [None])
        if current_course:
            context.user_data['course_min_age'] = current_course[3]
    else:
        try:
            min_age = int(update.message.text)
            if min_age < 0:
                update.message.reply_text(
                    "Возраст должен быть положительным числом. Попробуйте снова."
                )
                return EDIT_COURSE_MIN_AGE
            context.user_data['course_min_age'] = min_age
        except ValueError:
            update.message.reply_text("Пожалуйста, введите число.")
            return EDIT_COURSE_MIN_AGE

    update.message.reply_text(
        f"Текущий максимальный возраст: {context.user_data.get('current_course', [None])[4]}\n"
        "Введите новый максимальный возраст (или /skip, чтобы оставить текущий):"
    )
    return EDIT_COURSE_MAX_AGE


def get_course_max_age_to_edit(update: Update,
                               context: CallbackContext,
                               skip=False) -> int:
    """Получает новый максимальный возраст и сохраняет изменения."""
    if skip:
        current_course = context.user_data.get('current_course', [None])
        if current_course:
            context.user_data['course_max_age'] = current_course[4]
    else:
        try:
            max_age = int(update.message.text)
            min_age = context.user_data.get('course_min_age')
            if max_age is not None and min_age is not None and max_age <= min_age:
                update.message.reply_text(
                    "Максимальный возраст должен быть больше минимального. Попробуйте снова."
                )
                return EDIT_COURSE_MAX_AGE
            context.user_data['course_max_age'] = max_age
        except ValueError:
            update.message.reply_text("Пожалуйста, введите число.")
            return EDIT_COURSE_MAX_AGE

    # Сохраняем изменения в базе данных
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            '''
            UPDATE courses 
            SET name = %s, description = %s, min_age = %s, max_age =%s 
            WHERE id = %s
        ''', (context.user_data['course_name'],
              context.user_data['course_description'],
              context.user_data['course_min_age'],
              context.user_data['course_max_age'],
              context.user_data['course_id']))
        conn.commit()
        update.message.reply_text(f"✅ Курс успешно обновлен!")
    except psycopg2.Error as e:
        update.message.reply_text(f"❌ Ошибка при обновлении курса: {e}")
        conn.rollback()
    finally:
        conn.close()
    clear_user_data(context)
    return ConversationHandler.END


def edit_course(update: Update, context: CallbackContext):
    pass


def create_course(update: Update, context: CallbackContext):
    pass


def add_location(update: Update, context: CallbackContext):
    """Добавляет новый адрес школы."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text(
            "У вас нет прав для выполнения этой команды.")
        return

    try:
        # Expecting format: /add_location <district> | <address>
        location_data = " ".join(context.args)
        if "|" not in location_data:
            update.message.reply_text(
                "Использование: /add_location <район> | <адрес>")
            return

        district, address = [
            part.strip() for part in location_data.split("|", 1)
        ]

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO locations (district, address) VALUES (%s, %s) RETURNING id',
            (district, address))
        location_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()

        update.message.reply_text(f"✅ Адрес успешно добавлен!\n"
                                  f"ID: {location_id}\n"
                                  f"Район: {district}\n"
                                  f"Адрес: {address}")
    except Exception as e:
        update.message.reply_text(f"❌ Ошибка при добавлении адреса: {str(e)}")


def list_locations(update: Update, context: CallbackContext):
    """Показывает список всех адресов школы."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, district, address FROM locations ORDER BY district')
    locations = cursor.fetchall()
    conn.close()

    if not locations:
        update.message.reply_text("📍 Адреса школы пока не добавлены.")
        return

    message = "📍 Адреса школы:\n\n"
    current_district = None

    for loc in locations:
        if loc[1] != current_district:
            current_district = loc[1]
            message += f"\n🏢 {current_district}:\n"
        message += f"  • {loc[2]} (ID: {loc[0]})\n"

    update.message.reply_text(message)


def delete_location(update: Update, context: CallbackContext):
    """Удаляет адрес школы."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text(
            "У вас нет прав для выполнения этой команды.")
        return

    try:
        location_id = int(context.args[0])
        conn = get_connection()
        cursor = conn.cursor()

        # Get location info before deletion
        cursor.execute('SELECT district, address FROM locations WHERE id = %s',
                       (location_id, ))
        location = cursor.fetchone()

        if not location:
            update.message.reply_text("❌ Адрес с таким ID не найден.")
            conn.close()
            return

        cursor.execute('DELETE FROM locations WHERE id = %s', (location_id, ))
        conn.commit()
        conn.close()

        update.message.reply_text(f"✅ Адрес успешно удален!\n"
                                  f"Район: {location[0]}\n"
                                  f"Адрес: {location[1]}")
    except (IndexError, ValueError):
        update.message.reply_text("Использование: /delete_location <ID>")

def delete_tags_command(update: Update, context: CallbackContext):
    """Удаляет теги у курса."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return

    try:
        # Ожидаем формат: /delete_tags <course_id> <tag1> <tag2> ... <tagN>
        args = context.args
        if len(args) < 2:
            update.message.reply_text("Использование: /delete_tags <ID курса> <тег1> <тег2> ... <тегN>")
            return

        course_id = int(args[0])
        tags_to_delete = args[1:]

        conn = get_connection()
        cursor = conn.cursor()

        # Проверяем существование курса
        cursor.execute('SELECT name FROM courses WHERE id = %s', (course_id,))
        course = cursor.fetchone()

        if not course:
            update.message.reply_text("❌ Курс с таким ID не найден.")
            conn.close()
            return

        # Удаляем указанные теги
        cursor.execute('DELETE FROM course_tags WHERE course_id = %s AND tag = ANY(%s)',
                      (course_id, tags_to_delete))
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        update.message.reply_text(f"✅ Удалено {deleted_count} тегов у курса '{course[0]}'.")
    except (IndexError, ValueError) as e:
        update.message.reply_text(f"❌ Ошибка при удалении тегов: {str(e)}")

def add_tags_command(update: Update, context: CallbackContext):
    """Добавляет теги к курсу."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return

    try:
        # Ожидаем формат: /add_tags <course_id> <tag1> <tag2> ... <tagN>
        args = context.args
        if len(args) < 2:
            update.message.reply_text("Использование: /add_tags <ID курса> <тег1> <тег2> ... <тегN>")
            return

        course_id = int(args[0])
        tags = args[1:]

        conn = get_connection()
        cursor = conn.cursor()

        # Проверяем существование курса
        cursor.execute('SELECT name FROM courses WHERE id = %s', (course_id,))
        course = cursor.fetchone()

        if not course:
            update.message.reply_text("❌ Курс с таким ID не найден.")
            conn.close()
            return

        # Добавляем теги
        add_course_tags(cursor, course_id, tags)
        conn.commit()
        conn.close()

        update.message.reply_text(f"✅ Теги успешно добавлены к курсу '{course[0]}'.")
    except (IndexError, ValueError) as e:
        update.message.reply_text(f"❌ Ошибка при добавлении тегов: {str(e)}")

def list_courses_admin(update: Update, context: CallbackContext):
    """Выводит список курсов с ID и тегами для администраторов."""
    if update.message.chat_id not in get_admin_ids():
        update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, c.name, STRING_AGG(ct.tag, ', ') as tags
        FROM courses c
        LEFT JOIN course_tags ct ON c.id = ct.course_id
        GROUP BY c.id, c.name
        ORDER BY c.id
    """)
    courses = cursor.fetchall()
    conn.close()

    if not courses:
        update.message.reply_text("Список курсов пуст.")
        return

    courses_list = "\n\n".join([
        f"ID: {course[0]}\nНазвание: {course[1]}\nТеги: {course[2] or 'нет тегов'}"
        for course in courses
    ])
    update.message.reply_text(f"Список курсов:\n\n{courses_list}")


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
        CommandHandler('filter_trials', filter_trials),
        CommandHandler('add_tags', add_tags_command),
        CommandHandler('delete_tags', delete_tags_command),
        CommandHandler('list_courses_admin', list_courses_admin)
    ]