# Lean runtime image for agent-terminal-ui.
#
# Ships ONLY the frontend and its runtime deps (textual, rich, httpx, pydantic,
# pyyaml) -- no test/shell extras, no agent_utilities, no model weights. The heavy
# agent-utilities backend (KG engine + embedding model) is a separate, shared
# service the UI reaches over HTTP via AGENT_URL; it must never be co-located
# per-instance. A single frontend instance imports to ~30-50 MB RSS, so many fit
# on a Pi-class node (see reports/agent-terminal-ui-baseline-2026-06-11.md).
FROM python:3.13-slim AS build
WORKDIR /app
RUN pip install --no-cache-dir --upgrade pip build
COPY . .
RUN python -m build --wheel --outdir /dist

FROM python:3.13-slim
# Non-root, no build toolchain, no caches: minimal resident + image footprint.
RUN useradd --create-home --uid 10001 app
COPY --from=build /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -f /tmp/*.whl
USER app
ENV AGENT_URL="http://agent-utilities:8000" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["agent-terminal-ui"]
