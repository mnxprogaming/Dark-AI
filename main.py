import os
import sqlite3
import requests
import yt_dlp
import tempfile
import re
import phonenumbers
from phonenumbers import carrier, geocoder, NumberParseException
from urllib.parse import urlparse
from keep_alive import keep_alive
import telebot
from telebot import types as tg_types
from google import genai
from flask import Flask
from threading import Thread
from ddgs import DDGS

# =========================
# WEB SERVER
# =========================

# ==============================
# 🌐 WEB SEARCH FEATURE
# ==============================

def web_search(query, max_results=5):
    try:
        results = []

        with DDGS() as ddgs:
            search_results = ddgs.text(
                query,
                region="in-en",
                safesearch="moderate",
                max_results=max_results
            )

            for r in search_results:
                results.append({
                    "title": r.get("title", ""),
                    "body": r.get("body", ""),
                    "url": r.get("href", "")
                })

        return results

    except Exception as e:
        print(f"Web Search Error: {e}")
        return []

# ==============================
# 🤖 AUTO WEB SEARCH DETECTION
# ==============================

def needs_web_search(text):
    text = text.lower().strip()

    keywords = [
        "latest",
        "आज",
        "अभी",
        "ताजा",
        "ताज़ा",
        "news",
        "न्यूज़",
        "समाचार",
        "weather",
        "मौसम",
        "price",
        "कीमत",
        "भाव",
        "rate",
        "रेट",
        "live",
        "लाइव",
        "current",
        "अभी का",
        "आज का",
        "आज की",
        "कौन जीता",
        "result",
        "रिजल्ट"
    ]

    return any(keyword in text for keyword in keywords)


# =========================
# API KEYS
# =========================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN missing")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY missing")


# =========================
# TELEGRAM + GEMINI
# =========================

bot = telebot.TeleBot(BOT_TOKEN)

client = genai.Client(
    api_key=GEMINI_API_KEY
)


# =========================
# DARK AI PERSONALITY
# =========================

AI_NAME = "Dark AI"

SYSTEM_PROMPT = f"""
Tum {AI_NAME} ho, ek smart, friendly aur helpful AI assistant.

User se Hindi ya Hinglish mein naturally baat karo.
User English mein bole to English mein jawab de sakte ho.

Coding, study, writing, stories, translation, maths,
ideas, planning aur general questions mein help karo.

Jawab clear, useful aur seedha do.
"""


# =========================
# PERMANENT MEMORY
# =========================

DB_NAME = "dark_ai_memory.db"


def init_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            text TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def add_memory(user_id, role, text):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO memories (user_id, role, text) VALUES (?, ?, ?)",
        (user_id, role, text)
    )

    conn.commit()
    conn.close()


def get_memory(user_id, limit=10):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT role, text
        FROM memories
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
    """, (user_id, limit))

    rows = cursor.fetchall()

    conn.close()

    rows.reverse()

    return rows


def clear_memory(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM memories WHERE user_id = ?",
        (user_id,)
    )

    conn.commit()
    conn.close()


init_database()
    
# =========================
# GOOGLE SHEETS
# =========================

GOOGLE_SHEET_URL = os.environ.get("GOOGLE_SHEET_URL")


def save_to_google_sheet(user_id, username, message, reply):
    try:
        data = {
            "secret": os.environ.get("SHEET_SECRET"),
            "user_id": user_id,
            "username": username,
            "message": message,
            "reply": reply
        }

        response = requests.post(
            GOOGLE_SHEET_URL,
            json=data,
            timeout=10
        )

        print("Google Sheet:", response.text)

    except Exception as e:
        print("❌ Google Sheet Error:", e)


# =========================
# START MENU
# =========================

@bot.message_handler(commands=["start"])
def start_command(message):

    welcome = f"""
🤖 Welcome to {AI_NAME}! ❤️

Main tumhara personal AI assistant hoon.

