FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir "rememb[mcp]==0.4.4"

ENV REMEMB_GLOBAL=1

CMD ["rememb", "mcp"]
