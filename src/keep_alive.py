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
    return "🤖 MonGPT is alive and running!"

@app.route('/health')
def health():
    return {"status": "healthy", "service": "MonGPT"}, 200

def run():
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Запуск keep-alive сервера на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def keep_alive():
    logger.info("📡 Запуск keep-alive потока...")
    t = Thread(target=run, daemon=True)
    t.start()
    logger.info("✅ Keep-alive поток запущен")