👇 Neeche menu se feature choose karo:
"""

    markup = tg_types.InlineKeyboardMarkup(row_width=2)

    btn_ai = tg_types.InlineKeyboardButton(
        "🤖 AI Chat",
        callback_data="ai_chat"
    )

    btn_download = tg_types.InlineKeyboardButton(
        "📥 Downloader",
        callback_data="downloader"
    )

    btn_number = tg_types.InlineKeyboardButton(
    "📱 Number Check",
    callback_data="number_check"
    )

    btn_tools = tg_types.InlineKeyboardButton(
        "🛠️ Tools",
        callback_data="tools"
    )

    markup.add(
    btn_ai,
    btn_download,
    btn_number,
    btn_tools
   )

    bot.send_message(
        message.chat.id,
        welcome,
        reply_markup=markup
    )


# =========================
# MENU BUTTON HANDLER
# =========================

@bot.callback_query_handler(func=lambda call: True)
def menu_callback(call):

    if call.data == "ai_chat":

        bot.answer_callback_query(call.id)

        bot.send_message(
            call.message.chat.id,
            "🤖 AI Chat active hai.\n\n"
            "Apna sawaal bhejo, Dark AI jawab dega."
        )

    elif call.data == "downloader":

        bot.answer_callback_query(call.id)

        bot.send_message(
            call.message.chat.id,
            "📥 Downloader\n\n"
            "Video/photo ka link bhejo.\n"
            "Example:\n"
            "Download this video https://example.com/video"
        )

    elif call.data == "number_check":

        bot.answer_callback_query(call.id)

        bot.send_message(
            call.message.chat.id,
            "📱 Number Check\n\n"
            "Phone number bhejo.\n\n"
            "Example:\n"
            "+919696712836\n\n"
            "Ya likho:\n"
            "Is number ke baare me batao +919696712836"
        )

    elif call.data == "tools":

        bot.answer_callback_query(call.id)

        bot.send_message(
            call.message.chat.id,
            "🛠️ Tools\n\n"
            "📥 Video/Photo Downloader\n"
            "📱 Number Check\n"
            "🧠 Permanent Memory\n"
            "🤖 AI Assistant\n"
            "💻 Coding Help\n"
            "📝 Writing Help"
        )

# =========================
# CLEAR MEMORY COMMAND
# =========================

@bot.message_handler(commands=["clear"])
def clear_command(message):

    clear_memory(message.from_user.id)

    bot.reply_to(
        message,
        "🧠 Tumhari memory clear kar di gayi hai!"
    )

# =========================
# PHOTO + VIDEO DOWNLOADER
# =========================

def is_url(text):
    if not text:
        return False

    return re.match(
        r"^https?://",
        text.strip(),
        re.IGNORECASE
    ) is not None


def download_media(url):
    temp_dir = tempfile.mkdtemp()

    ydl_opts = {
        "outtmpl": os.path.join(temp_dir, "%(title)s.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": 50 * 1024 * 1024
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

    return filename


@bot.message_handler(commands=["download"])
def download_command(message):

    text = message.text.replace("/download", "", 1).strip()

    if not text:
        bot.reply_to(
            message,
            "📥 Usage:\n\n/download <video/photo link>"
        )
        return

    process_download(message, text)


@bot.message_handler(
    func=lambda message:
    message.content_type == "text"
    and ("http://" in message.text.lower()
         or "https://" in message.text.lower())
)
def url_downloader(message):

    text = message.text.strip()

    match = re.search(
        r'https?://[^\s]+',
        text,
        re.IGNORECASE
    )

    if not match:
        return

    url = match.group(0)

    download_words = [
        "download",
        "डाउनलोड",
        "डाउनलोड करो",
        "download karo",
        "video download",
        "photo download",
        "video",
        "photo"
    ]

    if any(word in text.lower() for word in download_words):
        process_download(message, url)

def process_download(message, url):

    try:

        bot.send_chat_action(
            message.chat.id,
            "upload_video"
        )

        status = bot.reply_to(
            message,
            "⏳ Media download ho raha hai..."
        )

        file_path = download_media(url)

        if not os.path.exists(file_path):
            bot.edit_message_text(
                "❌ Media download nahi ho paya.",
                message.chat.id,
                status.message_id
            )
            return

        file_size = os.path.getsize(file_path)

        # Telegram upload safety limit for this bot setup
        if file_size > 50 * 1024 * 1024:

            bot.edit_message_text(
                "❌ File bahut badi hai.\n"
                "Please chhota video/link try karo.",
                message.chat.id,
                status.message_id
            )

            os.remove(file_path)
            return

        bot.edit_message_text(
            "📤 Download complete!\n"
            "Telegram par upload ho raha hai...",
            message.chat.id,
            status.message_id
        )

        extension = os.path.splitext(file_path)[1].lower()

        with open(file_path, "rb") as media:

            if extension in [".jpg", ".jpeg", ".png", ".webp"]:

                bot.send_photo(
                    message.chat.id,
                    media,
                    caption="🖼️ Download complete\n🤖 Dark AI"
                )

            else:

                bot.send_video(
                    message.chat.id,
                    media,
                    caption="🎬 Download complete\n🤖 Dark AI",
                    supports_streaming=True
                )

        os.remove(file_path)

        try:
            bot.delete_message(
                message.chat.id,
                status.message_id
            )
        except:
            pass

    except Exception as e:

        print("DOWNLOAD ERROR:", e)

        bot.reply_to(
            message,
            "❌ Download failed.\n\n"
            "Possible reasons:\n"
            "• Link private hai\n"
            "• Link supported nahi hai\n"
            "• Video unavailable hai\n"
            "• File bahut badi hai"
        )
# =========================
# PHONE NUMBER FUNCTIONS
# =========================

def extract_phone_number(text):
    if not text:
        return None

    match = re.search(
        r'(?<!\d)(\+?\d[\d\s\-()]{7,}\d)(?!\d)',
        text
    )

    if match:
        return match.group(1).strip()

    return None


def check_phone_number(phone):
    try:
        cleaned_phone = re.sub(r'[\s\-()]', '', phone)

        parsed = phonenumbers.parse(cleaned_phone, None)

        valid = phonenumbers.is_valid_number(parsed)

        country = geocoder.country_name_for_number(
            parsed,
            "en"
        )

        region = geocoder.description_for_number(
            parsed,
            "en"
        )

        carrier_name = carrier.name_for_number(
            parsed,
            "en"
        )

        number_type = phonenumbers.number_type(parsed)

        if number_type == phonenumbers.PhoneNumberType.MOBILE:
            phone_type = "Mobile"
        elif number_type == phonenumbers.PhoneNumberType.FIXED_LINE:
            phone_type = "Fixed Line"
        elif number_type == phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE:
            phone_type = "Mobile / Fixed Line"
        else:
            phone_type = "Unknown"

        return {
            "valid": valid,
            "country": country or "Unknown",
            "carrier": carrier_name or "Unknown",
            "type": phone_type,
            "region": region or "Unknown"
        }

    except NumberParseException:
        return None
# =========================
# AUTOMATIC PHONE NUMBER CHECK
# =========================

@bot.message_handler(
    func=lambda message:
    message.content_type == "text"
    and extract_phone_number(message.text) is not None
)
def phone_number_handler(message):

    phone = extract_phone_number(message.text)

    result = check_phone_number(phone)

    if not result:
        bot.reply_to(
            message,
            "❌ Number ko samajh nahi paaya.\n"
            "Example: +919876543210"
        )
        return

    valid_text = "Yes" if result["valid"] else "No"

    reply = f"""
