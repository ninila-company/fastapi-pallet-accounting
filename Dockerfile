# Используем официальный образ Python. slim-версия меньше по размеру.
FROM python:3.13-slim

# Устанавливаем системные зависимости, необходимые для WeasyPrint (генерация PDF)
# --no-install-recommends помогает уменьшить размер образа
# fontconfig - для работы со шрифтами
# libpango-1.0-0, libpangoft2-1.0-0, libcairo2 - для рендеринга текста и графики
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    fontconfig \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем файл с зависимостями и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY . .

# Указываем порт, который будет слушать приложение
EXPOSE 8000

# Команда для запуска приложения при старте контейнера
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
