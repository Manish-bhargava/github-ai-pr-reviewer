

FROM python:3.11-slim

WORKDIR /app

# install dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# copy learner service code
COPY . /app

# run app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004"]