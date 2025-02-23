from telegram.ext import Updater, CommandHandler, CallbackQueryHandler
from handlers import (
    get_conversation_handler,
    get_edit_course_handler,
    add_admin_command,
    list_courses,
    view_trials,
    help_command,
    delete_course,
    about,
    filter_trials,
    cancel,
    # Новые обработчики
    clear_trials,
    handle_clear_trials,
    add_location,
    list_locations,
    delete_location,
    confirm_trial,
    get_confirm_trial_handler,
    add_tags_command, 
    list_courses_admin
)
from database import init_db
from config import BOT_TOKEN
import logging

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # Инициализация базы данных
    init_db()

    # Создание бота
    updater = Updater(BOT_TOKEN)
    dispatcher = updater.dispatcher

    # Добавление обработчиков
    dispatcher.add_handler(get_conversation_handler())
    dispatcher.add_handler(get_edit_course_handler())
    dispatcher.add_handler(get_confirm_trial_handler())  # Добавляем обработчик подтверждения записи

    # Базовые команды
    dispatcher.add_handler(CommandHandler('add_admin', add_admin_command))
    dispatcher.add_handler(CommandHandler('courses', list_courses))
    dispatcher.add_handler(CommandHandler('view_trials', view_trials))
    dispatcher.add_handler(CommandHandler('help', help_command))
    dispatcher.add_handler(CommandHandler('delete_course', delete_course))
    dispatcher.add_handler(CommandHandler('about', about))
    dispatcher.add_handler(CommandHandler('filter_trials', filter_trials))
    dispatcher.add_handler(CommandHandler('cancel', cancel))
    dispatcher.add_handler(CommandHandler('confirm_trial', confirm_trial))  # Добавляем команду подтверждения
    dispatcher.add_handler(CommandHandler('add_tags', add_tags_command))
    dispatcher.add_handler(CommandHandler('delete_tags', delete_tags_command))
    dispatcher.add_handler(CommandHandler('list_courses_admin', list_courses_admin))

    # Новые команды
    dispatcher.add_handler(CommandHandler('clear_trials', clear_trials))
    dispatcher.add_handler(CallbackQueryHandler(handle_clear_trials, pattern='^clear_trials_'))

    # Команды для работы с районами и адресами
    dispatcher.add_handler(CommandHandler('add_location', add_location))
    dispatcher.add_handler(CommandHandler('list_locations', list_locations))
    dispatcher.add_handler(CommandHandler('delete_location', delete_location))

    # Запуск бота
    updater.start_polling()
    logger.info("Bot started successfully!")
    updater.idle()

if __name__ == '__main__':
    main()