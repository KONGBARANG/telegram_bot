import os
import telebot
from telebot import types
import logging

# ១. រៀបចំប្រព័ន្ធដំណឹង (Logging) ដើម្បីឲ្យឃើញសកម្មភាពក្នុង Terminal
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from twilio.rest import Client
except ImportError:
    Client = None

# ២. ដាក់ API Token របស់អ្នកនៅទីនេះ ឬក៏ប្រើ Environment Variable
API_TOKEN = os.getenv('TELEGRAM_API_TOKEN', '8829234386:AAGAxOs6g9CIlAw8AXCdzV4RN5JlSvrnFTU')
if not API_TOKEN:
    logger.error('TELEGRAM_API_TOKEN មិនបានកំណត់ទេ។')
    raise SystemExit('Please set TELEGRAM_API_TOKEN environment variable.')

bot = telebot.TeleBot(API_TOKEN)

bot_info = None
BOT_USERNAME = None
try:
    bot_info = bot.get_me()
    BOT_USERNAME = bot_info.username if bot_info else None
except Exception as e:
    logger.error(f'Failed to initialize Telegram bot: {e}')
    raise SystemExit('Invalid Telegram API token or network issue. Check TELEGRAM_API_TOKEN and connectivity.')

TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_FROM_PHONE = os.getenv('TWILIO_FROM_PHONE')

# កន្លែងផ្ទុកទិន្នន័យបណ្តោះអាសន្ន
delivery_data = {}
customer_phones = {}  # phone_number -> order_id
customer_chats = {}  # customer chat_id -> order_id

print("--- Bot កំពុងចាប់ផ្តើមដំណើរការ... ---")

# ៣. ផ្នែកសម្រាប់អ្នកដឹកជញ្ជូន (Driver)
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    text = message.text or ""
    if text.startswith('/start'):
        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            order_id = parts[1].strip()
            if order_id in delivery_data:
                customer_chats[message.chat.id] = order_id
                driver_id = delivery_data[order_id]['driver_id']
                bot.send_message(message.chat.id, f"✅ ល្អ! Order #{order_id} ត្រូវបានភ្ជាប់ទៅអ្នក។\nសូមចុចប៊ូតុងខាងក្រោមដើម្បីផ្ញើទីតាំងរបស់អ្នក:" )
                markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
                button_location = types.KeyboardButton("📍 ផ្ញើទីតាំង", request_location=True)
                markup.add(button_location)
                bot.send_message(message.chat.id, "📍 សូមចុចប៊ូតុងនេះ", reply_markup=markup)
                bot.send_message(driver_id, f"📩 អតិថិជនបានចូល Bot និងត្រូវបានភ្ជាប់ទៅ Order #{order_id}។")
                return
    bot.reply_to(message, "សួស្តី! ប្រើពាក្យ /delivery ដើម្បីចាប់ផ្តើមផ្ញើសំណុំរឿងដឹកជញ្ជូន។")

@bot.message_handler(commands=['delivery'])
def start_delivery(message):
    logger.info(f"អ្នកដឹក ID {message.chat.id} បានចាប់ផ្តើមការដឹកជញ្ជូន")
    msg = bot.send_message(message.chat.id, "📦 សូមបញ្ចូលលេខកូដអីវ៉ាន់ (Order ID):")
    bot.register_next_step_handler(msg, process_order_id)

def process_order_id(message):
    order_id = message.text.strip() if message.text else ""
    driver_id = message.chat.id
    if not order_id:
        logger.warning(f"Order ID ជាករណីទទេពីអ្នកដឹក {driver_id}")
        msg = bot.send_message(driver_id, "❌ លេខ Order ID មិនត្រឹមត្រូវ។ សូមបញ្ចូលលេខកូដអីវ៉ាន់ម្តងទៀត:")
        bot.register_next_step_handler(msg, process_order_id)
        return

    delivery_data[order_id] = {'driver_id': driver_id}
    
    logger.info(f"បានចុះឈ្មោះ Order #{order_id} សម្រាប់អ្នកដឹក {driver_id}")
    
    bot.send_message(driver_id, f"✅ បានកត់ត្រា Order #{order_id}។ សូមបញ្ចូលលេខទូរស័ព្ទរបស់អតិថិជន...")
    
    # រង់ចាំលេខទូរស័ព្ទ
    msg = bot.send_message(driver_id, "📱 សូមបញ្ចូលលេខទូរស័ព្ទ (ឧទាហរណ៍: +855987654321):")
    bot.register_next_step_handler(msg, process_customer_phone, order_id)

