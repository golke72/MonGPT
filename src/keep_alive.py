from flask import Flask
from threading import Thread
import os
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/')
def home():
    """Главная страница для проверки работоспособности"""
    return "🤖 MonGPT is alive and running!"

@app.route('/health')
def health():
    """Health check для Render"""
    return {"status": "healthy"}, 200

def run():
    """Запуск Flask сервера"""
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Запускаю keep-alive сервер на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def keep_alive():
    """Запуск сервера в отдельном потоке"""
    logger.info("📡 Запускаю keep-alive поток...")
    t = Thread(target=run, daemon=True)
    t.start()
    logger.info("✅ Keep-alive поток запущен")
