FROM python:3.12-slim

WORKDIR /workspace

COPY services/communication-service/requirements.txt /tmp/requirements.txt
COPY packages/shared-schemas /tmp/packages/shared-schemas
COPY packages/shared-config /tmp/packages/shared-config
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && pip install --no-cache-dir /tmp/packages/shared-schemas /tmp/packages/shared-config

COPY infra /workspace/infra
COPY packages/shared-config /workspace/packages/shared-config
COPY services/communication-service/app /workspace/services/communication-service/app

ENV PYTHONPATH=/workspace/services/communication-service

CMD ["python", "-m", "app.main"]
