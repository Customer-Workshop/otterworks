FROM mcr.microsoft.com/dotnet/sdk:9.0 AS builder

WORKDIR /app
COPY ApiGateway.csproj global.json ./
RUN dotnet restore ApiGateway.csproj

COPY . .
RUN dotnet publish ApiGateway.csproj -c Release -o /app/publish --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:9.0

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app/publish .

RUN useradd -u 1001 -m appuser
USER appuser

EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s CMD curl -f http://localhost:8080/health || exit 1
ENTRYPOINT ["dotnet", "ApiGateway.dll"]
