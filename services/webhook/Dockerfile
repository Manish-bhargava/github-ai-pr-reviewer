FROM python:3.11-slim

WORKDIR /app

COPY services/webhook/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . .

CMD ["uvicorn", "services.webhook.main:app", "--host", "0.0.0.0", "--port", "8001"]