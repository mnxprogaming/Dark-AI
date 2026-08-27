import os
import sqlite3
import requests
import yt_dlp
import tempfile
import re
from urllib.parse import urlparse
from keep_alive import keep_alive
import telebot
from google import genai
from google.genai import types
from flask import Flask
from threading import Thread

# =========================
# WEB SERVER
# =========================




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

GOOGLE_SHEET_URL = "https://script.google.com/macros/s/AKfycbxxCtHcajJiRnhFTuuEZKETUq07-L7UnIEtgQWInH2GTupPhdsRGIjHP7raCcNzu4aa/exec"

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
# START COMMAND
# =========================

@bot.message_handler(commands=["start"])
def start_command(message):

    welcome = f"""
🤖 Welcome to {AI_NAME}!

Main tumhara personal AI assistant hoon. ❤️

✨ Main ye kaam kar sakta hoon:

🧠 Questions & Answers
💻 Coding
📝 Writing
📚 Study
🌐 Translation
💡 Ideas
📐 Maths
📖 Story & Content
🧠 Permanent Memory

Bas apna sawaal bhejo aur main jawab dunga.

🚀 Let's start!
"""

    bot.reply_to(message, welcome)


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

        conversation += "\nUser: " + message.text

        response = client.models.generate_content(
    model="gemini-3.6-flash",
    contents=conversation,
    config=types.GenerateContentConfig(
        tools=[
            types.Tool(
                google_search=types.GoogleSearch()
            )
        ]
    )
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
