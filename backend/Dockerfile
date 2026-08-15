FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # The ADK engine imports adk_agents as a top-level package.
    PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY adk_agents ./adk_agents
COPY data ./data

# Cloud Run runs containers as an unprivileged user by convention; doing it
# explicitly means the image behaves the same anywhere it is run.
RUN useradd --create-home --uid 1000 cardsense && chown -R cardsense:cardsense /app
USER cardsense

# Cloud Run injects PORT and is free to choose it. Binding to a hard-coded 8080
# works today and fails silently the day it does not.
ENV PORT=8080
EXPOSE 8080
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
