# Автоцентр «Ласточка» — Django

Адаптивная информационная система автосалона: каталог, клиентский кабинет, CRM, роли сотрудников, бронирования, тест-драйвы, продажи, платежи, поставки, отчёты и REST API.

## Локальный запуск

```bash
python -m venv venv
# Windows:
.\venv\Scripts\Activate.ps1
# Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt
python manage.py migrate
python manage.py seed_cars
python manage.py runserver
```

- Сайт: http://127.0.0.1:8000/
- Админка: http://127.0.0.1:8000/admin/ (создайте администратора через `python manage.py createsuperuser`)
- REST API: http://127.0.0.1:8000/api/ — `cars/` (фильтры `search`, `brand`, `model`, `price_min`, `price_max`, `year`, `body`, `fuel`, `transmission`, `drivetrain`, `color`, `status`, `car_type`, `mileage_max`, `sort`), `bookings/`, `test-drives/`, `favorites/`, `sales/`. Каталог публичный; бронирования, избранное и тест-драйвы требуют авторизации и принадлежат только текущему клиенту.

Локально SQLite используется только как fallback, если PostgreSQL не настроен. Для основной БД задайте `DATABASE_URL` (например, `postgresql://user:password@localhost:5432/lastocka`) либо `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST` и `POSTGRES_PORT`. `DATABASE_SSL_REQUIRE=True` включает TLS для `DATABASE_URL`.

Seed-команда добавляет демонстрационные автомобили, справочник марок/моделей, услуги и поставщика. Чтобы дополнительно создать администратора командой, задайте сильный `SEED_ADMIN_PASSWORD` перед запуском. Роли клиента/менеджера/кассира/администратора/руководителя назначаются в Django Admin в профиле пользователя; менеджерская панель доступна по `/manager/`, отчёты — `/reports/`.

Для плановой обработки броней, срок которых истёк, запускайте `python manage.py expire_bookings` (например, ежедневно через планировщик задач).

Целевые тесты: `python manage.py test cars`.

## Деплой на Render

1. Загрузите проект на **GitHub** (новый репозиторий).
2. На [render.com](https://render.com) создайте **PostgreSQL** (Free).
3. Создайте **Web Service** → Connect репозиторий:
   - **Runtime:** Python 3
   - **Build Command:** `chmod +x build.sh && ./build.sh`
   - **Start Command:** `gunicorn config.wsgi:application`
4. Environment Variables:
   - `SECRET_KEY` — любая длинная случайная строка
   - `DEBUG` = `False`
   - `DATABASE_URL` — скопируйте **Internal Database URL** из PostgreSQL-сервиса
   - `PYTHON_VERSION` = `3.12.0` (по желанию)
5. После деплоя откройте Shell в Render и выполните:
   ```bash
   python manage.py createsuperuser
   python manage.py seed_cars
   ```

Сайт будет на адресе вида `https://your-app.onrender.com`.
