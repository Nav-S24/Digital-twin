FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Exclude the standalone React dashboard folder — it's a separate Vite app,
# not part of this Python service, and gets its own build step if used.
COPY api ./api
COPY config ./config
COPY services ./services
COPY twin ./twin
COPY utils ./utils
COPY data ./data
COPY main.py .

EXPOSE 8004
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004"]
