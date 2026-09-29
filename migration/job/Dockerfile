# Migration job image (CONTRACTS.md §13.2): ldm + Db2 client (ibm_db clidriver) + PostgreSQL/S3/PySpark (local mode,
# needs a JRE) + GnuCOBOL. Azure SQL (msodbcsql18 + pyodbc) is opt-in: --build-arg WITH_AZURE=1.
# Build from the repo root so the whole migration/ tree lands at /app/migration:
#   docker build -f migration/job/Dockerfile -t ldm:dev .
FROM python:3.12-slim-bookworm AS base

ARG WITH_AZURE=0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ACCEPT_EULA=Y \
    DEBIAN_FRONTEND=noninteractive

# JRE for Spark local mode, GnuCOBOL runtime + compiler (unload_command wrapper; cobc needs gcc), clidriver deps;
# msodbcsql18 only when WITH_AZURE=1.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg ca-certificates gcc g++ make \
        libxml2 libpam0g gnucobol3 openjdk-17-jre-headless procps \
    && if [ "$WITH_AZURE" = "1" ]; then \
        apt-get install -y --no-install-recommends unixodbc unixodbc-dev \
        && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
        && echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
            > /etc/apt/sources.list.d/mssql-release.list \
        && apt-get update \
        && apt-get install -y --no-install-recommends msodbcsql18 mssql-tools18; \
    fi \
    && apt-get purge -y --auto-remove gnupg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ibm_db downloads the IBM Data Server Driver (clidriver) into site-packages at install time.
COPY migration/job/pyproject.toml /app/migration/job/pyproject.toml
COPY migration/job/ldm /app/migration/job/ldm
RUN pip install --upgrade pip \
    && pip install "/app/migration/job[db2,postgresql,s3,spark]" \
    && if [ "$WITH_AZURE" = "1" ]; then pip install "/app/migration/job[azuresql]" && apt-get purge -y --auto-remove unixodbc-dev; fi \
    && apt-get purge -y --auto-remove g++ \
    && rm -rf /var/lib/apt/lists/*

ENV IBM_DB_HOME=/usr/local/lib/python3.12/site-packages/clidriver \
    LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/clidriver/lib \
    PATH="/usr/local/lib/python3.12/site-packages/clidriver/bin:/opt/mssql-tools18/bin:${PATH}" \
    JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 \
    PYSPARK_PYTHON=/usr/local/bin/python \
    LOCAL_STAGING_DIR=/work/staging \
    LDM_HOST=eks

# The full migration tree (manifest, overlays, copybooks, unload wrapper, target DDL) at /app/migration.
COPY migration /app/migration
# Compile UNLOAD01 once at build time and prove it against the checked-in fixtures (make check).
RUN make -s -C /app/migration/source/unload build \
    && make -s -C /app/migration/source/unload check \
    && rm -rf /app/migration/source/unload/build

RUN groupadd --system --gid 10001 ldm \
    && useradd --system --uid 10001 --gid ldm --home /work ldm \
    && mkdir -p /work/staging \
    && chown -R ldm:ldm /work /app/migration

USER ldm
VOLUME ["/work/staging"]

ENTRYPOINT ["python", "-m", "ldm"]
CMD ["--help"]
