FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Exclude the standalone React frontend (ChatPanel.jsx etc.) — not part
# of this Python service.
COPY data ./data
COPY routes ./routes
COPY services ./services
COPY main.py .

EXPOSE 8007
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8007"]
