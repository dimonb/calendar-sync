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
COPY calendar-sync/ calendar-sync/
COPY sync.py sync.py
COPY config.py config.py

# Устанавливаем зависимости через pip
RUN pip install --no-cache-dir .

# Делаем директорию для SQLite базы, если нужно
RUN mkdir -p /data

# Указываем рабочий каталог
ENV PYTHONPATH=/app

# Стартовая команда
CMD ["python", "sync.py"]