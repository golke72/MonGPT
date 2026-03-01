import asyncio
import logging
import os
import random
import tempfile
import hashlib
import io
import re
import base64
import json
import urllib.parse
from typing import Dict, Optional, List
from collections import deque
from io import BytesIO
from datetime import datetime

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, Voice, VideoNote, Video, Audio,
    ReplyKeyboardMarkup, KeyboardButton,
    FSInputFile, BufferedInputFile,
    CallbackQuery, Document
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import yt_dlp
from PIL import Image
import cv2
import numpy as np
import matplotlib.pyplot as plt
from gtts import gTTS
from cachetools import TTLCache
from openai import AsyncOpenAI

# Попытка импорта опциональных библиотек
try:
    from pyzbar.pyzbar import decode
    PYZBAR_AVAILABLE = True
except ImportError:
    PYZBAR_AVAILABLE = False
    print("⚠️ pyzbar не установлен, QR-сканирование отключено")

try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False
    print("⚠️ qrcode не установлен, генерация QR отключена")

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    print("⚠️ pydub не установлен, конвертация аудио ограничена")

# Keep-alive
try:
    from src.keep_alive import keep_alive
except:
    def keep_alive(): pass

load_dotenv()
keep_alive()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== КОНФИГИ ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
AUDD_API_TOKEN = os.getenv("AUDD_API_TOKEN")
YOUR_USER_ID = int(os.getenv("YOUR_USER_ID", "0"))

if not BOT_TOKEN:
    raise ValueError("❌ Нет токена бота!")

# ========== ИНИЦИАЛИЗАЦИЯ ==========
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# OpenRouter клиент
if OPENROUTER_API_KEY:
    openrouter_client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
        default_headers={
            "HTTP-Referer": "https://github.com/MonGPT",
            "X-Title": "MonGPT"
        }
    )
else:
    openrouter_client = None

# ========== КЭШ И ХРАНИЛИЩА ==========
cache = TTLCache(maxsize=200, ttl=3600)
dialog_history: Dict[int, deque] = {}
MAX_HISTORY = 10
your_balance = 666_666_666

# ========== СИСТЕМНЫЙ ПРОМПТ ==========
SYSTEM_PROMPT = "Ты — MonGPT, бро-эксперт. Отвечай кратко и по делу. Используй эмодзи."

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard():
    builder = ReplyKeyboardBuilder()
    buttons = [
        ["🤖 Чат", "🎨 Рисунок"],
        ["🌐 Поиск", "🎵 Музыка"],
        ["🖼️ Фото", "📹 Видео"],
        ["💰 Баланс", "⚙️ Всё"]
    ]
    for row in buttons:
        builder.row(*[KeyboardButton(text=btn) for btn in row])
    return builder.as_markup(resize_keyboard=True)

def get_all_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔐 Пароль", callback_data="pass")
    builder.button(text="🔲 QR", callback_data="qr")
    builder.button(text="📈 График", callback_data="chart")
    builder.button(text="🌡️ Погода", callback_data="weather")
    builder.button(text="🎲 Рандом", callback_data="random")
    builder.button(text="📅 Дата", callback_data="date")
    builder.adjust(2)
    return builder.as_markup()

# ========== ОСНОВНЫЕ ФУНКЦИИ ==========
async def chat(prompt: str, model: str = "openrouter/free") -> str:
    """Умный чат через OpenRouter"""
    if not openrouter_client:
        return "❌ OpenRouter не настроен"
    
    cache_key = hashlib.md5(f"{prompt}_{model}".encode()).hexdigest()
    if cache_key in cache:
        return cache[cache_key]
    
    try:
        response = await openrouter_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0.7,
        )
        result = response.choices[0].message.content
        cache[cache_key] = result
        return result
    except Exception as e:
        logger.error(f"OpenRouter error: {e}")
        return f"❌ Ошибка: {e}"

