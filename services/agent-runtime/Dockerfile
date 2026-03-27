FROM python:3.12-slim

WORKDIR /workspace

COPY services/agent-runtime/requirements.txt /tmp/requirements.txt
COPY packages/shared-schemas /tmp/packages/shared-schemas
COPY packages/shared-config /tmp/packages/shared-config
COPY packages/game-rules /tmp/packages/game-rules
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && pip install --no-cache-dir /tmp/packages/shared-schemas /tmp/packages/shared-config /tmp/packages/game-rules

COPY infra /workspace/infra
COPY packages/shared-config /workspace/packages/shared-config
COPY services/agent-runtime/app /workspace/services/agent-runtime/app

ENV PYTHONPATH=/workspace/services/agent-runtime

CMD ["python", "-m", "app.main"]
