import os
import re
import sqlite3
import tempfile
from datetime import datetime
from threading import Thread

import requests
import pytz
import telebot
import yt_dlp
import phonenumbers
from phonenumbers import carrier, geocoder, NumberParseException
from ddgs import DDGS
from google import genai
from flask import Flask
from keep_alive import keep_alive


# ============================================================
# DARK AI - CENTRAL AI ROUTER STRUCTURE
#
# Telegram
#    ↓
# Message
#    ↓
# AI Intent Router
#    ↓
# ┌───────────────┬────────────────┐
# │   FEATURE     │      CHAT      │
# │       ↓       │        ↓       │
# │ Python Func.  │  Gemini AI     │
# │       ↓       │        ↓       │
# │    Result     │     Reply      │
# └───────┬───────┴────────┬───────┘
#         ↓                ↓
#              Telegram Reply
# ============================================================


# =========================
# CONFIG / API KEYS
# =========================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GOOGLE_SHEET_URL = os.environ.get("GOOGLE_SHEET_URL")
SHEET_SECRET = os.environ.get("SHEET_SECRET")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN missing")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY missing")


# =========================
# TELEGRAM + GEMINI
# =========================

bot = telebot.TeleBot(BOT_TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY)

AI_NAME = "Dark AI"


# =========================
# AI PERSONALITY
# =========================

SYSTEM_PROMPT = f"""
Tum {AI_NAME} ho, ek smart, friendly aur helpful AI assistant.

User se Hindi ya Hinglish mein naturally baat karo.
User English mein bole to English mein jawab de sakte ho.

Coding, study, writing, stories, translation, maths, ideas,
planning aur general questions mein help karo.

Jawab clear, useful aur seedha do.

User agar spelling, grammar, typing ya Hinglish mein galti kare,
to intended meaning samajhne ki koshish karo.

Example:
"aj kon sa din h" = "Aaj kaun sa din hai?"
"aaj ki det kya h" = "Aaj ki date kya hai?"
"mausam delhi btao" = "Delhi ka weather batao"
"""


# ============================================================
# 1. WEB SEARCH
# ============================================================

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
        print("WEB SEARCH ERROR:", e)
        return []


# ============================================================
# 2. DATE / TIME
# ============================================================

def get_india_datetime():
    try:
        tz = pytz.timezone("Asia/Kolkata")
        now = datetime.now(tz)

        days = {
            "Monday": "सोमवार",
            "Tuesday": "मंगलवार",
            "Wednesday": "बुधवार",
            "Thursday": "गुरुवार",
            "Friday": "शुक्रवार",
            "Saturday": "शनिवार",
            "Sunday": "रविवार"
        }

        day_en = now.strftime("%A")

        return (
            "🇮🇳 India Time\n\n"
            f"📅 Date: {now.strftime('%d-%m-%Y')}\n"
            f"📆 Day: {days.get(day_en, day_en)} ({day_en})\n"
            f"🕐 Time: {now.strftime('%I:%M:%S %p')}"
        )

    except Exception as e:
        return f"❌ Date/Time error: {e}"


# ============================================================
# 3. WEATHER
# ============================================================

def get_weather(city):
    try:
        geo_url = "https://geocoding-api.open-meteo.com/v1/search"

        geo_response = requests.get(
            geo_url,
            params={
                "name": city,
                "count": 1,
                "language": "en",
                "format": "json"
            },
            timeout=10
        )

        geo_response.raise_for_status()
        geo_data = geo_response.json()

        if not geo_data.get("results"):
            return None

        location = geo_data["results"][0]

        latitude = location["latitude"]
        longitude = location["longitude"]
        city_name = location["name"]
        country = location.get("country", "")

        weather_url = "https://api.open-meteo.com/v1/forecast"

        weather_response = requests.get(
            weather_url,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": (
                    "temperature_2m,"
                    "relative_humidity_2m,"
                    "apparent_temperature,"
                    "precipitation,"
                    "weather_code,"
                    "wind_speed_10m"
                ),
                "timezone": "auto"
            },
            timeout=10
        )

        weather_response.raise_for_status()
        current = weather_response.json().get("current")

        if not current:
            return None

        return {
            "city": city_name,
            "country": country,
            "temperature": current.get("temperature_2m"),
            "feels_like": current.get("apparent_temperature"),
            "humidity": current.get("relative_humidity_2m"),
            "precipitation": current.get("precipitation"),
            "wind": current.get("wind_speed_10m"),
            "weather_code": current.get("weather_code")
        }

    except Exception as e:
        print("WEATHER ERROR:", e)
        return None


