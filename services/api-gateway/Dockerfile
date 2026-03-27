FROM python:3.12-slim

WORKDIR /workspace

COPY services/api-gateway/requirements.txt /tmp/requirements.txt
COPY packages/shared-schemas /tmp/packages/shared-schemas
COPY packages/shared-config /tmp/packages/shared-config
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && pip install --no-cache-dir /tmp/packages/shared-schemas /tmp/packages/shared-config

COPY infra /workspace/infra
COPY packages/shared-config /workspace/packages/shared-config
COPY services/api-gateway/app /workspace/services/api-gateway/app

ENV PYTHONPATH=/workspace/services/api-gateway

CMD ["python", "-m", "app.main"]
