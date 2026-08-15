FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY dashboard ./dashboard

RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1
ENV CAREER_OS_CONTROL_PLANE_PATH=/data/control_plane.json
VOLUME ["/data"]

CMD ["sh", "-c", "uvicorn career_os.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