async def download_file(file_id: str) -> str:
    file = await bot.get_file(file_id)
    dest = tempfile.NamedTemporaryFile(delete=False).name
    await bot.download_file(file.file_path, dest)
    return dest

async def search_web(query: str) -> str:
    """Поиск в интернете"""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            if results:
                return "\n\n".join([
                    f"🔗 <b>{r['title']}</b>\n{r['body'][:150]}...\n<a href='{r['href']}'>Ссылка</a>"
                    for r in results
                ])
    except Exception as e:
        logger.error(f"Search error: {e}")
    return "❌ Ничего не нашел"

async def transcribe_audio(file_path: str) -> str:
    """Распознавание речи через Gemini"""
    if not openrouter_client:
        return "OpenRouter не настроен"
    
    try:
        with open(file_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode()
        
        response = await openrouter_client.chat.completions.create(
            model="google/gemini-3-flash-preview:free",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Распознай речь в этом аудио"},
                    {"type": "audio_url", "audio_url": {"url": f"data:audio/mpeg;base64,{audio_b64}"}}
                ]
            }],
            max_tokens=512,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Transcribe error: {e}")
        return f"Ошибка: {e}"

async def recognize_music(file_path: str) -> Optional[dict]:
    """Распознавание музыки через AudD"""
    if not AUDD_API_TOKEN:
        return None
    
    try:
        with open(file_path, "rb") as f:
            audio_data = f.read()
        
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field('api_token', AUDD_API_TOKEN)
            data.add_field('file', audio_data, filename='audio.mp3', content_type='audio/mpeg')
            data.add_field('return', 'apple_music,spotify')
            
            async with session.post('https://api.audd.io/', data=data) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    if result.get('status') == 'success':
                        track = result.get('result', {})
                        if track:
                            return {
                                'title': track.get('title', 'Unknown'),
                                'artist': track.get('artist', 'Unknown'),
                                'album': track.get('album', 'Unknown')
                            }
    except Exception as e:
        logger.error(f"AudD error: {e}")
    return None

async def download_audio(query: str) -> Optional[str]:
    """Скачать MP3 с YouTube"""
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }],
        'outtmpl': 'temp/%(title)s.%(ext)s',
        'quiet': True,
        'default_search': 'ytsearch1',
    }
    
    try:
        os.makedirs('temp', exist_ok=True)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=True)
            if info:
                for file in os.listdir('temp'):
                    if file.endswith('.mp3'):
                        return os.path.join('temp', file)
    except Exception as e:
        logger.error(f"Audio download error: {e}")
    return None

async def download_video(url: str) -> Optional[str]:
    """Скачать MP4 с YouTube"""
    ydl_opts = {
        'format': 'best[ext=mp4]',
        'outtmpl': 'temp/%(title)s.%(ext)s',
        'quiet': True,
    }
    try:
        os.makedirs('temp', exist_ok=True)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if os.path.exists(filename):
                return filename
    except Exception as e:
        logger.error(f"Video download error: {e}")
    return None

async def analyze_image(file_path: str, prompt: str = "Что на этом изображении?") -> str:
    """Распознавание изображения через Gemini"""
    if not openrouter_client:
        return "OpenRouter не настроен"
    
    try:
        with open(file_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        
        response = await openrouter_client.chat.completions.create(
            model="google/gemini-3-flash-preview:free",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                ]
            }],
            max_tokens=512,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Ошибка: {e}"

async def image_to_sticker(file_path: str) -> BytesIO:
    """Создание стикера из фото"""
    try:
        img = Image.open(file_path)
        img.thumbnail((512, 512))
        output = BytesIO()
        img.save(output, format='PNG')
        output.seek(0)
        return output
    except Exception as e:
        logger.error(f"Sticker error: {e}")
        return None

async def enhance_image(file_path: str) -> BytesIO:
    """Улучшение качества фото"""
    try:
        img = cv2.imread(file_path)
        enhanced = cv2.convertScaleAbs(img, alpha=1.2, beta=10)
        _, buffer = cv2.imencode('.jpg', enhanced)
        return BytesIO(buffer)
    except Exception as e:
        logger.error(f"Enhance error: {e}")
        return None

