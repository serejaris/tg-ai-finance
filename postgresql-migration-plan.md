# План миграции на PostgreSQL для Railway

## Версионный лог

### 2025-01-27 - Миграция на PostgreSQL
**Промпт:** при каждом обновлении (редеплое) база данных стирается. что делать?

**Проблема:**
- Railway использует эфемерную файловую систему
- При каждом редеплое контейнер пересоздается
- Файл expenses.db (SQLite) теряется при каждом редеплое
- Нужно постоянное хранилище данных

**Решение:** Переход на PostgreSQL
- Railway предоставляет постоянное хранилище для PostgreSQL
- Данные не будут стираться при редеплое
- PostgreSQL - стандартное решение для production

**План:**
- [x] Добавить psycopg2-binary в requirements.txt
- [x] Добавить DATABASE_URL в config.py
- [x] Переписать storage.py для работы с PostgreSQL
  - Заменить sqlite3 на psycopg2
  - Изменить синтаксис SQL для PostgreSQL:
    - INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL PRIMARY KEY
    - PRAGMA table_info → information_schema
    - ? плейсхолдеры → %s
    - INSERT OR REPLACE → INSERT ... ON CONFLICT
    - strftime → EXTRACT
  - Добавить функцию get_connection для подключения
- [x] Добавить инструкцию по настройке PostgreSQL на Railway в README.md

**Сделано:**
- ✅ Добавлен psycopg2-binary==2.9.9 в requirements.txt
- ✅ Добавлена переменная DATABASE_URL в config.py из переменных окружения
- ✅ Полностью переписана storage.py:
  - Заменен импорт sqlite3 на psycopg2 и RealDictCursor
  - Добавлена функция get_connection() для подключения к PostgreSQL через DATABASE_URL
  - Обновлена init_db() для использования SERIAL PRIMARY KEY и information_schema
  - Обновлены все функции для использования %s вместо ?
  - Заменен INSERT OR REPLACE на INSERT ... ON CONFLICT для PostgreSQL
  - Обновлен get_monthly_expenses для использования EXTRACT вместо strftime
- ✅ Обновлен README.md:
  - Изменено "Хранение данных в SQLite" на "Хранение данных в PostgreSQL"
  - Удален expenses.db из структуры проекта
  - Обновлено описание storage.py
  - Добавлен раздел "Деплой на Railway" с инструкцией по добавлению PostgreSQL сервиса
  - Добавлено предупреждение о стирании данных без PostgreSQL

**Важно:** Для работы на Railway необходимо добавить PostgreSQL сервис через "New" → "Database" → "PostgreSQL" в панели проекта. Railway автоматически установит переменную DATABASE_URL.

