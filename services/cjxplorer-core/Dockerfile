FROM python:3.12-slim

RUN groupadd -r backend && useradd -r -g backend backend

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chown -R backend:backend /app
USER backend

CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]
