import os
import psycopg2
from psycopg2.extras import DictCursor
from config import MAIN_ADMIN_ID

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_connection():
    """Returns a database connection."""
    return psycopg2.connect(DATABASE_URL)

def init_db():
    """Инициализация базы данных."""
    conn = get_connection()
    cursor = conn.cursor()

    # Таблица для пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            parent_name TEXT,
            phone TEXT,
            child_name TEXT NOT NULL,
            child_age INTEGER NOT NULL,
            child_interests TEXT
        )
    ''')

    # Таблица для курсов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS courses (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            min_age INTEGER NOT NULL,
            max_age INTEGER NOT NULL
        )
    ''')

    # Таблица для локаций
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS locations (
            id SERIAL PRIMARY KEY,
            district TEXT NOT NULL,
            address TEXT NOT NULL
        )
    ''')

    # Таблица для записей на пробные занятия
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trial_lessons (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            course_id INTEGER NOT NULL,
            location_id INTEGER NOT NULL,
            date TIMESTAMP NOT NULL,
            confirmed BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (course_id) REFERENCES courses(id),
            FOREIGN KEY (location_id) REFERENCES locations(id)
        )
    ''')

    # Таблица для администраторов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL UNIQUE
        )
    ''')

    # Добавляем главного администратора, если его нет
    cursor.execute('SELECT COUNT(*) FROM admins WHERE chat_id = %s', (MAIN_ADMIN_ID,))
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO admins (chat_id) VALUES (%s)', (MAIN_ADMIN_ID,))

    # Добавляем тестовые локации, если их нет
    cursor.execute('SELECT COUNT(*) FROM locations')
    if cursor.fetchone()[0] == 0:
        locations = [
            ("Центральный", "ул. Ленина, д. 42"),
            ("Северный", "ул. Пушкина, д. 10"),
            ("Южный", "ул. Гагарина, д. 25"),
            ("Западный", "ул. Мира, д. 15"),
            ("Восточный", "ул. Садовая, д. 30")
        ]
        cursor.executemany('INSERT INTO locations (district, address) VALUES (%s, %s)', locations)

    # Добавляем тестовые курсы, если их нет
    cursor.execute('SELECT COUNT(*) FROM courses')
    if cursor.fetchone()[0] == 0:
        courses = [
            ("Основы логики и программирования", "🧠 Развиваем логическое мышление и изучаем основы программирования.", 6, 7),
            ("Компьютерная грамотность", "💻 Освойте основы работы с компьютером.", 7, 9),
            ("Создание веб-сайтов", "🌐 Научим создавать современные веб-сайты с нуля.", 11, 13),
            ("Графический дизайн", "🎨 Курс по созданию графики и дизайну.", 9, 14),
            ("Python", "🐍 Изучение языка программирования Python.", 12, 17)
        ]
        cursor.executemany('INSERT INTO courses (name, description, min_age, max_age) VALUES (%s, %s, %s, %s)', courses)

    conn.commit()
    conn.close()

def get_admin_ids():
    """Возвращает список chat_id администраторов."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT chat_id FROM admins')
    admins = [row[0] for row in cursor.fetchall()]
    conn.close()
    return admins

def add_admin(chat_id: int):
    """Добавляет администратора."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO admins (chat_id) VALUES (%s)', (chat_id,))
    conn.commit()
    conn.close()

def get_locations():
    """Возвращает список всех локаций."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, district, address FROM locations')
    locations = cursor.fetchall()
    conn.close()
    return locations

def get_location_by_id(location_id: int):
    """Возвращает информацию о локации по ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT district, address FROM locations WHERE id = %s', (location_id,))
    location = cursor.fetchone()
    conn.close()
    return location if location else None