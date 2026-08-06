FROM python:3.12-slim

ARG PYPI_INDEX_URL=https://pypi.org/simple
ARG PIP_DEFAULT_TIMEOUT=60

WORKDIR /app
COPY apps/api/requirements.runtime.lock /app/apps/api/requirements.runtime.lock
RUN pip install \
      --disable-pip-version-check \
      --no-cache-dir \
      --retries 10 \
      --timeout "${PIP_DEFAULT_TIMEOUT}" \
      --index-url "${PYPI_INDEX_URL}" \
      -r /app/apps/api/requirements.runtime.lock

COPY apps/api /app/apps/api
COPY config /app/config
RUN pip install --disable-pip-version-check --no-cache-dir --no-deps /app/apps/api

RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /app/tmp \
    && chown -R app:app /app
USER app

EXPOSE 8000
CMD ["uvicorn", "project_manager_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
