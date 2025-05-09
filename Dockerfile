FROM python:3.13-slim

# Устанавливаем зависимости системы
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Создаем рабочую директорию
WORKDIR /app

# Устанавливаем зависимости через pip
RUN pip install --no-cache-dir poetry

# Копируем файлы проекта
COPY pyproject.toml .
COPY poetry.lock .
COPY README.md .
RUN poetry install --no-root

# Копируем файлы проекта
COPY calendar_sync/ calendar_sync/


# Делаем директорию для SQLite базы, если нужно
RUN mkdir -p /data

# Указываем рабочий каталог
ENV PYTHONPATH=/app

# Стартовая команда
CMD ["poetry", "run", "poe", "app"]