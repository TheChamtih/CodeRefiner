# bot.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler, CommandHandler, MessageHandler, Filters, CallbackQueryHandler
from telegram.ext import Updater
from handlers import (get_conversation_handler,
                      add_admin_command ,
                      list_courses ,
                      view_trials ,
                      confirm_trial,
                      help_command ,
                      delete_course ,
                      get_create_course_handler,
                      get_edit_course_handler ,
                      clear_trials ,
                      about ,
                      filter_trials,
                      get_confirm_trial_handler,
                      cancel
                      )
from config import BOT_TOKEN
import logging

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
def main():
    # Инициализация базы данных
    from database import init_db
    init_db()

    # Создание бота
    updater = Updater(BOT_TOKEN)
    dispatcher = updater.dispatcher

    # Добавление обработчиков
    dispatcher.add_handler(get_conversation_handler())
    dispatcher.add_handler(get_confirm_trial_handler())
    dispatcher.add_handler(get_edit_course_handler())  # Добавляем ConversationHandler для редактирования курса
    dispatcher.add_handler(get_create_course_handler())  # Добавляем ConversationHandler для создания курса
    
    dispatcher.add_handler(CommandHandler('add_admin', add_admin_command))
    dispatcher.add_handler(CommandHandler('courses', list_courses))
    dispatcher.add_handler(CommandHandler('view_trials', view_trials))  # Обновлённая команда
    dispatcher.add_handler(CommandHandler('confirm_trial', confirm_trial))
    dispatcher.add_handler(CommandHandler('clear_trials', clear_trials))  # Новая команда
    dispatcher.add_handler(CommandHandler('help', help_command))
    dispatcher.add_handler(CommandHandler('delete_course', delete_course))
    dispatcher.add_handler(CommandHandler('about', about))  # Добавляем команду /about
    dispatcher.add_handler(CommandHandler('filter_trials', filter_trials))
    dispatcher.add_handler(CommandHandler('cancel', cancel))

    # Запуск бота
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()