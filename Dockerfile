FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir "rememb==0.4.9"

ENV REMEMB_GLOBAL=1

CMD ["rememb", "mcp"]
