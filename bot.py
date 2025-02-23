from telegram.ext import Updater, CommandHandler, CallbackQueryHandler
from handlers import (
    get_conversation_handler,
    get_confirm_trial_handler,
    get_create_course_handler,
    get_edit_course_handler,
    add_admin_command,
    list_courses,
    view_trials,
    confirm_trial,
    help_command,
    delete_course,
    clear_trials,
    handle_clear_trials,
    about,
    filter_trials,
    cancel
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
    dispatcher.add_handler(get_confirm_trial_handler())
    dispatcher.add_handler(get_edit_course_handler())
    dispatcher.add_handler(get_create_course_handler())

    # Базовые команды
    dispatcher.add_handler(CommandHandler('add_admin', add_admin_command))
    dispatcher.add_handler(CommandHandler('courses', list_courses))
    dispatcher.add_handler(CommandHandler('view_trials', view_trials))
    dispatcher.add_handler(CommandHandler('help', help_command))
    dispatcher.add_handler(CommandHandler('delete_course', delete_course))
    dispatcher.add_handler(CommandHandler('about', about))
    dispatcher.add_handler(CommandHandler('filter_trials', filter_trials))
    dispatcher.add_handler(CommandHandler('cancel', cancel))

    # Обработчики для очистки пробных занятий
    dispatcher.add_handler(CommandHandler('clear_trials', clear_trials))
    dispatcher.add_handler(CallbackQueryHandler(handle_clear_trials, pattern="^clear_trials_"))

    # Запуск бота
    updater.start_polling()
    logger.info("Bot started successfully!")
    updater.idle()

if __name__ == '__main__':
    main()