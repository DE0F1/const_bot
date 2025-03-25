import telebot
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
import os

load_dotenv();
service_account_info = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
try: 
    service_account_info = json.loads(service_account_json_str)
except json.JSONDecodeError as e:
    print (f"Error decoding JSON: {e}")
    praise

# ==== Настройка Google Sheets ====
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict("service_account_info", scope)
client = gspread.authorize(creds)

# Открываем таблицу
spreadsheet = client.open("Students Certificates")
students_sheet = spreadsheet.worksheet("students")
certificates_sheet = spreadsheet.worksheet("certificates")

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("NO TOKENS")

bot = telebot.TeleBot(TOKEN)

# Список ID администраторов
ADMIN_IDS = os.getenv("ADMIN_IDS")  # Замените на реальные ID

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

# ==== Старт бота ====
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    records = students_sheet.get_all_records()

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
            students_sheet.update_cell(i+1, 5, "approved")
            bot.send_message(user_id, "Ваш аккаунт подтвержден!", reply_markup=main_menu())
            bot.send_message(call.message.chat.id, "Ученик подтвержден!")
            return

# ==== Загрузка грамот ====
@bot.message_handler(content_types=['document'])
def upload_certificate(message):
    user_id = message.chat.id
    file_id = message.document.file_id

    records = students_sheet.get_all_records()
    for row in records:
        if row["ID"] == user_id and row["Статус"] == "approved":
            certificates_sheet.append_row([file_id, user_id, file_id, "pending"])
            bot.send_message(user_id, "Грамота отправлена на проверку.")
            
            for admin_id in ADMIN_IDS:
                bot.send_message(admin_id, f"Новая грамота от {row['Имя']} (ID: {user_id})",
                                 reply_markup=InlineKeyboardMarkup().add(
                                     InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_cert_{file_id}")
                                 ))
            return

    bot.send_message(user_id, "Вы не зарегистрированы или ожидаете подтверждения.")

# ==== Подтверждение грамот ====
@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_cert_"))
def approve_certificate(call):
    file_id = call.data.split("_")[2]

    data = certificates_sheet.get_all_values()
    for i, row in enumerate(data):
        if row[0] == file_id:
            certificates_sheet.update_cell(i+1, 4, "approved")
            bot.send_message(call.message.chat.id, "Грамота подтверждена!")
            bot.send_message(int(row[1]), "Ваша грамота подтверждена!")
            return

# ==== Просмотр грамот ====
@bot.message_handler(func=lambda message: message.text == "Мои грамоты 📂")
def my_certificates(message):
    user_id = message.chat.id
    records = certificates_sheet.get_all_records()
    found = False

    for row in records:
        if row["ID ученика"] == user_id and row["Статус"] == "approved":
            bot.send_document(user_id, row["Файл"])
            found = True

    if not found:
        bot.send_message(user_id, "У вас нет подтвержденных грамот.")

# ==== Запуск бота ====
bot.polling()