def weather_reply(city):
    city = city.strip()

    if not city:
        return (
            "🌦️ Weather ke liye city ka naam likho.\n\n"
            "Example:\n"
            "• Delhi ka weather batao\n"
            "• Mumbai mausam\n"
            "• मौसम Panipat"
        )

    result = get_weather(city)

    if not result:
        return "❌ Is city ka weather nahi mil paya."

    return (
        "🌦️ Live Weather\n\n"
        f"📍 Location: {result['city']}, {result['country']}\n"
        f"🌡️ Temperature: {result['temperature']}°C\n"
        f"🤔 Feels Like: {result['feels_like']}°C\n"
        f"💧 Humidity: {result['humidity']}%\n"
        f"🌧️ Precipitation: {result['precipitation']} mm\n"
        f"💨 Wind Speed: {result['wind']} km/h\n\n"
        "🤖 Dark AI"
    )


# ============================================================
# 4. CURRENCY
# ============================================================

def convert_currency(amount, from_currency, to_currency):
    try:
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        url = (
            f"https://api.frankfurter.dev/v2/rate/"
            f"{from_currency}/{to_currency}"
        )

        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            return None

        data = response.json()
        rate = data.get("rate")

        if rate is None:
            return None

        rate = float(rate)
        converted = amount * rate

        return converted, rate

    except Exception as e:
        print("CURRENCY ERROR:", e)
        return None


def extract_currency(text):
    """
    Examples:
    100 USD INR
    100 dollar INR
    100 USD to INR
    100 dollar ko rupees me badlo
    """

    upper = text.upper()

    match = re.search(
        r"(\d+(?:\.\d+)?)\s*([A-Z]{3})\s*(?:TO|IN|ME|KO)?\s*([A-Z]{3})",
        upper
    )

    if match:
        return float(match.group(1)), match.group(2), match.group(3)

    # Common natural-language forms
    amount_match = re.search(r"\b(\d+(?:\.\d+)?)\b", text)

    if not amount_match:
        return None

    amount = float(amount_match.group(1))
    lower = text.lower()

    if any(x in lower for x in ["dollar", "usd"]):
        from_currency = "USD"
    elif any(x in lower for x in ["rupee", "rupees", "रुपये", "रुपया", "inr"]):
        from_currency = "INR"
    elif any(x in lower for x in ["euro", "eur"]):
        from_currency = "EUR"
    elif any(x in lower for x in ["pound", "gbp"]):
        from_currency = "GBP"
    else:
        from_currency = None

    if any(x in lower for x in ["rupee", "rupees", "रुपये", "रुपया", "inr"]):
        to_currency = "INR"
    elif any(x in lower for x in ["dollar", "usd"]):
        to_currency = "USD"
    elif any(x in lower for x in ["euro", "eur"]):
        to_currency = "EUR"
    elif any(x in lower for x in ["pound", "gbp"]):
        to_currency = "GBP"
    else:
        to_currency = None

    if from_currency and to_currency and from_currency != to_currency:
        return amount, from_currency, to_currency

    return None


def currency_reply(text):
    data = extract_currency(text)

    if not data:
        return (
            "💰 Currency Converter\n\n"
            "Example:\n"
            "/currency 100 USD INR\n\n"
            "Ya:\n"
            "100 dollar ko rupees me badlo"
        )

    amount, from_currency, to_currency = data

    result = convert_currency(
        amount,
        from_currency,
        to_currency
    )

    if not result:
        return "❌ Currency rate nahi mil paya."

    converted, rate = result

    return (
        "💰 Currency Converter\n\n"
        f"💵 Amount: {amount:g} {from_currency}\n"
        f"🔄 Rate: 1 {from_currency} = {rate:.4f} {to_currency}\n"
        f"💸 Result: {converted:.2f} {to_currency}\n\n"
        "🤖 Dark AI"
    )


