FROM python:3.12-slim

WORKDIR /workspace

COPY services/game-engine/requirements.txt /tmp/requirements.txt
COPY packages/shared-schemas /tmp/packages/shared-schemas
COPY packages/shared-config /tmp/packages/shared-config
COPY packages/game-rules /tmp/packages/game-rules
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && pip install --no-cache-dir /tmp/packages/shared-schemas /tmp/packages/shared-config /tmp/packages/game-rules

COPY infra /workspace/infra
COPY packages/shared-config /workspace/packages/shared-config
COPY services/game-engine/app /workspace/services/game-engine/app

ENV PYTHONPATH=/workspace/services/game-engine

CMD ["python", "-m", "app.main"]