def send_sms_notification(to_phone, body):
    if not Client:
        logger.warning('Twilio client មិនត្រូវបានដំឡើង។')
        return False
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_PHONE):
        logger.warning('Twilio credentials មិនបានកំណត់។')
        return False
    try:
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        twilio_client.messages.create(body=body, from_=TWILIO_FROM_PHONE, to=to_phone)
        logger.info(f'SMS បានផ្ញើទៅ {to_phone}')
        return True
    except Exception as e:
        logger.error(f'Failed to send SMS to {to_phone}: {e}')
        return False


def get_order_bot_link(order_id):
    if not BOT_USERNAME:
        return None
    return f"https://t.me/{BOT_USERNAME}?start={order_id}"


def normalize_phone(phone):
    if not phone:
        return ""
    phone = phone.strip()
    digits = ''.join(ch for ch in phone if ch.isdigit())
    if phone.startswith('+'):
        return '+' + digits
    if digits.startswith('0'):
        return '+855' + digits[1:]
    if digits.startswith('855'):
        return '+' + digits
    return digits


def process_customer_phone(message, order_id):
    """រង់ចាំលេខទូរស័ព្ទលោកអ្នក ហើយផ្ញើលម្អិត Telegram Bot"""
    if not order_id:
        driver_id = message.chat.id
        bot.send_message(driver_id, "⚠️ មិនអាចរកឃើញ Order ID បានទេ។ សូមចាប់ផ្តើមម្តងទៀតដោយ /delivery.")
        return

    phone_number = message.text.strip() if message.text else ""
    normalized_phone = normalize_phone(phone_number)
    driver_id = message.chat.id
    
    # កក់ចាក់ទិន្នន័យលេខទូរស័ព្ទ
    delivery_data[order_id]['phone_raw'] = phone_number
    delivery_data[order_id]['phone'] = normalized_phone
    delivery_data[order_id]['chat_id'] = None  # នឹងកក់ចាក់ chat_id នៃលោកអ្នក
    customer_phones[normalized_phone] = {'order_id': order_id, 'driver_id': driver_id}
    
    logger.info(f"បានទទួលលេខទូរស័ព្ទ {phone_number} សម្រាប់ Order #{order_id}")
    
    bot.send_message(driver_id, f"✅ បានកត់ត្រាលេខទូរស័ព្ធ: {phone_number}\n\n📱 សូមផ្ញើតំណរខាងក្រោមទៅអតិថិជន:")
    bot_link = get_order_bot_link(order_id)
    if bot_link:
        bot.send_message(driver_id, f"🔗 {bot_link}")

        sms_body = f"សួស្តី! សូមចូលលើ Bot និងបញ្ជូល Order #{order_id} ដើម្បីផ្ញើទីតាំង: {bot_link}"
        if send_sms_notification(normalized_phone, sms_body):
            bot.send_message(driver_id, "📩 SMS បានផ្ញើទៅអតិថិជនដោយស្វ័យប្រវត្តិ។")
        else:
            bot.send_message(driver_id, "⚠️ SMS មិនបានផ្ញើដោយស្វ័យប្រវត្តិ។ សូមចម្លងតំណនេះទៅអតិថិជនក្នុង SMS ឬ WhatsApp:")
            bot.send_message(driver_id, f"🔗 {bot_link}")

        bot.send_message(driver_id, "📌 អតិថិជនសូមចុចលើតំណនេះ ដើម្បីដាក់មក Bot ហើយបន្ទាប់មកផ្ញើទីតាំង។")
    else:
        bot.send_message(driver_id, "📌 មិនអាចបង្កើតតំណ Bot បានទេ។ សូមប្រាប់អតិថិជនឲ្យស្វែងរក Bot ដោយឈ្មោះ ហើយបញ្ជូលលេខ Order ID ឬលេខទូរស័ព្ទ។")
    bot.send_message(driver_id, "👉 បើអតិថិជនបានចូល, Bot នឹងសុំទីតាំងរបស់ពួកគេដោយស្វ័យប្រវត្តិ។")