# ============================================================
# 5. PHONE NUMBER CHECK
# ============================================================

def extract_phone_number(text):
    if not text:
        return None

    match = re.search(
        r"(?<!\d)(\+?\d[\d\s\-()]{7,}\d)(?!\d)",
        text
    )

    if match:
        return match.group(1).strip()

    return None


def check_phone_number(phone):
    try:
        cleaned_phone = re.sub(r"[\s\-()]", "", phone)

        # India default region if +91 is not supplied.
        region = "IN" if not cleaned_phone.startswith("+") else None

        parsed = phonenumbers.parse(cleaned_phone, region)
        valid = phonenumbers.is_valid_number(parsed)

        country = geocoder.country_name_for_number(parsed, "en")
        region_name = geocoder.description_for_number(parsed, "en")
        carrier_name = carrier.name_for_number(parsed, "en")

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
            "region": region_name or "Unknown"
        }

    except NumberParseException:
        return None


def phone_reply(text):
    phone = extract_phone_number(text)

    if not phone:
        return (
            "📱 Number Check\n\n"
            "Phone number bhejo.\n\n"
            "Example:\n"
            "+919696712836"
        )

    result = check_phone_number(phone)

    if not result:
        return "❌ Number ko samajh nahi paaya.\nExample: +919876543210"

    valid_text = "Yes" if result["valid"] else "No"

    return (
        "📱 Number Check\n\n"
        f"Number: {phone}\n"
        f"✅ Valid: {valid_text}\n"
        f"🌍 Country: {result['country']}\n"
        f"📡 Carrier: {result['carrier']}\n"
        f"📱 Type: {result['type']}\n"
        f"📍 Region: {result['region']}\n\n"
        "🔎 Public Information\n"
        "Name: Public source se available nahi\n"
        "Business: Public source se available nahi\n"
        "Website: Public source se available nahi\n"
        "Spam reports: Public source se available nahi\n\n"
        "⚠️ Sirf publicly available information dikhayi gayi hai."
    )


# ============================================================
# 6. DOWNLOADER
# ============================================================

def is_url(text):
    return bool(
        re.match(
            r"^https?://",
            text.strip(),
            re.IGNORECASE
        )
    )


def extract_url(text):
    match = re.search(
        r"https?://[^\s]+",
        text,
        re.IGNORECASE
    )

    return match.group(0) if match else None


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

        if file_size > 50 * 1024 * 1024:
            bot.edit_message_text(
                "❌ File 50 MB se badi hai.\n"
                "Please chhota video/link try karo.",
                message.chat.id,
                status.message_id
            )

            try:
                os.remove(file_path)
            except OSError:
                pass

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

        try:
            os.remove(file_path)
        except OSError:
            pass

        try:
            bot.delete_message(
                message.chat.id,
                status.message_id
            )
        except Exception:
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


# ============================================================
# 7. PERMANENT MEMORY
# ============================================================

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


# ============================================================
# 8. GOOGLE SHEETS
# ============================================================

