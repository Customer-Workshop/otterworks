FROM mcr.microsoft.com/dotnet/sdk:9.0 AS builder

WORKDIR /app
COPY NotificationService.csproj ./
RUN dotnet restore

COPY . .
RUN dotnet publish -c Release -o /out

FROM mcr.microsoft.com/dotnet/aspnet:9.0
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /out .

RUN useradd -r -u 1001 appuser
USER appuser

EXPOSE 8086
HEALTHCHECK --interval=10s --timeout=3s CMD curl -f http://localhost:8086/health || exit 1
ENTRYPOINT ["dotnet", "NotificationService.dll"]
