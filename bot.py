import telebot
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
import os

load_dotenv()
service_account_info = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

# Преобразуем строку JSON в словарь
creds_dict = json.loads(service_account_info)

# ==== Настройка Google Sheets ====
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Открываем таблицу
try:
    spreadsheet = client.open("Student Certificates")
    students_sheet = spreadsheet.worksheet("students")
    certificates_sheet = spreadsheet.worksheet("certificates")
except gspread.SpreadsheetNotFound:
    raise ValueError("Таблица 'Student Certificates' не найдена.")
except Exception as e:
    raise ValueError(f"Ошибка при открытии таблицы: {e}")

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("NO TOKENS")

bot = telebot.TeleBot(TOKEN)

# Список ID администраторов
ADMIN_IDS = os.getenv("ADMIN_IDS").split(",")  # Убедитесь, что это список ID

# ==== Главное меню ====
def main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("Загрузить грамоту 📜"))
    markup.add(KeyboardButton("Мои грамоты 📂"))
    return markup

# ==== Меню администратора ====
def admin_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("Просмотр заявок 📝"))
    markup.add(KeyboardButton("Просмотр грамот 📜"))
    return markup

# ==== Проверка, является ли пользователь администратором ====
def is_admin(user_id):
    return str(user_id) in ADMIN_IDS

# ==== Старт бота ====
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    records = students_sheet.get_all_records()

    if is_admin(user_id):
        bot.send_message(user_id, "Добро пожаловать, администратор!", reply_markup=admin_menu())
        return

    for row in records:
        if row["ID"] == user_id:
            if row["Статус"] == "approved":
                bot.send_message(user_id, "Добро пожаловать!", reply_markup=main_menu())
            else:
                bot.send_message(user_id, "Ожидайте подтверждения.")
            return

    bot.send_message(user_id, "Введите ваше имя:")
    bot.register_next_step_handler(message, get_name)

# ==== Регистрация ====
def get_name(message):
    user_id = message.chat.id
    name = message.text
    bot.send_message(user_id, "Введите вашу почту:")
    bot.register_next_step_handler(message, get_email, name)

def get_email(message, name):
    user_id = message.chat.id
    email = message.text
    bot.send_message(user_id, "Введите ваш класс:")
    bot.register_next_step_handler(message, get_class, name, email)

def get_class(message, name, email):
    user_id = message.chat.id
    class_name = message.text

    students_sheet.append_row([user_id, name, email, class_name, "pending"])
    bot.send_message(user_id, "Регистрация отправлена на подтверждение.")
    
    for admin_id in ADMIN_IDS:
        bot.send_message(admin_id, f"Новый ученик: {name}\nКласс: {class_name}\nID: {user_id}",
                         reply_markup=InlineKeyboardMarkup().add(
                             InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_{user_id}")
                         ))

# ==== Подтверждение регистрации ====
@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_"))
def approve_student(call):
    user_id = int(call.data.split("_")[1])

    data = students_sheet.get_all_values()
    for i, row in enumerate(data):
        if row[0] == str(user_id):
            students_sheet.update_cell(i + 1, 5, "approved")
            bot.send_message(user_id, "Ваш аккаунт подтвержден!", reply_markup=main_menu())
            bot.send_message(call.message.chat.id, "Ученик подтвержден!")
            return

#Загрузка грамот
@bot.message_handler(content_types=['document'])
def upload_certificate(message):
    user_id = message.chat.id
    file_id = message.document.file_id

    if is_admin(user_id):
        bot.send_message(user_id, "Администраторы не могут загружать грамоты.")
        return

    records = students_sheet.get_all_records()
    found = False  # Флаг для проверки, найден ли пользователь

    for row in records:
        if row.get("ID") == user_id and row.get("Статус") == "approved":
            found = True  # Устанавливаем флаг, если пользователь найден
            try:
                # Добавляем данные в таблицу certificates
                certificates_sheet.append_row([user_id, row["Имя"], row["Класс"], file_id])
                bot.send_message(user_id, "Грамота отправлена на проверку.")
                
                for admin_id in ADMIN_IDS:
                    bot.send_message(admin_id, f"Новая грамота от {row['Имя']} (ID: {user_id})",
                                     reply_markup=InlineKeyboardMarkup().add(
                                         InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_cert_{file_id}")
                                     ))
                return
            except Exception as e:
                bot.send_message(user_id, "Произошла ошибка при записи в таблицу.")
                print(f"Ошибка при записи в таблицу: {e}")  # Выводим ошибку в консоль
                return

    if not found:
        bot.send_message(user_id, "Вы не зарегистрированы или ожидаете подтверждения.")

# ==== Подтверждение грамот ====
@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_cert_"))
def approve_certificate(call):
    file_id = call.data.split("_")[2]

    data = certificates_sheet.get_all_values()
    for i, row in enumerate(data):
        if row[3] == file_id:  # Проверяем по индексу 3, так как "file_id" на 4-м месте
            certificates_sheet.update_cell(i + 1, 5, "approved")  # Обновляем статус
            bot.send_message(call.message.chat.id, "Грамота подтверждена!")
            bot.send_message(int(row[0]), "Ваша грамота подтверждена!")  # ID ученика на 1-м месте
            return
# ==== Просмотр грамот ====
@bot.message_handler(func=lambda message: message.text == "Мои грамоты 📂")
def my_certificates(message):
    user_id = message.chat.id
    records = certificates_sheet.get_all_records()
    found = False

    for row in records:
        if row["user_id"] == user_id and row["status"] == "approved":  # Проверяем статус
            bot.send_document(user_id, row["file_id"])  # Отправляем файл
            found = True

    if not found:
        bot.send_message(user_id, "У вас нет подтвержденных грамот.")

# ==== Запуск бота ====
bot.polling(timeout=30)  # Увеличьте время ожидания до 30 секунд
