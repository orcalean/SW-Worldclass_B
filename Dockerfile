FROM python:3.12-slim
# LibreOffice renders DOCX/PPTX/XLSX to PDF so layout and pictures reach the vision model in place.
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-core libreoffice-writer \
    libreoffice-calc libreoffice-impress fonts-dejavu && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.4.20 /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY app ./app
COPY rubrics ./rubrics
# Alembic: the app runs migrations on startup
COPY alembic.ini ./
COPY migrations ./migrations
ENV SWC_DATA_DIR=/data
EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