async def generate_qr(data: str) -> Optional[BytesIO]:
    """Генерация QR-кода"""
    if not QRCODE_AVAILABLE:
        return None
    try:
        img = qrcode.make(data)
        output = BytesIO()
        img.save(output, format='PNG')
        output.seek(0)
        return output
    except Exception as e:
        logger.error(f"QR error: {e}")
        return None

async def scan_qr(file_path: str) -> Optional[str]:
    """Сканирование QR-кода"""
    if not PYZBAR_AVAILABLE:
        return None
    try:
        img = cv2.imread(file_path)
        qr_codes = decode(img)
        if qr_codes:
            return qr_codes[0].data.decode('utf-8')
    except Exception as e:
        logger.error(f"QR scan error: {e}")
    return None

def generate_password(length: int = 12) -> str:
    chars = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%&"
    return ''.join(random.choice(chars) for _ in range(length))

async def create_chart() -> BytesIO:
    """Создание графика"""
    plt.figure(figsize=(8, 4))
    x = list(range(7))
    y = [random.uniform(80, 100) for _ in range(7)]
    plt.plot(x, y, marker='o')
    plt.title('Курс USD/RUB')
    plt.grid(True)
    bio = BytesIO()
    plt.savefig(bio, format='png')
    bio.seek(0)
    plt.close()
    return bio

async def get_weather(city: str) -> str:
    """Получение погоды"""
    try:
        url = f"https://wttr.in/{city}?format=%t+%c+%w&m"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as resp:
                return await resp.text()
    except:
        return "Не удалось получить погоду"

def calculate(expression: str) -> Optional[str]:
    """Калькулятор"""
    try:
        expression = expression.replace(',', '.')
        safe = re.sub(r'[^0-9+\-*/().]', '', expression)
        result = eval(safe)
        return f"{result:.2f}"
    except:
        return None

# ========== ОБРАБОТЧИКИ КОМАНД ==========
@dp.message(Command("start"))
async def cmd_start(msg: Message):
    if msg.from_user.id == YOUR_USER_ID:
        welcome = f"👑 С возвращением, создатель! Баланс: {your_balance:,}"
    else:
        welcome = "🤙 Йоу, бро!"
    
    await msg.answer(
        f"{welcome}\n\n"
        f"🤖 <b>MonGPT</b> — 40+ функций\n"
        f"👇 Меню внизу",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "🤖 Чат")
async def cmd_chat(msg: Message):
    await msg.reply("💬 Напиши что хочешь — я отвечу")

@dp.message(F.text == "🎨 Рисунок")
async def cmd_draw(msg: Message):
    await msg.reply("🎨 Напиши что нарисовать (например: красный дракон)")

@dp.message(F.text == "🌐 Поиск")
async def cmd_search(msg: Message):
    await msg.reply("🔍 Напиши что искать (например: погода в Саранске)")

@dp.message(F.text == "🎵 Музыка")
async def cmd_music(msg: Message):
    await msg.reply("🎵 Напиши название песни, я найду и скачаю")

@dp.message(F.text == "🖼️ Фото")
async def cmd_photo(msg: Message):
    await msg.reply(
        "📸 <b>Отправь фото</b>\n"
        "• <code>что это</code> — опишу\n"
        "• <code>стикер</code> — сделаю стикер\n"
        "• <code>улучши</code> — повышу качество",
        parse_mode="HTML"
    )

@dp.message(F.text == "📹 Видео")
async def cmd_video(msg: Message):
    await msg.reply("🎥 Пришли ссылку на YouTube — скачаю")

@dp.message(F.text == "💰 Баланс")
async def cmd_balance(msg: Message):
    if msg.from_user.id == YOUR_USER_ID:
        await msg.reply(f"👑 Твой баланс: {your_balance:,}")
    else:
        await msg.reply("💰 Баланс: ∞")