def save_to_google_sheet(user_id, username, message, reply):
    if not GOOGLE_SHEET_URL:
        return

    try:
        data = {
            "secret": SHEET_SECRET,
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
        print("GOOGLE SHEET ERROR:", e)


# ============================================================
# 9. AI INTENT ROUTER
# ============================================================

ALLOWED_INTENTS = {
    "TIME",
    "DATE",
    "WEATHER",
    "CURRENCY",
    "WEB_SEARCH",
    "DOWNLOAD",
    "PHONE_NUMBER",
    "CHAT"
}


def detect_intent(text):
    try:
        prompt = f"""
Tum Dark AI ke CENTRAL INTENT ROUTER ho.

User ke message ka meaning samjho.
Spelling, grammar aur Hinglish mistakes ignore karo.

Sirf inme se EK intent return karo:

TIME
DATE
WEATHER
CURRENCY
WEB_SEARCH
DOWNLOAD
PHONE_NUMBER
CHAT

Rules:

TIME:
- Abhi ka time poocha ho.
- "kitne baje", "time batao", "india ka time".

DATE:
- Aaj ki date, day, din poocha ho.
- "aaj kaun sa din hai", "aaj ki date kya hai".

WEATHER:
- Kisi city ka weather/mausam/temperature poocha ho.

CURRENCY:
- Currency conversion ya exchange rate poocha ho.

WEB_SEARCH:
- Latest/current/live/news/result information chahiye.
- Aisi information jo internet se verify karni zaroori ho.

DOWNLOAD:
- Video/photo/media download karne ko bola ho.
- Message mein URL ho aur download intent ho.

PHONE_NUMBER:
- Phone number check/validate/carrier/region ke baare mein poocha ho.

CHAT:
- Baaki sab normal AI conversation.

IMPORTANT:
- Sirf intent ka naam return karo.
- Extra text mat likho.

Examples:

"aj kon sa din h" -> DATE
"aaj ki det kya h" -> DATE
"abhi kitne baje hain" -> TIME
"delhi ka mausam kaisa hai" -> WEATHER
"100 dollar ko rupees me badlo" -> CURRENCY
"india ki latest news batao" -> WEB_SEARCH
"ye video download krdo https://example.com/x" -> DOWNLOAD
"download karo https://example.com/x" -> DOWNLOAD
"is number ko check kro +919876543210" -> PHONE_NUMBER
"python kya hai" -> CHAT

User message:
{text}
"""

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt
        )

        intent = (response.text or "").strip().upper()

        # Gemini kabhi extra text de de to first valid intent pick karo.
        for allowed in ALLOWED_INTENTS:
            if allowed in intent:
                return allowed

        return "CHAT"

    except Exception as e:
        print("INTENT ROUTER ERROR:", e)

        # Gemini unavailable ho to basic safe fallback.
        lower = text.lower()

        if extract_phone_number(text):
            return "PHONE_NUMBER"

        if extract_url(text) and any(
            x in lower
            for x in [
                "download",
                "डाउनलोड",
                "video download",
                "photo download"
            ]
        ):
            return "DOWNLOAD"

        if any(
            x in lower
            for x in [
                "weather",
                "मौसम",
                "mausam",
                "temperature",
                "तापमान"
            ]
        ):
            return "WEATHER"

        if any(
            x in lower
            for x in [
                "latest",
                "news",
                "न्यूज़",
                "समाचार",
                "live",
                "current",
                "आज की खबर"
            ]
        ):
            return "WEB_SEARCH"

        if any(
            x in lower
            for x in [
                "time",
                "समय",
                "kitne baje",
                "india ka time"
            ]
        ):
            return "TIME"

        if any(
            x in lower
            for x in [
                "date",
                "दिन",
                "तारीख",
                "tarikh",
                "aaj ki date"
            ]
        ):
            return "DATE"

        return "CHAT"


# ============================================================
# 10. FEATURE EXTRACTION HELPERS
# ============================================================

def extract_city(text):
    lower = text.lower().strip()

    patterns = [
        r"(?:weather|मौसम|mausam)\s+(?:of\s+|in\s+|ka\s+|ki\s+)?(.+)$",
        r"(.+?)\s+(?:ka|ki|ke)\s+(?:weather|mausam)\s*(?:batao|bata|बताओ)?$",
        r"(?:weather|मौसम)\s+(.+)$"
    ]

    for pattern in patterns:
        match = re.search(pattern, lower, re.IGNORECASE)

        if match:
            city = match.group(1).strip()

            city = re.sub(
                r"\b(batao|bata|please|plz|today|aaj|kaisa|kaisi|hai|h)\b",
                "",
                city,
                flags=re.IGNORECASE
            ).strip()

            if city:
                return city

    # Last fallback: remove common weather words.
    city = re.sub(
        r"\b(weather|mausam|temperature|forecast)\b|मौसम|तापमान",
        "",
        lower,
        flags=re.IGNORECASE
    ).strip()

    return city


# ============================================================
# 11. WEB SEARCH + GEMINI SUMMARY
# ============================================================

