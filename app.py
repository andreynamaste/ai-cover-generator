#!/usr/bin/env python3
"""
🎨 AI Cover Generator - Генератор обложек для социальных сетей
С системой регистрации, личными API токенами и Google OAuth
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
from flask_cors import CORS
from authlib.integrations.flask_client import OAuth
from werkzeug.utils import secure_filename
import requests
import time
import os
import uuid
import hashlib
import sqlite3
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-super-secret-key-change-me-in-production-12345')
app.config['PERMANENT_SESSION_LIFETIME'] = 86400 * 30  # 30 дней
# SESSION_COOKIE_SECURE только на HTTPS (проверяем по переменной окружения или hostname)
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Защита от XSS
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Защита от CSRF
CORS(app)

# Устанавливаем SESSION_COOKIE_SECURE только если не localhost
import socket
hostname = socket.gethostname()
if 'localhost' not in hostname and '127.0.0.1' not in hostname:
    app.config['SESSION_COOKIE_SECURE'] = True

# ============ GOOGLE OAUTH CONFIG ============
# Для настройки Google OAuth:
# 1. Зайдите на https://console.cloud.google.com/
# 2. Создайте проект
# 3. APIs & Services -> Credentials -> Create Credentials -> OAuth Client ID
# 4. Добавьте Authorized redirect URI: https://2msp.webversy.top/covers/auth/google/callback
# 5. Скопируйте Client ID и Client Secret

GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')

oauth = OAuth(app)

if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    google = oauth.register(
        name='google',
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )
else:
    google = None

# Конфигурация
class Config:
    KIE_API_URL = "https://api.kie.ai/api/v1/jobs"
    OUTPUT_FOLDER = "/tmp/cover-generator"
    UPLOAD_FOLDER = "/var/www/cover-generator/uploads"
    DATABASE = "/var/www/cover-generator/users.db"
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

os.makedirs(Config.OUTPUT_FOLDER, exist_ok=True)
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = Config.UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = Config.MAX_CONTENT_LENGTH

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect(Config.DATABASE, timeout=60, check_same_thread=False)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=60000')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            google_id TEXT,
            api_token TEXT,
            openai_token TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            generations_count INTEGER DEFAULT 0
        )
    ''')
    # Добавляем колонку openai_token если её нет
    try:
        c.execute('ALTER TABLE users ADD COLUMN openai_token TEXT')
    except:
        pass
    c.execute('''
        CREATE TABLE IF NOT EXISTS generations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task_id TEXT,
            platform TEXT,
            style TEXT,
            prompt TEXT,
            status TEXT,
            image_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            token TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    # Добавляем колонку google_id если её нет
    try:
        c.execute('ALTER TABLE users ADD COLUMN google_id TEXT')
    except:
        pass
    conn.commit()
    conn.close()

init_db()

def get_db():
    """Получить соединение с БД с правильными настройками для многопользовательского доступа"""
    conn = sqlite3.connect(
        Config.DATABASE, 
        timeout=60,  # Увеличенный таймаут
        check_same_thread=False,  # Разрешить многопоточность
        isolation_level=None  # Autocommit режим
    )
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=60000')  # 60 секунд ожидания при блокировке
    conn.execute('PRAGMA synchronous=NORMAL')  # Быстрее, но безопасно
    return conn

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

def fix_prompt_with_openai(prompt, openai_token):
    """Исправляет промпт используя OpenAI API"""
    try:
        headers = {
            'Authorization': f'Bearer {openai_token}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {
                    "role": "system",
                    "content": "Ты помощник для исправления промптов для генерации изображений. Исправь все ошибки, опечатки, сделай текст понятным, профессиональным и читаемым. Сохрани смысл и идею, но улучши формулировку. Ответь ТОЛЬКО исправленным текстом, без дополнительных комментариев."
                },
                {
                    "role": "user",
                    "content": f"Исправь этот промпт для генерации изображения: {prompt}"
                }
            ],
            "temperature": 0.3,
            "max_tokens": 500
        }
        
        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers=headers,
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            fixed_prompt = result['choices'][0]['message']['content'].strip()
            return fixed_prompt
        else:
            print(f"OpenAI API error: {response.status_code}")
            return None
    except Exception as e:
        print(f"OpenAI error: {e}")
        return None

def fix_prompt_errors(prompt, openai_token=None):
    """
    Исправляет ошибки в промпте:
    - Сначала пытается использовать OpenAI если токен есть
    - Иначе использует бесплатный метод
    """
    if not prompt:
        return prompt
    
    # Пытаемся использовать OpenAI если токен есть
    if openai_token:
        fixed = fix_prompt_with_openai(prompt, openai_token)
        if fixed:
            return fixed
    
    # Бесплатный метод исправления
    # Убираем лишние пробелы
    prompt = ' '.join(prompt.split())
    
    # Убираем двойные запятые
    prompt = re.sub(r',{2,}', ',', prompt)
    
    # Убираем запятые перед точками
    prompt = re.sub(r',\s*\.', '.', prompt)
    
    # Исправляем частые опечатки
    replacements = {
        'релакму': 'релаксацию',
        'релакм': 'релаксация',
        'йоге': 'йоге',
        'сделай': 'создай',
        'пост про': 'пост о',
        'банер': 'баннер',
        'обложка для': 'обложка',
        'картинка': 'изображение',
        'фото': 'фотография',
        'ошибки': 'ошибки',
        'исправь': 'исправь',
        'текст': 'текст'
    }
    
    for wrong, correct in replacements.items():
        prompt = re.sub(r'\b' + wrong + r'\b', correct, prompt, flags=re.IGNORECASE)
    
    # Убираем лишние запятые в конце
    prompt = prompt.rstrip(',. ')
    
    # Первая буква заглавная
    if prompt and prompt[0].islower():
        prompt = prompt[0].upper() + prompt[1:]
    
    return prompt

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/covers/login')
        return f(*args, **kwargs)
    return decorated_function

# Размеры для разных соц сетей
SOCIAL_MEDIA_SIZES = {
    "youtube_banner": {
        "name": "YouTube Баннер канала",
        "width": 2560, "height": 1440,
        "aspect_ratio": "16:9", "resolution": "4K",
        "description": "Шапка канала YouTube", "icon": "📺"
    },
    "youtube_thumbnail": {
        "name": "YouTube Превью",
        "width": 1280, "height": 720,
        "aspect_ratio": "16:9", "resolution": "2K",
        "description": "Превью для видео", "icon": "🎬"
    },
    "facebook_cover": {
        "name": "Facebook Обложка",
        "width": 820, "height": 312,
        "aspect_ratio": "21:9", "resolution": "1K",
        "description": "Обложка страницы Facebook", "icon": "📘"
    },
    "facebook_post": {
        "name": "Facebook Пост",
        "width": 1200, "height": 630,
        "aspect_ratio": "16:9", "resolution": "2K",
        "description": "Изображение для поста", "icon": "📰"
    },
    "instagram_post": {
        "name": "Instagram Пост",
        "width": 1080, "height": 1080,
        "aspect_ratio": "1:1", "resolution": "2K",
        "description": "Квадратный пост Instagram", "icon": "📷"
    },
    "instagram_story": {
        "name": "Instagram Stories",
        "width": 1080, "height": 1920,
        "aspect_ratio": "9:16", "resolution": "2K",
        "description": "Сторис Instagram/Reels", "icon": "📱"
    },
    "instagram_portrait": {
        "name": "Instagram Портрет",
        "width": 1080, "height": 1350,
        "aspect_ratio": "4:5", "resolution": "2K",
        "description": "Вертикальный пост", "icon": "🖼️"
    },
    "twitter_header": {
        "name": "Twitter/X Шапка",
        "width": 1500, "height": 500,
        "aspect_ratio": "3:2", "resolution": "2K",
        "description": "Обложка профиля Twitter", "icon": "🐦"
    },
    "linkedin_cover": {
        "name": "LinkedIn Обложка",
        "width": 1584, "height": 396,
        "aspect_ratio": "4:1", "resolution": "2K",
        "description": "Обложка профиля LinkedIn", "icon": "💼"
    },
    "tiktok_cover": {
        "name": "TikTok Обложка",
        "width": 1080, "height": 1920,
        "aspect_ratio": "9:16", "resolution": "2K",
        "description": "Обложка для TikTok", "icon": "🎵"
    },
    "vk_cover": {
        "name": "ВКонтакте Обложка",
        "width": 1590, "height": 400,
        "aspect_ratio": "4:1", "resolution": "2K",
        "description": "Обложка сообщества ВК", "icon": "🔵"
    },
    "telegram_channel": {
        "name": "Telegram Канал",
        "width": 1280, "height": 720,
        "aspect_ratio": "16:9", "resolution": "2K",
        "description": "Превью для Telegram", "icon": "✈️"
    }
}

# Форматы изображений
IMAGE_FORMATS = {
    "realistic": {
        "name": "Реалистичный",
        "prompt_suffix": "photorealistic, realistic photography, high detail, natural lighting, professional photo quality, lifelike",
        "icon": "📸"
    },
    "cartoon": {
        "name": "Мультяшный",
        "prompt_suffix": "cartoon style, animated, colorful, playful, stylized illustration, 2D animation style, vibrant colors",
        "icon": "🎨"
    },
    "anime": {
        "name": "Аниме",
        "prompt_suffix": "anime style, manga art, Japanese animation, cel-shaded, vibrant anime colors, detailed anime illustration",
        "icon": "🎌"
    }
}

# Стили дизайна (расширенный список с preview изображениями)
DESIGN_STYLES = {
    "modern": {
        "name": "Современный", 
        "prompt_prefix": "Modern minimalist design with clean lines, bold typography, gradient backgrounds,", 
        "icon": "✨",
        "preview": "https://images.unsplash.com/photo-1558655146-364adaf1fcc9?w=400&h=300&fit=crop"
    },
    "neon": {
        "name": "Неон", 
        "prompt_prefix": "Neon cyberpunk style with glowing effects, dark background, vibrant neon colors pink blue purple,", 
        "icon": "💜",
        "preview": "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=400&h=300&fit=crop"
    },
    "gradient": {
        "name": "Градиент", 
        "prompt_prefix": "Beautiful gradient background with smooth color transitions, professional look,", 
        "icon": "🌈",
        "preview": "https://images.unsplash.com/photo-1557672172-298e090bd0f1?w=400&h=300&fit=crop"
    },
    "3d": {
        "name": "3D Графика", 
        "prompt_prefix": "3D rendered elements, glossy materials, depth and shadows, professional 3D design,", 
        "icon": "🎮",
        "preview": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=400&h=300&fit=crop"
    },
    "vintage": {
        "name": "Винтаж", 
        "prompt_prefix": "Vintage retro style, warm colors, nostalgic feel, classic typography,", 
        "icon": "📻",
        "preview": "https://images.unsplash.com/photo-1513475382585-d06e58bcb0e0?w=400&h=300&fit=crop"
    },
    "nature": {
        "name": "Природа", 
        "prompt_prefix": "Natural elements, green plants, organic shapes, eco-friendly aesthetic,", 
        "icon": "🌿",
        "preview": "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=400&h=300&fit=crop"
    },
    "tech": {
        "name": "Технологии", 
        "prompt_prefix": "High-tech futuristic design, circuit patterns, blue tech glow, digital elements,", 
        "icon": "🤖",
        "preview": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=400&h=300&fit=crop"
    },
    "gaming": {
        "name": "Игровой", 
        "prompt_prefix": "Epic gaming style, dynamic action, bold colors, esports aesthetic,", 
        "icon": "🎮",
        "preview": "https://images.unsplash.com/photo-1493711662062-fa541adb3fc8?w=400&h=300&fit=crop"
    },
    "business": {
        "name": "Бизнес", 
        "prompt_prefix": "Professional corporate design, clean layout, trustworthy colors blue gray,", 
        "icon": "💼",
        "preview": "https://images.unsplash.com/photo-1556761175-5973dc0f32e7?w=400&h=300&fit=crop"
    },
    "creative": {
        "name": "Креативный", 
        "prompt_prefix": "Creative artistic design, unique visual elements, eye-catching composition,", 
        "icon": "🎨",
        "preview": "https://images.unsplash.com/photo-1513475382585-d06e58bcb0e0?w=400&h=300&fit=crop"
    },
    "minimalist": {
        "name": "Минимализм", 
        "prompt_prefix": "Minimalist design, lots of white space, simple geometric shapes, clean and elegant,", 
        "icon": "⚪",
        "preview": "https://images.unsplash.com/photo-1561070791-2526d30994b5?w=400&h=300&fit=crop"
    },
    "watercolor": {
        "name": "Акварель", 
        "prompt_prefix": "Watercolor painting style, soft brush strokes, flowing colors, artistic watercolor effect,", 
        "icon": "🎨",
        "preview": "https://images.unsplash.com/photo-1541961017774-22349e4a1262?w=400&h=300&fit=crop"
    },
    "sketch": {
        "name": "Эскиз", 
        "prompt_prefix": "Hand-drawn sketch style, pencil drawing, artistic sketch, line art,", 
        "icon": "✏️",
        "preview": "https://images.unsplash.com/photo-1513475382585-d06e58bcb0e0?w=400&h=300&fit=crop"
    },
    "pop_art": {
        "name": "Поп-арт", 
        "prompt_prefix": "Pop art style, bold colors, comic book aesthetic, vibrant pop culture design,", 
        "icon": "🖼️",
        "preview": "https://images.unsplash.com/photo-1541961017774-22349e4a1262?w=400&h=300&fit=crop"
    },
    "abstract": {
        "name": "Абстрактный", 
        "prompt_prefix": "Abstract art, geometric shapes, flowing forms, contemporary abstract design,", 
        "icon": "🔷",
        "preview": "https://images.unsplash.com/photo-1557672172-298e090bd0f1?w=400&h=300&fit=crop"
    },
    "luxury": {
        "name": "Люкс", 
        "prompt_prefix": "Luxury premium design, gold accents, elegant typography, sophisticated high-end aesthetic,", 
        "icon": "💎",
        "preview": "https://images.unsplash.com/photo-1556761175-5973dc0f32e7?w=400&h=300&fit=crop"
    },
    "sport": {
        "name": "Спорт", 
        "prompt_prefix": "Dynamic sports design, athletic energy, motion blur effects, sporty vibrant colors,", 
        "icon": "⚽",
        "preview": "https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=400&h=300&fit=crop"
    },
    "food": {
        "name": "Еда", 
        "prompt_prefix": "Appetizing food photography style, warm lighting, delicious presentation, culinary aesthetic,", 
        "icon": "🍕",
        "preview": "https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=400&h=300&fit=crop"
    },
    "travel": {
        "name": "Путешествия", 
        "prompt_prefix": "Travel adventure style, scenic landscapes, wanderlust aesthetic, exploration theme,", 
        "icon": "✈️",
        "preview": "https://images.unsplash.com/photo-1488646953014-85cb44e25828?w=400&h=300&fit=crop"
    },
    "fashion": {
        "name": "Мода", 
        "prompt_prefix": "Fashion editorial style, elegant models, stylish composition, trendy fashion design,", 
        "icon": "👗",
        "preview": "https://images.unsplash.com/photo-1445205170230-053b83016050?w=400&h=300&fit=crop"
    }
}

# Примеры для форматов (одна тема в разных стилях)
FORMAT_EXAMPLES = {
    "banana_ad": {
        "topic": "Реклама бананов",
        "realistic": "https://i.imgur.com/realistic-banana.jpg",  # Замените на реальные URL
        "cartoon": "https://i.imgur.com/cartoon-banana.jpg",
        "anime": "https://i.imgur.com/anime-banana.jpg"
    }
}

PROMPT_EXAMPLES = [
    {"category": "YouTube", "title": "Техно канал", "prompt": "Tech review channel banner with futuristic gadgets, blue neon glow, modern typography, dark background"},
    {"category": "YouTube", "title": "Игровой канал", "prompt": "Epic gaming channel banner with controller, explosive effects, bold GAMING text, purple orange gradient"},
    {"category": "Instagram", "title": "Фитнес блог", "prompt": "Fitness motivation post with athletic silhouette, sunrise gradient, inspirational quote space, energetic vibe"},
    {"category": "Facebook", "title": "Ресторан", "prompt": "Restaurant cover with delicious food photography style, warm lighting, elegant typography, appetizing colors"},
    {"category": "Business", "title": "Стартап", "prompt": "Startup company cover with rocket launch, growth chart elements, innovative blue gradient, professional look"}
]


# ============ GOOGLE OAUTH ROUTES ============

@app.route('/covers/auth/google')
def google_login():
    if not google:
        return redirect('/covers/login?error=google_not_configured')
    redirect_uri = 'https://2msp.webversy.top/covers/auth/google/callback'
    return google.authorize_redirect(redirect_uri)


@app.route('/covers/auth/google/callback')
def google_callback():
    if not google:
        return redirect('/covers/login?error=google_not_configured')
    
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
        
        if not user_info:
            return redirect('/covers/login?error=google_failed')
        
        google_id = user_info.get('sub')
        email = user_info.get('email')
        name = user_info.get('name', email.split('@')[0])
        
        conn = get_db()
        c = conn.cursor()
        
        # Проверяем существует ли пользователь с таким google_id
        c.execute('SELECT * FROM users WHERE google_id = ?', (google_id,))
        user = c.fetchone()
        
        if user:
            # Логиним существующего пользователя
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            conn.close()
            return redirect('/covers/')
        
        # Проверяем email
        c.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = c.fetchone()
        
        if user:
            # Привязываем Google к существующему аккаунту
            c.execute('UPDATE users SET google_id = ? WHERE id = ?', (google_id, user['id']))
            conn.commit()
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            conn.close()
            return redirect('/covers/')
        
        # Создаём нового пользователя
        username = name.replace(' ', '_').lower()
        # Проверяем уникальность username
        c.execute('SELECT id FROM users WHERE username = ?', (username,))
        if c.fetchone():
            username = f"{username}_{str(uuid.uuid4())[:4]}"
        
        c.execute(
            'INSERT INTO users (username, email, google_id) VALUES (?, ?, ?)',
            (username, email, google_id)
        )
        conn.commit()
        user_id = c.lastrowid
        conn.close()
        
        session.permanent = True
        session['user_id'] = user_id
        session['username'] = username
        
        # Перенаправляем на настройки для добавления API токена
        return redirect('/covers/settings?welcome=1')
        
    except Exception as e:
        print(f"Google OAuth error: {e}")
        return redirect('/covers/login?error=google_failed')


# ============ AUTH ROUTES ============

@app.route('/covers/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.form
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        api_token = data.get('api_token', '').strip()
        
        if not username or not email or not password:
            return render_template('register.html', error='Заполните все обязательные поля', google_enabled=bool(google))
        
        if len(password) < 6:
            return render_template('register.html', error='Пароль должен быть минимум 6 символов', google_enabled=bool(google))
        
        try:
            conn = get_db()
            c = conn.cursor()
            c.execute(
                'INSERT INTO users (username, email, password_hash, api_token) VALUES (?, ?, ?, ?)',
                (username, email, hash_password(password), api_token if api_token else None)
            )
            conn.commit()
            user_id = c.lastrowid
            conn.close()
            
            session.permanent = True
            session['user_id'] = user_id
            session['username'] = username
            
            if api_token:
                return redirect('/covers/')
            else:
                return redirect('/covers/settings')
                
        except sqlite3.IntegrityError:
            return render_template('register.html', error='Пользователь с таким именем или email уже существует', google_enabled=bool(google))
    
    return render_template('register.html', google_enabled=bool(google))


@app.route('/covers/login', methods=['GET', 'POST'])
def login():
    error = request.args.get('error')
    error_msg = None
    
    if error == 'google_not_configured':
        error_msg = 'Google авторизация не настроена'
    elif error == 'google_failed':
        error_msg = 'Ошибка авторизации через Google'
    
    if request.method == 'POST':
        data = request.form
        email = data.get('email', '').strip()
        password = data.get('password', '')
        
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE email = ? AND password_hash = ?', 
                  (email, hash_password(password)))
        user = c.fetchone()
        conn.close()
        
        if user:
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect('/covers/')
        else:
            return render_template('login.html', error='Неверный email или пароль', google_enabled=bool(google))
    
    return render_template('login.html', error=error_msg, google_enabled=bool(google))


@app.route('/covers/logout')
def logout():
    session.clear()
    return redirect('/covers/login')


def send_password_reset_email(email, reset_link):
    """Отправка email с ссылкой для восстановления пароля"""
    try:
        # Простая реализация через SMTP (можно настроить через переменные окружения)
        smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        smtp_user = os.environ.get('SMTP_USER', '')
        smtp_password = os.environ.get('SMTP_PASSWORD', '')
        
        if not smtp_user or not smtp_password:
            # Если SMTP не настроен, логируем и возвращаем False
            print(f"Password reset link for {email}: {reset_link}")
            print(f"SMTP not configured. Reset link: {reset_link}")
            return False
        
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = email
        msg['Subject'] = 'Восстановление пароля - AI Cover Generator'
        
        body = f"""
        Здравствуйте!
        
        Вы запросили восстановление пароля для AI Cover Generator.
        
        Для восстановления пароля перейдите по ссылке:
        {reset_link}
        
        Ссылка действительна в течение 1 часа.
        
        Если вы не запрашивали восстановление пароля, просто проигнорируйте это письмо.
        
        С уважением,
        Команда AI Cover Generator
        """
        
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        
        return True
    except Exception as e:
        print(f"Email send error: {e}")
        # В режиме разработки просто логируем
        return True


@app.route('/covers/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        
        if not email:
            return render_template('forgot-password.html', error='Введите email')
        
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT id, username FROM users WHERE email = ?', (email,))
        user = c.fetchone()
        
        if user:
            # Создаём токен для восстановления
            reset_token = str(uuid.uuid4())
            expires_at = datetime.now() + timedelta(hours=1)
            
            c.execute('''
                INSERT INTO password_resets (user_id, token, expires_at)
                VALUES (?, ?, ?)
            ''', (user['id'], reset_token, expires_at))
            conn.commit()
            conn.close()
            
            # Отправляем email
            reset_link = f"https://2msp.webversy.top/covers/reset-password?token={reset_token}"
            email_sent = send_password_reset_email(email, reset_link)
            
            # Если email не настроен, показываем ссылку на странице
            if not email_sent:
                return render_template('forgot-password.html', 
                                     success=f'Ссылка для восстановления пароля (email не настроен, используйте эту ссылку):',
                                     reset_link=reset_link)
            
            return render_template('forgot-password.html', 
                                 success='Ссылка для восстановления пароля отправлена на ваш email. Проверьте почту (включая папку "Спам").')
        else:
            conn.close()
            # Не раскрываем существование пользователя
            return render_template('forgot-password.html', 
                                 success='Если такой email существует, ссылка для восстановления пароля отправлена.')
    
    return render_template('forgot-password.html')


@app.route('/covers/reset-password', methods=['GET', 'POST'])
def reset_password():
    token = request.args.get('token') or request.form.get('token', '')
    
    if not token:
        return redirect('/covers/forgot-password')
    
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT pr.user_id, pr.expires_at, pr.used, u.email
        FROM password_resets pr
        JOIN users u ON pr.user_id = u.id
        WHERE pr.token = ? AND pr.used = 0
    ''', (token,))
    reset_data = c.fetchone()
    
    if not reset_data:
        conn.close()
        return render_template('forgot-password.html', error='Недействительная или истёкшая ссылка')
    
    expires_at = datetime.fromisoformat(reset_data['expires_at'])
    if datetime.now() > expires_at:
        conn.close()
        return render_template('forgot-password.html', error='Ссылка истекла. Запросите новую.')
    
    if request.method == 'POST':
        new_password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not new_password or len(new_password) < 6:
            conn.close()
            return render_template('reset-password.html', token=token, error='Пароль должен быть минимум 6 символов')
        
        if new_password != confirm_password:
            conn.close()
            return render_template('reset-password.html', token=token, error='Пароли не совпадают')
        
        # Обновляем пароль
        c.execute('UPDATE users SET password_hash = ? WHERE id = ?', 
                  (hash_password(new_password), reset_data['user_id']))
        c.execute('UPDATE password_resets SET used = 1 WHERE token = ?', (token,))
        conn.commit()
        conn.close()
        
        return redirect('/covers/login?password_reset=success')
    
    conn.close()
    return render_template('reset-password.html', token=token)


@app.route('/covers/settings', methods=['GET', 'POST'])
@login_required
def settings():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    user = c.fetchone()
    
    welcome = request.args.get('welcome')
    success_msg = None
    
    if welcome:
        success_msg = 'Добро пожаловать! Добавьте API токен для генерации обложек.'
    
    if request.method == 'POST':
        api_token = request.form.get('api_token', '').strip()
        openai_token = request.form.get('openai_token', '').strip()
        c.execute('UPDATE users SET api_token = ?, openai_token = ? WHERE id = ?', 
                  (api_token, openai_token if openai_token else None, session['user_id']))
        conn.commit()
        conn.close()
        return render_template('settings.html', user=user, success='Токены сохранены!', google_enabled=bool(google))
    
    conn.close()
    return render_template('settings.html', user=user, success=success_msg, google_enabled=bool(google))


# ============ HELP PAGE ============

@app.route('/covers/help')
def help_page():
    return render_template('help.html')


# ============ MAIN ROUTES ============

@app.route('/')
@app.route('/covers')
@app.route('/covers/')
def index():
    if 'user_id' not in session:
        return redirect('/covers/login')
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT api_token FROM users WHERE id = ?', (session['user_id'],))
    user = c.fetchone()
    conn.close()
    
    has_token = bool(user and user['api_token'])
    
    return render_template('index.html', 
                         sizes=SOCIAL_MEDIA_SIZES,
                         styles=DESIGN_STYLES,
                         formats=IMAGE_FORMATS,
                         format_examples=FORMAT_EXAMPLES,
                         examples=PROMPT_EXAMPLES,
                         username=session.get('username'),
                         has_token=has_token)


@app.route('/api/upload', methods=['POST'])
@app.route('/covers/api/upload', methods=['POST'])
@login_required
def upload_file():
    """Загрузка файлов с компьютера"""
    if 'file' not in request.files:
        return jsonify({'error': 'Файл не выбран'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Файл не выбран'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Добавляем уникальный ID чтобы избежать конфликтов
        unique_filename = f"{uuid.uuid4()}_{filename}"
        filepath = os.path.join(Config.UPLOAD_FOLDER, unique_filename)
        file.save(filepath)
        
        # Возвращаем URL для доступа к файлу
        file_url = f"/covers/uploads/{unique_filename}"
        return jsonify({'success': True, 'url': file_url, 'filename': unique_filename})
    
    return jsonify({'error': 'Неподдерживаемый формат файла'}), 400


@app.route('/covers/uploads/<filename>')
def uploaded_file(filename):
    """Отдача загруженных файлов"""
    return send_from_directory(Config.UPLOAD_FOLDER, filename)


@app.route('/api/generate', methods=['POST'])
@app.route('/covers/api/generate', methods=['POST'])
@login_required
def generate_cover():
    try:
        # Получаем токены пользователя
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT api_token, openai_token FROM users WHERE id = ?', (session['user_id'],))
        user = c.fetchone()
        conn.close()
        
        if not user or not user['api_token']:
            return jsonify({'error': 'API токен не настроен. Перейдите в настройки.'}), 400
        
        api_token = user['api_token']
        openai_token = user['openai_token'] if user and user['openai_token'] else None
        
        data = request.json
        platform = data.get('platform', 'youtube_thumbnail')
        style = data.get('style', 'modern')
        image_format = data.get('format', 'realistic')  # realistic, cartoon, anime
        user_prompt = data.get('prompt', '')
        
        # Исправляем ошибки в промпте (используя OpenAI если токен есть)
        user_prompt = fix_prompt_errors(user_prompt, openai_token)
        
        # Получаем ссылки на референсные изображения (до 5 штук)
        image_urls = data.get('image_urls', [])
        # Фильтруем пустые ссылки и конвертируем локальные URL в полные
        processed_urls = []
        for url in image_urls:
            url = url.strip()
            if not url:
                continue
            # Если это локальный URL загруженного файла, конвертируем в полный
            if url.startswith('/covers/uploads/'):
                url = f"https://2msp.webversy.top{url}"
            processed_urls.append(url)
        image_urls = processed_urls[:5]  # До 5 фото
        
        if not user_prompt:
            return jsonify({'error': 'Опишите желаемую обложку'}), 400
        
        size_config = SOCIAL_MEDIA_SIZES.get(platform, SOCIAL_MEDIA_SIZES['youtube_thumbnail'])
        style_config = DESIGN_STYLES.get(style, DESIGN_STYLES['modern'])
        format_config = IMAGE_FORMATS.get(image_format, IMAGE_FORMATS['realistic'])
        
        # Добавляем информацию о фото в промпт если есть
        photo_info = ""
        if processed_urls:
            photo_info = f", using {len(processed_urls)} reference photo(s) as style and content guide"
        
        # Собираем полный промпт с форматом (исправленный)
        full_prompt = f"{style_config['prompt_prefix']} {user_prompt}{photo_info}, {format_config['prompt_suffix']}, high quality, professional design, {size_config['width']}x{size_config['height']} pixels"
        
        headers = {
            'Authorization': f'Bearer {api_token}',
            'Content-Type': 'application/json'
        }
        
        # Базовый payload для Nano Banana Pro
        payload = {
            "model": "nano-banana-pro",
            "input": {
                "prompt": full_prompt,
                "aspect_ratio": size_config['aspect_ratio'],
                "resolution": size_config['resolution'],
                "output_format": "png"
            }
        }
        
        # Добавляем референсные изображения если есть (ОБЯЗАТЕЛЬНО!)
        if processed_urls:
            payload["input"]["image_prompts"] = [
                {"url": url, "weight": 0.7} for url in processed_urls
            ]
            print(f"✅ Added {len(processed_urls)} reference images to generation")
        
        response = requests.post(
            f"{Config.KIE_API_URL}/createTask",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        result = response.json()
        
        if result.get('code') == 200:
            # Сохраняем генерацию в БД
            conn = get_db()
            c = conn.cursor()
            c.execute('''
                INSERT INTO generations (user_id, task_id, platform, style, prompt, status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (session['user_id'], result['data']['taskId'], platform, style, user_prompt, 'processing'))
            c.execute('UPDATE users SET generations_count = generations_count + 1 WHERE id = ?', (session['user_id'],))
            conn.commit()
            conn.close()
            
            response_data = {
                'success': True,
                'taskId': result['data']['taskId'],
                'platform': platform,
                'images_used': len(processed_urls) if processed_urls else 0,
                'image_urls': processed_urls if processed_urls else [],
                'size': f"{size_config['width']}x{size_config['height']}",
                'message': f'Задача создана! Генерация началась... {"✅ Используется " + str(len(processed_urls)) + " фото" if processed_urls else ""}'
            }
            return jsonify(response_data)
        else:
            error_msg = result.get('msg', 'API Error')
            if result.get('code') == 401:
                error_msg = 'Неверный API токен. Проверьте настройки.'
            elif result.get('code') == 402:
                error_msg = 'Недостаточно кредитов на аккаунте Kie.ai'
            return jsonify({'error': error_msg, 'code': result.get('code')}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/status/<task_id>')
@app.route('/covers/api/status/<task_id>')
@login_required
def check_status(task_id):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT api_token FROM users WHERE id = ?', (session['user_id'],))
        user = c.fetchone()
        
        if not user or not user['api_token']:
            conn.close()
            return jsonify({'error': 'API токен не настроен'}), 400
        
        headers = {'Authorization': f'Bearer {user["api_token"]}'}
        
        response = requests.get(
            f"{Config.KIE_API_URL}/recordInfo",
            params={'taskId': task_id},
            headers=headers,
            timeout=30
        )
        
        result = response.json()
        
        if result.get('code') == 200:
            data = result['data']
            state = data.get('state', 'waiting')
            
            response_data = {'state': state, 'taskId': task_id}
            
            if state == 'success':
                import json
                result_json = json.loads(data.get('resultJson', '{}'))
                urls = result_json.get('resultUrls', [])
                if urls:
                    response_data['imageUrl'] = urls[0]
                    response_data['message'] = 'Обложка готова!'
                    
                    # Обновляем статус в БД
                    c.execute('UPDATE generations SET status = ?, image_url = ? WHERE task_id = ?',
                              ('success', urls[0], task_id))
                    conn.commit()
            elif state == 'fail':
                response_data['error'] = data.get('failMsg', 'Generation failed')
                c.execute('UPDATE generations SET status = ? WHERE task_id = ?', ('failed', task_id))
                conn.commit()
            else:
                response_data['message'] = 'Генерация в процессе...'
            
            conn.close()
            return jsonify(response_data)
        else:
            conn.close()
            return jsonify({'error': 'Failed to check status'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/generate-prompt', methods=['POST'])
@app.route('/covers/api/generate-prompt', methods=['POST'])
@login_required
def generate_prompt():
    """Генератор профессиональных промптов на основе темы и желаний пользователя"""
    try:
        # Получаем OpenAI токен пользователя
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT openai_token FROM users WHERE id = ?', (session['user_id'],))
        user = c.fetchone()
        openai_token = user['openai_token'] if user and user['openai_token'] else None
        conn.close()
        
        data = request.json
        topic = data.get('topic', '').strip()
        description = data.get('description', '').strip()
        platform = data.get('platform', 'youtube_banner')
        style = data.get('style', 'modern')
        image_format = data.get('format', 'realistic')
        
        if not topic:
            return jsonify({'error': 'Укажите тему обложки'}), 400
        
        # Получаем конфигурации
        size_config = SOCIAL_MEDIA_SIZES.get(platform, SOCIAL_MEDIA_SIZES['youtube_banner'])
        style_config = DESIGN_STYLES.get(style, DESIGN_STYLES['modern'])
        format_config = IMAGE_FORMATS.get(image_format, IMAGE_FORMATS['realistic'])
        
        # Генерируем профессиональный промпт
        prompt_parts = []
        
        # Основная тема
        prompt_parts.append(topic)
        
        # Дополнительное описание если есть
        if description:
            prompt_parts.append(description)
        
        # Стиль дизайна
        prompt_parts.append(style_config['prompt_prefix'])
        
        # Формат изображения
        prompt_parts.append(format_config['prompt_suffix'])
        
        # Технические параметры
        prompt_parts.append(f"high quality, professional design, {size_config['width']}x{size_config['height']} pixels")
        
        # Собираем финальный промпт
        generated_prompt = ", ".join(prompt_parts)
        
        # Исправляем ошибки в сгенерированном промпте (используя OpenAI если токен есть)
        generated_prompt = fix_prompt_errors(generated_prompt, openai_token)
        
        return jsonify({
            'success': True,
            'prompt': generated_prompt,
            'suggestions': [
                f"Добавьте больше деталей о {topic}",
                f"Укажите цветовую гамму",
                f"Опишите настроение (энергичное, спокойное, драматичное)"
            ]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/fix-prompt', methods=['POST'])
@app.route('/covers/api/fix-prompt', methods=['POST'])
@login_required
def fix_prompt_api():
    """API для исправления промпта с помощью OpenAI"""
    try:
        data = request.json
        prompt = data.get('prompt', '').strip()
        
        if not prompt:
            return jsonify({'error': 'Введите промпт для исправления'}), 400
        
        # Получаем OpenAI токен пользователя
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT openai_token FROM users WHERE id = ?', (session['user_id'],))
        user = c.fetchone()
        openai_token = user['openai_token'] if user and user['openai_token'] else None
        conn.close()
        
        # Исправляем промпт
        used_openai = False
        if openai_token:
            fixed = fix_prompt_with_openai(prompt, openai_token)
            if fixed:
                fixed_prompt = fixed
                used_openai = True
            else:
                fixed_prompt = fix_prompt_errors(prompt, None)
        else:
            fixed_prompt = fix_prompt_errors(prompt, None)
        
        return jsonify({
            'success': True,
            'original': prompt,
            'fixed': fixed_prompt,
            'used_openai': used_openai
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def cleanup_old_history():
    """Удаляет историю генераций старше 3 дней"""
    try:
        conn = get_db()
        c = conn.cursor()
        # Удаляем записи старше 3 дней
        cutoff_date = datetime.now() - timedelta(days=3)
        c.execute('''
            DELETE FROM generations 
            WHERE created_at < ? AND status IN ('completed', 'failed')
        ''', (cutoff_date.isoformat(),))
        deleted_count = c.rowcount
        conn.commit()
        conn.close()
        if deleted_count > 0:
            print(f"🧹 Удалено {deleted_count} записей истории старше 3 дней")
        return deleted_count
    except Exception as e:
        print(f"Ошибка при очистке истории: {e}")
        return 0


@app.route('/covers/history')
@login_required
def history():
    # Автоматическая очистка старых записей
    cleanup_old_history()
    
    conn = get_db()
    c = conn.cursor()
    
    # Проверяем есть ли записи которые скоро будут удалены (через 3 дня)
    warning_date = datetime.now() - timedelta(days=2)  # Предупреждение за день до удаления
    cutoff_date = datetime.now() - timedelta(days=3)
    c.execute('''
        SELECT COUNT(*) as count FROM generations 
        WHERE user_id = ? AND created_at < ? AND created_at > ? AND status IN ('completed', 'failed')
    ''', (session['user_id'], warning_date.isoformat(), cutoff_date.isoformat()))
    warning_row = c.fetchone()
    warning_count = warning_row['count'] if warning_row else 0
    
    c.execute('''
        SELECT * FROM generations 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT 50
    ''', (session['user_id'],))
    generations = c.fetchall()
    
    # Проверяем возраст самой старой записи
    oldest_warning = None
    if generations:
        oldest = generations[-1]
        if oldest['created_at']:
            try:
                oldest_date = datetime.fromisoformat(oldest['created_at'])
                days_old = (datetime.now() - oldest_date).days
                if days_old >= 2:
                    oldest_warning = days_old
            except:
                pass
    
    conn.close()
    
    return render_template('history.html', 
                         generations=generations, 
                         username=session.get('username'),
                         warning_count=warning_count,
                         oldest_warning=oldest_warning)


@app.route('/api/sizes')
@app.route('/covers/api/sizes')
def get_sizes():
    return jsonify(SOCIAL_MEDIA_SIZES)


@app.route('/api/styles')
@app.route('/covers/api/styles')
def get_styles():
    return jsonify(DESIGN_STYLES)


@app.route('/covers/comics')
@login_required
def comics_page():
    """Страница генерации комиксов"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT api_token, openai_token FROM users WHERE id = ?', (session['user_id'],))
    user = c.fetchone()
    conn.close()
    
    has_token = bool(user and user['api_token'])
    
    return render_template('comics.html',
                         username=session.get('username'),
                         has_token=has_token,
                         google_enabled=bool(google))


