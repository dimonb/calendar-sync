FROM python:3.13-slim

# Устанавливаем зависимости системы
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Создаем рабочую директорию
WORKDIR /app

# Копируем файлы проекта
COPY pyproject.toml .
COPY poetry.lock .
COPY README.md .
COPY calendar_sync/ calendar_sync/

# Устанавливаем зависимости через pip
RUN pip install --no-cache-dir poetry
RUN poetry install

# Делаем директорию для SQLite базы, если нужно
RUN mkdir -p /data

# Указываем рабочий каталог
ENV PYTHONPATH=/app

# Стартовая команда
CMD ["poe", "app"]