# ៤. ផ្នែកទទួលទីតាំងពីលោកអ្នក
@bot.message_handler(func=lambda message: True)
def handle_customer_message(message):
    """ទទួល message ពីអតិថិជន និងស្នើប្រាប់ឲ្យផ្ញើទីតាំង"""
    chat_id = message.chat.id
    text = message.text.strip() if message.text else ""

    # ប្រសិនបើអតិថិជនបានចាប់ផ្តើម chat មុននឹងមាន order_id
    if chat_id in customer_chats:
        order_id = customer_chats[chat_id]
        info = delivery_data.get(order_id)
        if info is None:
            bot.send_message(chat_id, "⚠️ មិនអាចរកឃើញ order នេះទេ។ សូមផ្ញើលេខទូរស័ព្ទ ឬលេខ Order ID ម្ដងទៀត។")
            return

        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        button_location = types.KeyboardButton("📍 ផ្ញើទីតាំង", request_location=True)
        markup.add(button_location)
        bot.send_message(chat_id, "✅ សូមចុច 📍 ដើម្បីផ្ញើទីតាំងរបស់អ្នកទៅអ្នកដឹក។", reply_markup=markup)
        return

    # ប្រសិនបើអតិថិជនផ្ញើលេខទូរស័ព្ទ ឫលេខ Order ID
    matched_order = None
    normalized_text = normalize_phone(text)
    if normalized_text and normalized_text in customer_phones:
        matched_order = customer_phones[normalized_text]['order_id']
    elif text in delivery_data:
        matched_order = text

    if matched_order:
        delivery_data[matched_order]['chat_id'] = chat_id
        customer_chats[chat_id] = matched_order
        driver_id = delivery_data[matched_order]['driver_id']
        phone_number = delivery_data[matched_order].get('phone', 'N/A')

        bot.send_message(chat_id, f"✅ ល្អ! Order #{matched_order} ត្រូវបានភ្ជាប់ជាមួយអ្នក។\nសូមចុចប៊ូតុងខាងក្រោមដើម្បីផ្ញើទីតាំងរបស់អ្នក:")
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        button_location = types.KeyboardButton("📍 ផ្ញើទីតាំង", request_location=True)
        markup.add(button_location)
        bot.send_message(chat_id, "📍 សូមចុចប៊ូតុងនេះ", reply_markup=markup)

        bot.send_message(driver_id, f"📩 អតិថិជនបានភ្ជាប់ទៅ Order #{matched_order} (លេខ: {phone_number})។")
        return

    bot.send_message(chat_id, "សូមផ្ញើលេខទូរស័ព្ទ ឬលេខ Order ID ដែលអ្នកទទួលបានពីអ្នកដឹក ដើម្បីឲ្យ Bot ស្នើសុំទីតាំង។")

@bot.message_handler(content_types=['location'])
def handle_location(message):
    """ទទួលទីតាំងពីលោកអ្នក (Customer) ហើយផ្ញើទៅអ្នកដឹក"""
    if message.location is not None:
        lat = message.location.latitude
        lon = message.location.longitude
        logger.info(f"ទទួលបានទីតាំងថ្មីពី {message.chat.id}: Lat {lat}, Lon {lon}")

        order_id = customer_chats.get(message.chat.id)
        if not order_id:
            bot.send_message(message.chat.id, "⚠️ មិនអាចរកឃើញ Order ID របស់អ្នកទេ។ សូមផ្ញើលេខទូរស័ព្ទ ឬលេខ Order ID ម្ដងទៀត។")
            return

        info = delivery_data.get(order_id)
        if not info:
            bot.send_message(message.chat.id, "⚠️ មិនអាចរកឃើញ order នេះទេ។ សូមចាប់ផ្តើមម្តងទៀត។")
            return

        driver_id = info['driver_id']
        phone_number = info.get('phone', 'N/A')

        bot.send_message(driver_id, f"📍 ទីតាំងអ្នកទទួល (Order #{order_id}) លេខ: {phone_number}")
        bot.send_location(driver_id, lat, lon)
        bot.send_message(driver_id, "✅ ទីតាំងបានផ្ញើទៅអ្នកដឹកហើយ។")
        bot.send_message(message.chat.id, "✅ អរគុណ! ទីតាំងរបស់អ្នកត្រូវបានផ្ញើទៅអ្នកដឹកហើយ។")

        logger.info(f"ផ្ញើទីតាំង ({lat}, {lon}) ទៅអ្នកដឹក {driver_id} សម្រាប់ Order #{order_id}")


# ៥. បញ្ជាឲ្យ Bot ដើរ និងការពារការ Crash
if __name__ == "__main__":
    try:
        print("--- Bot កំពុងរង់ចាំសារ... (ចុច Ctrl+C ដើម្បីបញ្ឈប់) ---")
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        logger.error(f"មានកំហុសកើតឡើង: {e}")