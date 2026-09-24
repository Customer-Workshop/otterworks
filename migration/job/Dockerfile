# Migration job image (CONTRACTS.md §13.2): ldm + Db2 client (ibm_db clidriver) + ODBC Driver 18 + GnuCOBOL.
# Build from the repo root so the whole migration/ tree lands at /app/migration:
#   docker build -f migration/job/Dockerfile -t ldm:dev .
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ACCEPT_EULA=Y \
    DEBIAN_FRONTEND=noninteractive

# msodbcsql18 (Azure SQL via pyodbc), GnuCOBOL runtime + compiler (unload_command wrapper; cobc needs gcc), clidriver deps.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg ca-certificates unixodbc unixodbc-dev gcc g++ \
        libxml2 libpam0g gnucobol3 \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
        > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends msodbcsql18 mssql-tools18 \
    && apt-get purge -y --auto-remove gnupg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ibm_db downloads the IBM Data Server Driver (clidriver) into site-packages at install time.
COPY migration/job/pyproject.toml /app/migration/job/pyproject.toml
COPY migration/job/ldm /app/migration/job/ldm
RUN pip install --upgrade pip \
    && pip install "/app/migration/job[db2,azuresql]" \
    && apt-get purge -y --auto-remove g++ unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

ENV IBM_DB_HOME=/usr/local/lib/python3.12/site-packages/clidriver \
    LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/clidriver/lib \
    PATH="/usr/local/lib/python3.12/site-packages/clidriver/bin:/opt/mssql-tools18/bin:${PATH}" \
    LOCAL_STAGING_DIR=/work/staging \
    LDM_HOST=eks

# The full migration tree (manifest, overlays, copybooks, unload wrapper, target DDL) at /app/migration.
COPY migration /app/migration

RUN groupadd --system --gid 10001 ldm \
    && useradd --system --uid 10001 --gid ldm --home /work ldm \
    && mkdir -p /work/staging \
    && chown -R ldm:ldm /work /app/migration

USER ldm
VOLUME ["/work/staging"]

ENTRYPOINT ["python", "-m", "ldm"]
CMD ["--help"]
