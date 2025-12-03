# 🎨 AI Cover Generator

Генератор профессиональных обложек для социальных сетей с использованием нейросети Nano Banana Pro.

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-3.0-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## ✨ Возможности

- 🖼️ Генерация обложек для YouTube, Facebook, Instagram, Twitter, TikTok, ВКонтакте и других платформ
- 🎨 10 уникальных стилей дизайна
- 👤 Система регистрации с личными API токенами
- 🔐 Google OAuth авторизация
- 📜 История генераций
- 📐 Точные размеры для каждой платформы

## 📱 Поддерживаемые платформы

| Платформа | Размер | Описание |
|-----------|--------|----------|
| YouTube Баннер | 2560×1440 | Шапка канала |
| YouTube Превью | 1280×720 | Превью для видео |
| Facebook Обложка | 820×312 | Обложка страницы |
| Instagram Пост | 1080×1080 | Квадратный пост |
| Instagram Stories | 1080×1920 | Сторис/Reels |
| Twitter Шапка | 1500×500 | Обложка профиля |
| TikTok | 1080×1920 | Обложка видео |
| ВКонтакте | 1590×400 | Обложка сообщества |
| LinkedIn | 1584×396 | Обложка профиля |
| Telegram | 1280×720 | Превью канала |

## 🎨 Стили дизайна

- ✨ Современный (Modern)
- 💜 Неон (Neon)
- 🌈 Градиент (Gradient)
- 🎮 3D Графика
- 📻 Винтаж (Vintage)
- 🌿 Природа (Nature)
- 🤖 Технологии (Tech)
- 🎮 Игровой (Gaming)
- 💼 Бизнес (Business)
- 🎨 Креативный (Creative)

## 🚀 Установка

### 1. Клонируйте репозиторий

```bash
git clone https://github.com/yourusername/ai-cover-generator.git
cd ai-cover-generator
```

### 2. Создайте виртуальное окружение

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Установите зависимости

```bash
pip install -r requirements.txt
```

### 4. Настройте переменные окружения

```bash
export SECRET_KEY="your-secret-key"
export GOOGLE_CLIENT_ID="your-google-client-id"  # опционально
export GOOGLE_CLIENT_SECRET="your-google-secret"  # опционально
```

### 5. Запустите приложение

```bash
python app.py
```

Приложение будет доступно на http://localhost:5002

## 🔧 Конфигурация

### Google OAuth (опционально)

1. Создайте проект в [Google Cloud Console](https://console.cloud.google.com/)
2. Включите OAuth 2.0
3. Добавьте Redirect URI: `https://your-domain.com/covers/auth/google/callback`
4. Скопируйте Client ID и Client Secret

### Nginx (production)

```nginx
location /covers {
    proxy_pass http://localhost:5002;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

### Systemd сервис

```ini
[Unit]
Description=AI Cover Generator
After=network.target

[Service]
User=www-data
WorkingDirectory=/var/www/cover-generator
Environment="SECRET_KEY=your-secret-key"
Environment="GOOGLE_CLIENT_ID=your-client-id"
Environment="GOOGLE_CLIENT_SECRET=your-secret"
ExecStart=/var/www/cover-generator/venv/bin/python app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## 📁 Структура проекта

```
cover-generator/
├── app.py              # Основное приложение Flask
├── requirements.txt    # Зависимости Python
├── templates/          # HTML шаблоны
│   ├── index.html      # Главная страница генератора
│   ├── login.html      # Страница входа
│   ├── register.html   # Страница регистрации
│   ├── settings.html   # Настройки пользователя
│   ├── history.html    # История генераций
│   └── help.html       # Страница помощи
├── INSTRUCTION.md      # Инструкция на русском
└── GOOGLE_OAUTH_SETUP.md  # Настройка Google OAuth
```

## 🔑 API Kie.ai

Для генерации изображений используется [Nano Banana Pro](https://kie.ai) API.

Каждый пользователь вводит свой API токен в настройках. Получить токен можно на https://kie.ai/api-key

## 📖 Использование

1. Зарегистрируйтесь на сайте
2. Получите API токен на [kie.ai](https://kie.ai/api-key)
3. Добавьте токен в настройках
4. Выберите платформу и стиль
5. Опишите желаемую обложку
6. Нажмите "Сгенерировать"
7. Скачайте готовую обложку!

## 🛠️ Технологии

- **Backend:** Python 3.10+, Flask 3.0
- **Database:** SQLite
- **Auth:** Flask sessions, Google OAuth (Authlib)
- **API:** Kie.ai Nano Banana Pro
- **Frontend:** HTML5, CSS3, JavaScript

## 📄 Лицензия

MIT License

## 👨‍💻 Автор

Создано с ❤️ для генерации красивых обложек

