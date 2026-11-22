FROM python:3.15-slim

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir -e .

ENV REMEMB_GLOBAL=1

CMD ["rememb", "mcp"]