@app.route('/covers/caricature')
@login_required
def caricature_page():
    """Страница генерации карикатур"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT api_token, openai_token FROM users WHERE id = ?', (session['user_id'],))
    user = c.fetchone()
    conn.close()
    
    has_token = bool(user and user['api_token'])
    
    return render_template('caricature.html',
                         username=session.get('username'),
                         has_token=has_token,
                         google_enabled=bool(google))


@app.route('/api/generate-comics', methods=['POST'])
@app.route('/covers/api/generate-comics', methods=['POST'])
@login_required
def generate_comics():
    """Генерация комиксов (1-6 блоков)"""
    try:
        # Получаем токены пользователя
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT api_token, openai_token FROM users WHERE id = ?', (session['user_id'],))
        user = c.fetchone()
        conn.close()
        
        if not user or not user['api_token']:
            return jsonify({'error': 'API токен не настроен. Перейдите в настройки.'}), 400
        
        api_token = user['api_token']
        openai_token = user['openai_token'] if user and user['openai_token'] else None
        
        data = request.json
        blocks_count = int(data.get('blocks', 3))  # 1-6 блоков
        style = data.get('style', 'cartoon')  # cartoon или realistic
        topic = data.get('topic', '').strip()
        description = data.get('description', '').strip()
        image_urls = data.get('image_urls', [])
        
        if not topic:
            return jsonify({'error': 'Введите тему комикса'}), 400
        
        # Генерируем промпты для каждого блока
        comics_prompts = []
        if openai_token:
            # Используем OpenAI для генерации сценария
            try:
                headers = {
                    'Authorization': f'Bearer {openai_token}',
                    'Content-Type': 'application/json'
                }
                
                system_prompt = f"""Создай сценарий для комикса из {blocks_count} кадров на тему: {topic}.
                {'Описание: ' + description if description else ''}
                
                Верни ТОЛЬКО список из {blocks_count} промптов, каждый на отдельной строке.
                Каждый промпт должен описывать один кадр комикса.
                Промпты должны быть короткими (до 20 слов), понятными для генерации изображения.
                Формат: просто список промптов, каждый с новой строки."""
                
                payload = {
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Создай сценарий комикса на тему: {topic}"}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 500
                }
                
                response = requests.post(
                    'https://api.openai.com/v1/chat/completions',
                    headers=headers,
                    json=payload,
                    timeout=15
                )
                
                if response.status_code == 200:
                    result = response.json()
                    generated_text = result['choices'][0]['message']['content'].strip()
                    comics_prompts = [p.strip() for p in generated_text.split('\n') if p.strip()][:blocks_count]
            except Exception as e:
                print(f"OpenAI error for comics: {e}")
        
        # Если OpenAI не сработал, генерируем простые промпты
        if not comics_prompts or len(comics_prompts) < blocks_count:
            for i in range(blocks_count):
                prompt = f"{topic}, scene {i+1}"
                if description:
                    prompt += f", {description}"
                comics_prompts.append(prompt)
        
        # Формируем финальные промпты с учетом стиля и фото
        style_prefix = "cartoon style, comic book, vibrant colors, " if style == 'cartoon' else "realistic style, photorealistic, "
        
        final_prompts = []
        for i, prompt in enumerate(comics_prompts):
            final_prompt = f"{prompt}, {style_prefix}comic panel {i+1} of {blocks_count}"
            
            # Добавляем ссылки на фото если есть
            if image_urls:
                photo_refs = ", ".join([f"reference image {j+1}: {url}" for j, url in enumerate(image_urls[:6]) if url.strip()])
                if photo_refs:
                    final_prompt += f", {photo_refs}"
            
            final_prompts.append(final_prompt)
        
        # Генерируем изображения для каждого блока
        task_ids = []
        for i, prompt in enumerate(final_prompts):
            # Исправляем промпт
            fixed_prompt = fix_prompt_errors(prompt, openai_token)
            
            # Создаём задачу генерации
            payload = {
                "prompt": fixed_prompt,
                "width": 1024,
                "height": 1024,
                "num_inference_steps": 30,
                "guidance_scale": 7.5
            }
            
            # Добавляем reference images если есть
            if image_urls:
                ref_images = [url for url in image_urls[:6] if url.strip()]
                if ref_images:
                    payload["reference_images"] = ref_images
            
            headers = {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                Config.KIE_API_URL,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                task_data = response.json()
                task_id = task_data.get('task_id')
                if task_id:
                    task_ids.append({
                        'block': i + 1,
                        'task_id': task_id,
                        'prompt': fixed_prompt
                    })
        
        if not task_ids:
            return jsonify({'error': 'Не удалось создать задачи генерации'}), 500
        
        # Сохраняем в БД
        conn = get_db()
        c = conn.cursor()
        for task_info in task_ids:
            c.execute('''
                INSERT INTO generations (user_id, task_id, platform, style, prompt, status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (session['user_id'], task_info['task_id'], 'comics', style, task_info['prompt'], 'processing'))
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'blocks': blocks_count,
            'task_ids': task_ids,
            'message': f'Генерация комикса из {blocks_count} блоков начата!'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/generate-caricature', methods=['POST'])
@app.route('/covers/api/generate-caricature', methods=['POST'])
@login_required
def generate_caricature():
    """Генерация карикатуры"""
    try:
        # Получаем токены пользователя
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT api_token, openai_token FROM users WHERE id = ?', (session['user_id'],))
        user = c.fetchone()
        conn.close()
        
        if not user or not user['api_token']:
            return jsonify({'error': 'API токен не настроен. Перейдите в настройки.'}), 400
        
        api_token = user['api_token']
        openai_token = user['openai_token'] if user and user['openai_token'] else None
        
        data = request.json
        prompt = data.get('prompt', '').strip()
        image_urls = data.get('image_urls', [])
        
        if not prompt:
            return jsonify({'error': 'Введите описание карикатуры'}), 400
        
        # Формируем промпт для карикатуры
        caricature_prompt = f"caricature style, {prompt}, exaggerated features, humorous, cartoon portrait, single character, full body or portrait"
        
        # Добавляем ссылки на фото если есть
        if image_urls:
            photo_refs = ", ".join([f"reference image {j+1}: {url}" for j, url in enumerate(image_urls[:6]) if url.strip()])
            if photo_refs:
                caricature_prompt += f", {photo_refs}, use these reference images to create caricature"
        
        # Исправляем промпт
        fixed_prompt = fix_prompt_errors(caricature_prompt, openai_token)
        
        # Создаём задачу генерации
        payload = {
            "prompt": fixed_prompt,
            "width": 1024,
            "height": 1024,
            "num_inference_steps": 30,
            "guidance_scale": 7.5
        }
        
        # Добавляем reference images если есть
        if image_urls:
            ref_images = [url for url in image_urls[:6] if url.strip()]
            if ref_images:
                payload["reference_images"] = ref_images
        
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            Config.KIE_API_URL,
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            task_data = response.json()
            task_id = task_data.get('task_id')
            
            if task_id:
                # Сохраняем в БД
                conn = get_db()
                c = conn.cursor()
                c.execute('''
                    INSERT INTO generations (user_id, task_id, platform, style, prompt, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (session['user_id'], task_id, 'caricature', 'caricature', fixed_prompt, 'processing'))
                conn.commit()
                conn.close()
                
                return jsonify({
                    'success': True,
                    'task_id': task_id,
                    'prompt': fixed_prompt,
                    'message': 'Генерация карикатуры начата!'
                })
        
        return jsonify({'error': 'Не удалось создать задачу генерации'}), 500
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("🎨 Starting AI Cover Generator...")
    print("📍 URL: http://localhost:5002")
    print(f"🔑 Google OAuth: {'Enabled' if google else 'Disabled'}")
    
    # Автоматическая очистка истории при запуске
    deleted = cleanup_old_history()
    if deleted > 0:
        print(f"🧹 Очищено {deleted} записей истории при запуске")
    
    # debug=False и threaded=True для стабильной работы с несколькими пользователями
    app.run(host='0.0.0.0', port=5002, debug=False, threaded=True)
