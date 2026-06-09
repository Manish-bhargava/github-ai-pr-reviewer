FROM python:3.11-slim
WORKDIR /db
COPY services/webhook/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY db/ .
CMD ["alembic", "upgrade", "head"]
