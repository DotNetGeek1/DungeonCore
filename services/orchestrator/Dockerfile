FROM python:3.12-slim

WORKDIR /workspace

COPY services/orchestrator/requirements.txt /tmp/requirements.txt
COPY packages/shared-schemas /tmp/packages/shared-schemas
COPY packages/shared-config /tmp/packages/shared-config
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && pip install --no-cache-dir /tmp/packages/shared-schemas /tmp/packages/shared-config

COPY infra /workspace/infra
COPY packages/shared-config /workspace/packages/shared-config
COPY services/orchestrator/app /workspace/services/orchestrator/app

ENV PYTHONPATH=/workspace/services/orchestrator

CMD ["python", "-m", "app.main"]
