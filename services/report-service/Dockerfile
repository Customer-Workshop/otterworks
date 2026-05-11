FROM mcr.microsoft.com/dotnet/sdk:9.0 AS builder
WORKDIR /app
COPY *.csproj .
RUN dotnet restore
COPY . .
RUN dotnet publish -c Release -o /publish

FROM mcr.microsoft.com/dotnet/aspnet:9.0
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /tmp/reports
COPY --from=builder /publish .
RUN useradd -r -u 1001 appuser && chown appuser:appuser /tmp/reports
USER appuser
EXPOSE 8091
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8091/health || exit 1
ENTRYPOINT ["dotnet", "ReportService.dll"]
