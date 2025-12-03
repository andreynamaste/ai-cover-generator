# 🔐 Настройка Google OAuth для AI Cover Generator

## Шаг 1: Создайте проект в Google Cloud Console

1. Зайдите на https://console.cloud.google.com/
2. Нажмите **"Select a project"** → **"New Project"**
3. Назовите проект: `AI Cover Generator`
4. Нажмите **"Create"**

## Шаг 2: Включите Google OAuth API

1. В меню слева выберите **"APIs & Services"** → **"Library"**
2. Найдите **"Google+ API"** или **"Google Identity"**
3. Нажмите **"Enable"**

## Шаг 3: Настройте OAuth Consent Screen

1. Перейдите в **"APIs & Services"** → **"OAuth consent screen"**
2. Выберите **"External"** → **"Create"**
3. Заполните:
   - App name: `AI Cover Generator`
   - User support email: ваш email
   - Developer contact: ваш email
4. Нажмите **"Save and Continue"**
5. Scopes: добавьте `email` и `profile`
6. Test users: добавьте ваш email для тестирования

## Шаг 4: Создайте OAuth Client ID

1. Перейдите в **"APIs & Services"** → **"Credentials"**
2. Нажмите **"+ CREATE CREDENTIALS"** → **"OAuth client ID"**
3. Выберите:
   - Application type: **Web application**
   - Name: `AI Cover Generator Web`
4. **Authorized redirect URIs** — добавьте:
   ```
   https://2msp.webversy.top/covers/auth/google/callback
   ```
5. Нажмите **"Create"**
6. **Скопируйте Client ID и Client Secret!**

## Шаг 5: Добавьте ключи в сервис

Отредактируйте файл сервиса:

```bash
sudo nano /etc/systemd/system/cover-generator.service
```

Добавьте переменные окружения в секцию `[Service]`:

```ini
[Service]
...
Environment="GOOGLE_CLIENT_ID=ваш-client-id.apps.googleusercontent.com"
Environment="GOOGLE_CLIENT_SECRET=ваш-client-secret"
```

## Шаг 6: Перезапустите сервис

```bash
sudo systemctl daemon-reload
sudo systemctl restart cover-generator
```

## Проверка

После настройки на странице входа появится кнопка **"Войти через Google"**.

---

## Пример полного файла сервиса:

```ini
[Unit]
Description=AI Cover Generator - Social Media Cover Creator
After=network.target

[Service]
User=root
WorkingDirectory=/var/www/cover-generator
ExecStart=/var/www/cover-generator/venv/bin/python3 /var/www/cover-generator/app.py
Restart=always
StandardOutput=append:/var/www/cover-generator/logs/app.log
StandardError=append:/var/www/cover-generator/logs/app.log
Environment="FLASK_APP=app.py"
Environment="FLASK_ENV=production"
Environment="SECRET_KEY=your-super-secret-random-key-here"
Environment="GOOGLE_CLIENT_ID=123456789-abc123.apps.googleusercontent.com"
Environment="GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxx"

[Install]
WantedBy=multi-user.target
```

---

## Частые проблемы

### "redirect_uri_mismatch"
Убедитесь, что в Google Console указан точный URL:
```
https://2msp.webversy.top/covers/auth/google/callback
```

### "access_denied"
1. Добавьте ваш email в Test users в OAuth consent screen
2. Или опубликуйте приложение (для всех пользователей)

### Google вход не появляется
Проверьте, что переменные окружения заданы:
```bash
sudo systemctl show cover-generator | grep Environment
```

