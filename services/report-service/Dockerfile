FROM mcr.microsoft.com/dotnet/sdk:9.0 AS build
WORKDIR /src
COPY ReportService.csproj .
RUN dotnet restore
COPY . .
RUN dotnet publish -c Release -o /app

FROM mcr.microsoft.com/dotnet/aspnet:9.0
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN mkdir -p /tmp/reports
COPY --from=build /app .
RUN useradd -r -u 1001 appuser && chown appuser:appuser /tmp/reports
USER appuser
EXPOSE 8091
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8091/health || exit 1
ENTRYPOINT ["dotnet", "ReportService.dll"]