def web_search_answer(message):
    results = web_search(message.text, 5)

    if not results:
        return "❌ Search results nahi mile."

    web_context = "\n\n".join(
        f"Source {i}:\n"
        f"Title: {r['title']}\n"
        f"Content: {r['body']}\n"
        f"URL: {r['url']}"
        for i, r in enumerate(results, 1)
    )

    prompt = f"""
{SYSTEM_PROMPT}

User ka question:
{message.text}

Internet search results:
{web_context}

Instructions:
- Sirf diye gaye search results ka use karo.
- Search results mein jo information hai uska concise answer do.
- Information invent mat karo.
- Important source URL include karo.
- Hindi/Hinglish mein answer do.
"""

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt
    )

    return response.text or "❌ Answer generate nahi ho paya."


# ============================================================
# 12. NORMAL GEMINI CHAT
# ============================================================

def chat_answer(user_id, text):
    history = get_memory(user_id, 10)

    conversation = SYSTEM_PROMPT + "\n\n"

    for role, old_text in history:
        conversation += f"{role}: {old_text}\n"

    conversation += f"\nUser: {text}\nDark AI:"

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=conversation
    )

    return response.text or "❌ Answer generate nahi ho paya."


# ============================================================
# 13. CENTRAL FEATURE DISPATCHER
# ============================================================

def handle_feature(message, intent):
    """
    Ye function poore bot ka central controller hai.

    Telegram message
          ↓
      detect_intent()
          ↓
      handle_feature()
          ↓
    correct Python function
    """

    text = message.text.strip()

    if intent == "TIME":
        return get_india_datetime()

    if intent == "DATE":
        return get_india_datetime()

    if intent == "WEATHER":
        city = extract_city(text)
        return weather_reply(city)

    if intent == "CURRENCY":
        return currency_reply(text)

    if intent == "WEB_SEARCH":
        return web_search_answer(message)

    if intent == "DOWNLOAD":
        url = extract_url(text)

        if not url:
            return (
                "📥 Downloader\n\n"
                "Video/photo ka link bhejo.\n"
                "Example:\n"
                "Download this video https://example.com/video"
            )

        process_download(message, url)
        return None

    if intent == "PHONE_NUMBER":
        return phone_reply(text)

    return None


# ============================================================
# 14. START MENU
# ============================================================

