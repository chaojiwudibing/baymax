FROM python:3.12-slim
RUN useradd --uid 10001 --create-home baymax
WORKDIR /app
COPY scripts/reminder_bridge.py /app/reminder_bridge.py
USER baymax
ENTRYPOINT ["python", "/app/reminder_bridge.py", "serve"]
