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