@bot.message_handler(commands=["start"])
def start_command(message):
    welcome = f"""
🤖 Welcome to {AI_NAME}! ❤️

Main tumhara personal AI assistant hoon.

Tum simple language mein message bhejo.
AI khud decide karega ki:
• Feature chalana hai
• Ya Gemini AI se chat karni hai

Examples:
🕐 "abhi kitne baje hain"
📅 "aaj ki date kya hai"
🌦️ "Delhi ka mausam batao"
💰 "100 USD INR"
🌐 "India ki latest news batao"
📥 "ye video download karo <link>"
📱 "is number ko check karo +919876543210"
🤖 "Python kya hai?"
"""

    markup = telebot.types.InlineKeyboardMarkup(row_width=2)

    btn_ai = telebot.types.InlineKeyboardButton(
        "🤖 AI Chat",
        callback_data="ai_chat"
    )

    btn_download = telebot.types.InlineKeyboardButton(
        "📥 Downloader",
        callback_data="downloader"
    )

    btn_number = telebot.types.InlineKeyboardButton(
        "📱 Number Check",
        callback_data="number_check"
    )

    btn_tools = telebot.types.InlineKeyboardButton(
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


# ============================================================
# 15. MENU CALLBACK
# ============================================================

@bot.callback_query_handler(func=lambda call: True)
def menu_callback(call):
    bot.answer_callback_query(call.id)

    if call.data == "ai_chat":
        bot.send_message(
            call.message.chat.id,
            "🤖 AI Chat active hai.\n\n"
            "Apna sawaal bhejo, Dark AI khud answer dega."
        )

    elif call.data == "downloader":
        bot.send_message(
            call.message.chat.id,
            "📥 Downloader\n\n"
            "Video/photo ka link bhejo.\n"
            "Example:\n"
            "Download this video https://example.com/video"
        )

    elif call.data == "number_check":
        bot.send_message(
            call.message.chat.id,
            "📱 Number Check\n\n"
            "Phone number bhejo.\n"
            "Example: +919696712836"
        )

    elif call.data == "tools":
        bot.send_message(
            call.message.chat.id,
            "🛠️ Tools\n\n"
            "📥 Video/Photo Downloader\n"
            "📱 Number Check\n"
            "🌦️ Live Weather\n"
            "💰 Currency Converter\n"
            "🌐 Web Search\n"
            "🕐 India Time\n"
            "🧠 Permanent Memory\n"
            "🤖 AI Assistant"
        )


# ============================================================
# 16. COMMANDS
# ============================================================

@bot.message_handler(commands=["time", "india_time"])
def time_command(message):
    bot.send_chat_action(message.chat.id, "typing")
    bot.reply_to(message, get_india_datetime())


@bot.message_handler(commands=["currency"])
def currency_command(message):
    text = message.text.replace("/currency", "", 1).strip()

    if not text:
        bot.reply_to(
            message,
            "💰 Use:\n/currency 100 USD INR"
        )
        return

    bot.send_chat_action(message.chat.id, "typing")
    bot.reply_to(message, currency_reply(text))


@bot.message_handler(commands=["search"])
def search_command(message):
    query = message.text.replace("/search", "", 1).strip()

    if not query:
        bot.reply_to(
            message,
            "🌐 Use:\n/search आज की भारत की खबरें"
        )
        return

    try:
        bot.send_chat_action(message.chat.id, "typing")
        results = web_search(query, 5)

        if not results:
            bot.reply_to(message, "❌ Search results nahi mile.")
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
        print("SEARCH COMMAND ERROR:", e)
        bot.reply_to(message, "❌ Web Search Error.")


@bot.message_handler(commands=["download"])
def download_command(message):
    text = message.text.replace("/download", "", 1).strip()
    url = extract_url(text)

    if not url:
        bot.reply_to(
            message,
            "📥 Use:\n/download <video/photo link>"
        )
        return

    process_download(message, url)


@bot.message_handler(commands=["clear"])
def clear_command(message):
    clear_memory(message.from_user.id)

    bot.reply_to(
        message,
        "🧠 Tumhari memory clear kar di gayi hai!"
    )


# ============================================================
# 17. IMAGE AI
# ============================================================

@bot.message_handler(content_types=["photo"])
def image_ai_handler(message):
    try:
        bot.send_chat_action(
            message.chat.id,
            "typing"
        )

        file_info = bot.get_file(
            message.photo[-1].file_id
        )

        image_bytes = bot.download_file(
            file_info.file_path
        )

        prompt = message.caption or (
            "Is image ko dhyan se analyze karo. "
            "Image mein kya dikh raha hai, important details batao. "
            "Agar image mein text hai to uska bhi batao. "
            "Hindi/Hinglish mein jawab do."
        )

        response = None
        last_error = None

        models = [
            "gemini-3.6-flash",
            "gemini-3.7-flash",
            "gemini-3.5-flash"
        ]

        for model_name in models:
            try:
                print("Trying image model:", model_name)

                response = client.models.generate_content(
                    model=model_name,
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

                break

            except Exception as e:
                last_error = e
                print("IMAGE MODEL FAILED:", model_name, e)

        if response is None:
            print("ALL IMAGE MODELS FAILED:", last_error)
            bot.reply_to(
                message,
                "❌ Abhi image analysis available nahi hai.\n"
                "Thodi der baad dobara try karo."
            )
            return

        answer = response.text or "❌ Image ka answer generate nahi ho paya."

        bot.send_message(
            message.chat.id,
            "🖼️ Dark AI Image Analysis\n\n" + answer,
            parse_mode=None
        )

    except Exception as e:
        print("IMAGE AI ERROR:", e)

        bot.reply_to(
            message,
            "❌ Image analyze nahi ho payi."
        )


# ============================================================
# 18. VOICE AI
# ============================================================

@bot.message_handler(content_types=["voice"])
def voice_handler(message):
    """
    Voice bhi AI chat pipeline mein jayegi:
    Voice -> Speech to Text -> Central AI Chat
    """

    ogg_path = None
    wav_path = None

    try:
        bot.send_chat_action(
            message.chat.id,
            "typing"
        )

        file_info = bot.get_file(
            message.voice.file_id
        )

        voice_data = bot.download_file(
            file_info.file_path
        )

        with tempfile.NamedTemporaryFile(
            suffix=".ogg",
            delete=False
        ) as temp_file:
            temp_file.write(voice_data)
            ogg_path = temp_file.name

        from pydub import AudioSegment
        import speech_recognition as sr

        wav_path = ogg_path.replace(".ogg", ".wav")

        audio = AudioSegment.from_ogg(ogg_path)
        audio.export(wav_path, format="wav")

        recognizer = sr.Recognizer()

        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)

        text = recognizer.recognize_google(
            audio_data,
            language="hi-IN"
        )

        # Voice converted to text, then same normal AI pipeline.
        answer = process_ai_text(
            message,
            text,
            save_original=False
        )

        if answer:
            bot.reply_to(
                message,
                "🎤 आपने कहा:\n"
                f"{text}\n\n"
                "🤖 Dark AI:\n"
                f"{answer}"
            )

    except Exception as e:
        print("VOICE ERROR:", e)

        bot.reply_to(
            message,
            "❌ Voice process nahi ho payi.\n"
            "Please dobara clearly bolkar bhejo."
        )

    finally:
        for path in [ogg_path, wav_path]:
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass


# ============================================================
# 19. CENTRAL TEXT PROCESSOR
# ============================================================

def process_ai_text(message, text, save_original=True):
    """
    MAIN PIPELINE:

    Telegram message
           ↓
    detect_intent(text)
           ↓
    ┌───────────────┐
    │    FEATURE    │
    └───────┬───────┘
            ↓
       Python function
            ↓
          Result

    OR

    ┌───────────────┐
    │     CHAT      │
    └───────┬───────┘
            ↓
        Gemini AI
            ↓
          Answer
    """

    user_id = message.from_user.id
    text = text.strip()

    if not text:
        return "❌ Empty message."

    bot.send_chat_action(
        message.chat.id,
        "typing"
    )

    # --------------------------------------------
    # STEP 1: AI understands user intent
    # --------------------------------------------
    intent = detect_intent(text)

    print(
        f"🧠 Intent | user={user_id} | "
        f"intent={intent} | text={text}"
    )

    # --------------------------------------------
    # STEP 2: Feature route
    # --------------------------------------------
    if intent != "CHAT":
        # Feature handlers need message.text.
        original_text = message.text

        try:
            message.text = text
            result = handle_feature(message, intent)
        finally:
            message.text = original_text

        # DOWNLOAD sends its own Telegram response.
        if result is None:
            return None

        answer = result

    # --------------------------------------------
    # STEP 3: Normal Gemini chat
    # --------------------------------------------
    else:
        answer = chat_answer(
            user_id,
            text
        )

    # --------------------------------------------
    # STEP 4: Memory
    # --------------------------------------------
    if save_original:
        add_memory(
            user_id,
            "User",
            text
        )

    add_memory(
        user_id,
        "Dark AI",
        answer
    )

    # --------------------------------------------
    # STEP 5: Google Sheet
    # --------------------------------------------
    save_to_google_sheet(
        user_id,
        message.from_user.username or "",
        text,
        answer
    )

    return answer


# ============================================================
# 20. ONE CENTRAL TEXT HANDLER
# ============================================================

@bot.message_handler(content_types=["text"])
def central_text_handler(message):
    """
    IMPORTANT:
    Is bot mein text ke liye sirf EK central handler hai.

    Purane alag-alag:
    - weather text handler
    - phone text handler
    - URL downloader handler
    - time text handler
    - catch-all AI handler

    sabko combine karke yahan route kiya gaya hai.
    """

    try:
        answer = process_ai_text(
            message,
            message.text
        )

        if answer:
            bot.reply_to(
                message,
                answer,
                disable_web_page_preview=True
            )

    except Exception as e:
        print("CENTRAL AI ERROR:", e)

        bot.reply_to(
            message,
            "❌ AI Error:\n" + str(e)
        )


# ============================================================
# 21. START BOT
# ============================================================

print("==========================================")
print("🤖 DARK AI")
print("🧠 Central AI Intent Router: ON")
print("🛠️ Feature Dispatcher: ON")
print("💬 Gemini Chat: ON")
print("==========================================")

keep_alive()

bot.infinity_polling(
    skip_pending=True,
    timeout=30,
    long_polling_timeout=30
)
