# 🤖 Dark AI - Advanced Telegram Bot

Dark AI is a powerful and multifunctional Telegram bot created by **MNX Pro Gaming**. It uses Google's Gemini AI to provide smart, natural conversations, along with built-in utility tools like a media downloader and a phone number checker.

## 🌟 Key Features
* **🤖 Advanced AI Chat:** Powered by Gemini 3.6 Flash for fast, human-like responses in Hindi, Hinglish, and English.
* **🧠 Permanent Memory:** Remembers past conversations securely using an SQLite database (`dark_ai_memory.db`).
* **📥 Media Downloader:** Instantly downloads videos and photos from various platforms using `yt-dlp`.
* **📱 Number Check:** Extracts public carrier, country, and region details for any provided phone number.
* **📊 Google Sheets Logging:** Automatically logs user interactions to a private Google Sheet via Webhook.

## 🛠️ Technology Stack
* **Language:** Python
* **Library:** `pyTelegramBotAPI` (Telebot)
* **AI Engine:** Google GenAI SDK
* **Database:** SQLite3 & Google Apps Script
* **Deployment:** Render 

## 🔐 Setup & Environment Variables
If you want to host this bot yourself, never put your keys in the code. Set these variables in your `.env` file or cloud dashboard (like Render/Replit):
* `BOT_TOKEN` = Your Telegram Bot Token (from BotFather)
* `GEMINI_API_KEY` = Your Google Gemini API Key
* `SHEET_SECRET` = Your custom secret code for Google Sheets verification
* `GOOGLE_SHEET_URL` = Your Google Apps Script Web App URL

## 👨‍💻 Developer
Developed & Maintained by **MNX Pro Gaming**.

