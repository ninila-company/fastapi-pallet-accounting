# --- Этап 1: Сборка с зависимостями ---
# Используем официальный образ Python. slim-версия меньше по размеру.
FROM python:3.13-slim as builder

# Устанавливаем системные зависимости, необходимые для WeasyPrint (генерация PDF)
# --no-install-recommends помогает уменьшить размер образа
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем файл с зависимостями и устанавливаем их
# Это делается отдельным шагом для использования кэширования Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Этап 2: Финальный образ ---
FROM python:3.13-slim
WORKDIR /app

# Копируем системные библиотеки для WeasyPrint из этапа сборки
COPY --from=builder /usr/lib/x86_64-linux-gnu/ /usr/lib/x86_64-linux-gnu/

# Копируем исполняемые файлы, установленные через pip (включая uvicorn)
COPY --from=builder /usr/local/bin /usr/local/bin

# Копируем установленные Python-пакеты из этапа сборки
COPY --from=builder /usr/local/lib/python3.13/site-packages/ /usr/local/lib/python3.13/site-packages/

# Копируем код приложения
COPY . .

# Указываем порт, который будет слушать приложение
EXPOSE 8000

# Команда для запуска приложения при старте контейнера
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
