FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY . .

RUN uv sync

EXPOSE 5060

HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5060/health', timeout=2).getcode() == 200 else 1)"

CMD ["uv", "run", "python", "-m", "flask", "--app", "app", "run", "--host", "0.0.0.0", "--port", "5060"]