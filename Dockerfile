FROM python:3.11-slim

# Обновление системы и установка зависимостей
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y build-essential && \
    rm -rf /var/lib/apt/lists/*

# Задаём рабочую директорию
WORKDIR /app

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY . .

# Запускаем бота
ENTRYPOINT ["python", "-m", "app.main"]