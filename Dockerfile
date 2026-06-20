FROM python:3.12-slim

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir -e . -e packages/rememb-skills

ENV REMEMB_GLOBAL=1

CMD ["rememb", "mcp"]
