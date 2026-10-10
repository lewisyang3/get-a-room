FROM python:3.12-slim

WORKDIR /code

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY ingestion ./ingestion
COPY data ./data
COPY alembic ./alembic
COPY alembic.ini ./

EXPOSE 8000

# Shell form so hosts like Heroku can choose the port through $PORT.
# --forwarded-allow-ips trusts the X-Forwarded-Proto header Heroku's router
# sets, so URLs the API generates (e.g. redirects) use https.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --forwarded-allow-ips='*'
