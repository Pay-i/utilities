# payi-n8n-toolkit — minimal container for running audit/migrate CLIs
#
# Usage:
#   docker build -t payi-n8n-toolkit .
#   docker run --rm \
#     -e N8N_BASE_URL -e N8N_API_KEY \
#     -e PAYI_BASE_URL -e PAYI_API_KEY \
#     -v $(pwd)/reports:/reports \
#     payi-n8n-toolkit \
#     python audit-configure-payi-proxy.py --out /reports/audit.json
#
# The toolkit is stdlib-only, so the image stays small.

FROM python:3.12-slim

LABEL org.opencontainers.image.title="payi-n8n-toolkit"
LABEL org.opencontainers.image.description="Audit and migrate n8n AI workflows to route through Pay-i"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

COPY audit-configure-payi-proxy.py \
     migrate-workflows-to-payi.py \
     migrate-to-payi.sh \
     migrate-openai-to-payi.sh \
     ./

# Make the shell scripts executable; Python files are run via the python entrypoint.
RUN chmod +x migrate-to-payi.sh migrate-openai-to-payi.sh

# Run as a non-root user so the container doesn't have root privileges
# at runtime. The user owns /app so volume mounts under /reports remain
# writable when the host directory permits.
RUN useradd --create-home --uid 1000 --shell /bin/bash toolkit && \
    chown -R toolkit:toolkit /app
USER toolkit

# Default to the audit script with --help so `docker run payi-n8n-toolkit`
# does something useful instead of hanging on stdin.
ENTRYPOINT ["python"]
CMD ["audit-configure-payi-proxy.py", "--help"]
