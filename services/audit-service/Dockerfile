FROM mcr.microsoft.com/dotnet/sdk:8.0 AS builder

WORKDIR /app
COPY *.csproj ./
RUN dotnet restore

COPY . .
RUN dotnet publish -c Release -o /out

# glibc-based runtime: the IBM Db2 .NET provider (Net.IBM.Data.Db2-lnx) ships native
# libraries that do not load on musl/Alpine.
FROM mcr.microsoft.com/dotnet/aspnet:8.0
RUN apt-get update && apt-get install -y --no-install-recommends curl libxml2 libicu72 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /out .
ENV LD_LIBRARY_PATH=/app/clidriver/lib

RUN useradd -u 1001 -m appuser
USER appuser

EXPOSE 8090
HEALTHCHECK --interval=10s --timeout=3s CMD curl -f http://localhost:8090/health || exit 1
ENTRYPOINT ["dotnet", "AuditService.dll"]