📱 Number Check

Number: {phone}
✅ Valid: {valid_text}
🇮🇳 Country: {result["country"] or "Unknown"}
📡 Carrier: {result["carrier"]}
📱 Type: {result["type"]}
📍 Region: {result["region"]}

🔎 Public Information
Name: Public source se available nahi
Business: Public source se available nahi
Website: Public source se available nahi
Spam reports: Public source se available nahi

⚠️ Sirf publicly available information dikhayi gayi hai.
"""

    bot.reply_to(message, reply)
# =========================
# CHECK GEMINI MODELS
# =========================

try:
    print("\n===== AVAILABLE GEMINI MODELS =====")

    for model in client.models.list():
        print(
            model.name,
            "|",
            getattr(model, "supported_actions", None)
        )

except Exception as e:
    print("MODEL LIST ERROR:", e)

# =========================
# IMAGE AI
# =========================

@bot.message_handler(content_types=["photo"])
def image_ai_handler(message):
    try:
        bot.send_chat_action(
            message.chat.id,
            "typing"
        )

        # Telegram se photo file information lo
        file_info = bot.get_file(
            message.photo[-1].file_id
        )

        # Image download karo
        image_bytes = bot.download_file(
            file_info.file_path
        )

        # User ka question
        prompt = message.caption or (
            "Is image ko dhyan se analyze karo. "
            "Image mein kya dikh raha hai, "
            "important details aur agar text hai "
            "to uska bhi batao. "
            "Hindi/Hinglish mein jawab do."
        )

        # Gemini ko image + prompt bhejo
        response = client.models.generate_content(
            model="gemini-3.7-flash",
            contents=[
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_bytes
                    }
                },
                prompt
            ]
        )

        answer = response.text

        bot.send_message(
    message.chat.id,
    "🖼️ Dark AI Image Analysis\n\n" + str(answer),
    parse_mode=None
)

    except Exception as e:
        print("IMAGE AI ERROR:", e)

        bot.reply_to(
            message,
            "❌ Image analyze nahi ho payi.\n\n"
            "Error: " + str(e)
        )
# =========================
# 🌐 WEB SEARCH COMMAND
# =========================

@bot.message_handler(commands=["search"])
def search_command(message):

    query = message.text.replace("/search", "", 1).strip()

    if not query:
        bot.reply_to(
            message,
            "🌐 Web Search\n\n"
            "Aise use karo:\n"
            "/search आज की भारत की खबरें"
        )
        return

    try:
        bot.send_chat_action(
            message.chat.id,
            "typing"
        )

        results = web_search(query, 5)

        if not results:
            bot.reply_to(
                message,
                "❌ Search results nahi mile."
            )
            return

        reply = "🌐 Web Search Results\n\n"

        for i, result in enumerate(results, 1):
            reply += (
                f"{i}. {result['title']}\n"
                f"{result['body'][:300]}\n"
                f"🔗 {result['url']}\n\n"
            )

        bot.reply_to(
            message,
            reply,
            disable_web_page_preview=True
        )

    except Exception as e:
        print("WEB SEARCH ERROR:", e)
        bot.reply_to(
            message,
            "❌ Web Search Error:\n" + str(e)
        )
# =========================
# AI MESSAGE HANDLER
# =========================

@bot.message_handler(func=lambda message: True)
def ai_reply(message):

    try:

        bot.send_chat_action(
            message.chat.id,
            "typing"
        )

        user_id = message.from_user.id

        history = get_memory(user_id, 10)

        conversation = SYSTEM_PROMPT + "\n\n"
        
                for role, text in history:
                    conversation += role + ": " + text + "\n"


# ==============================
# 🌐 AUTO WEB SEARCH
# ==============================

    if needs_web_search(message.text):

    results = web_search(message.text, 5)

    if results:

        web_context = "\n\n".join(
            f"Source {i}:\n"
            f"Title: {r['title']}\n"
            f"Content: {r['body']}\n"
            f"URL: {r['url']}"
            for i, r in enumerate(results, 1)
        )

        conversation += f"""

🌐 WEB SEARCH RESULTS

{web_context}

IMPORTANT:
- User ke question ka answer in search results ke basis par do.
- Latest/current information ko priority do.
- Facts invent mat karo.
- Hindi/Hinglish mein clear answer do.
- Agar search results mein answer nahi hai to clearly batao.
- Answer ke end mein relevant Sources mention karo.

"""


conversation += "\nUser: " + message.text
            

        response = client.models.generate_content(
    model="gemini-3.6-flash",
    contents=conversation
)
        answer = response.text

        add_memory(
            user_id,
            "User",
            message.text
        )

        add_memory(
            user_id,
            "Dark AI",
            answer
        )
        save_to_google_sheet(
    user_id,
    message.from_user.username or "",
    message.text,
    answer)
        bot.reply_to(
            message,
            answer
        )

    except Exception as e:

        print("ERROR:", e)

        bot.reply_to(
            message,
            "❌ AI Error:\n" + str(e)
        )


# =========================
# START BOT
# =========================

print("🤖 Dark AI is running...")

keep_alive()
bot.infinity_polling()