@dp.message(F.text == "⚙️ Всё")
async def cmd_all(msg: Message):
    await msg.reply("🔧 Выбирай:", reply_markup=get_all_keyboard())

@dp.callback_query()
async def callbacks(call: CallbackQuery):
    if call.data == "pass":
        await call.message.edit_text(f"🔐 Пароль: <code>{generate_password()}</code>", parse_mode="HTML")
    elif call.data == "qr":
        await call.message.edit_text("🔲 Напиши 'qr текст' для генерации QR")
    elif call.data == "chart":
        chart = await create_chart()
        await call.message.delete()
        await call.message.answer_photo(BufferedInputFile(chart.getvalue(), "chart.png"))
    elif call.data == "weather":
        await call.message.edit_text("🌡️ Напиши 'погода Москва'")
    elif call.data == "random":
        await call.message.edit_text(f"🎲 {random.randint(1, 100)}")
    elif call.data == "date":
        await call.message.edit_text(f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    await call.answer()

@dp.message(Command("add_tokens"))
async def cmd_add_tokens(msg: Message):
    global your_balance
    if msg.from_user.id == YOUR_USER_ID:
        your_balance = 666_666_666
        await msg.reply("🔄 Баланс восстановлен")

# ========== ОСНОВНОЙ ОБРАБОТЧИК ==========
@dp.message()
async def handle_all(msg: Message):
    user_id = msg.from_user.id
    text = msg.text
    
    if not text or text in ["🤖 Чат", "🎨 Рисунок", "🌐 Поиск", "🎵 Музыка", "🖼️ Фото", "📹 Видео", "💰 Баланс", "⚙️ Всё"]:
        return
    
    await bot.send_chat_action(msg.chat.id, action="typing")
    
    # 1. РИСУНОК
    if "нарисуй" in text.lower() or "/draw" in text.lower():
        prompt = text.replace("нарисуй", "").replace("/draw", "").strip()
        if prompt:
            answer = await chat(f"Нарисуй: {prompt}", "stabilityai/stable-diffusion:free")
            await msg.reply(f"🎨 {answer}")
        return
    
    # 2. ПОИСК
    if any(w in text.lower() for w in ["найди", "погода", "курс", "новости"]):
        result = await search_web(text)
        await msg.reply(result, parse_mode="HTML", disable_web_page_preview=True)
        return
    
    # 3. QR
    if text.lower().startswith("qr "):
        data = text[3:].strip()
        if data:
            qr = await generate_qr(data)
            if qr:
                await msg.reply_photo(BufferedInputFile(qr.getvalue(), "qr.png"))
        return
    
    # 4. ПАРОЛЬ
    if "пароль" in text.lower() or "pass" in text.lower():
        nums = re.findall(r'\d+', text)
        length = int(nums[0]) if nums else 12
        await msg.reply(f"🔐 Пароль: <code>{generate_password(length)}</code>", parse_mode="HTML")
        return
    
    # 5. КАЛЬКУЛЯТОР
    if re.match(r'^[\d\s+\-*/().]+$', text):
        result = calculate(text)
        if result:
            await msg.reply(f"🧮 Результат: {result}")
            return
    
    # 6. ПОГОДА
    if "погода" in text.lower() and "в " in text.lower():
        city = text.lower().split("в ")[-1].strip()
        weather = await get_weather(city)
        await msg.reply(f"🌡️ <b>Погода в {city.title()}:</b>\n{weather}", parse_mode="HTML")
        return
    
    # 7. УМНЫЙ ЧАТ (ВСЁ ОСТАЛЬНОЕ)
    answer = await chat(text)
    await msg.reply(answer, parse_mode="HTML")

# ========== ОБРАБОТЧИК МЕДИА ==========
@dp.message(F.voice | F.video_note | F.audio)
async def handle_audio(msg: Message):
    user_id = msg.from_user.id
    await bot.send_chat_action(msg.chat.id, action="typing")
    loading = await msg.reply("⏳ Обрабатываю...")
    
    # Получаем file_id
    file_id = None
    if msg.voice:
        file_id = msg.voice.file_id
    elif msg.video_note:
        file_id = msg.video_note.file_id
    elif msg.audio:
        file_id = msg.audio.file_id
    
    if not file_id:
        await loading.delete()
        await msg.reply("❌ Не удалось получить аудио")
        return
    
    file_path = await download_file(file_id)
    
    # Сначала пробуем распознать музыку
    music = await recognize_music(file_path)
    if music:
        await loading.delete()
        await msg.reply(
            f"🎵 <b>Распознано:</b>\n"
            f"Название: {music['title']}\n"
            f"Исполнитель: {music['artist']}\n"
            f"Альбом: {music['album']}",
            parse_mode="HTML"
        )
        os.unlink(file_path)
        return
    
    # Если не музыка, распознаем речь
    recognized = await transcribe_audio(file_path)
    await loading.delete()
    await msg.reply(f"📝 <b>Распознал:</b>\n{recognized}", parse_mode="HTML")
    os.unlink(file_path)

@dp.message(F.video)
async def handle_video(msg: Message):
    await bot.send_chat_action(msg.chat.id, action="typing")
    loading = await msg.reply("⏳ Скачиваю видео...")
    
    url = msg.text if msg.text and "http" in msg.text else None
    if not url:
        await loading.delete()
        await msg.reply("❌ Пришли ссылку на YouTube")
        return
    
    file_path = await download_video(url)
    if file_path:
        await loading.delete()
        await msg.reply_video(FSInputFile(file_path))
        os.remove(file_path)
    else:
        await loading.delete()
        await msg.reply("❌ Не удалось скачать видео")

@dp.message(F.photo)
async def handle_photo(msg: Message):
    user_id = msg.from_user.id
    await bot.send_chat_action(msg.chat.id, action="typing")
    loading = await msg.reply("⏳ Обрабатываю фото...")
    
    file_id = msg.photo[-1].file_id
    file_path = await download_file(file_id)
    caption = msg.caption.lower() if msg.caption else ""
    
    # 1. Сканирование QR
    if "qr" in caption:
        qr_text = await scan_qr(file_path)
        if qr_text:
            await loading.delete()
            await msg.reply(f"🔲 QR: <code>{qr_text}</code>", parse_mode="HTML")
            os.unlink(file_path)
            return
    
    # 2. Стикер
    if "стикер" in caption:
        sticker = await image_to_sticker(file_path)
        if sticker:
            await loading.delete()
            await msg.reply_sticker(BufferedInputFile(sticker.getvalue(), "sticker.png"))
            os.unlink(file_path)
            return
    
    # 3. Улучшение
    if "улучши" in caption or "enhance" in caption:
        enhanced = await enhance_image(file_path)
        if enhanced:
            await loading.delete()
            await msg.reply_photo(BufferedInputFile(enhanced.getvalue(), "enhanced.jpg"), caption="🖼️ Улучшенное фото")
            os.unlink(file_path)
            return
    
    # 4. Анализ
    if "что это" in caption or "что на фото" in caption:
        analysis = await analyze_image(file_path)
        await loading.delete()
        await msg.reply(f"🖼️ {analysis}", parse_mode="HTML")
        os.unlink(file_path)
        return
    
    # 5. Просто фото
    await loading.delete()
    await msg.reply_photo(FSInputFile(file_path), caption="🖼️ Фото")
    os.unlink(file_path)

@dp.message(F.document)
async def handle_doc(msg: Message):
    await msg.reply("📄 Документ получен, обрабатываю...")
    # Здесь можно добавить обработку PDF, Word и т.д.

# ========== ЗАПУСК ==========
async def main():
    logger.info("🚀 MonGPT запущен с полным функционалом")
    os.makedirs('temp', exist_ok=True)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
