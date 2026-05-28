FROM python:3.12-slim AS base

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir .

# Repo to analyze is mounted at /repo
ENV PYTHONUNBUFFERED=1 \
    LITELLM_BASE_URL=http://litellm:4000

ENTRYPOINT ["contrib-estimator"]
CMD ["--repo", "/repo"]
