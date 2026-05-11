FROM mcr.microsoft.com/dotnet/sdk:9.0 AS builder

WORKDIR /app
COPY *.csproj ./
RUN dotnet restore

COPY . .
RUN dotnet publish -c Release -o /out

FROM mcr.microsoft.com/dotnet/aspnet:9.0-alpine
RUN apk --no-cache add curl
WORKDIR /app
COPY --from=builder /out .

RUN adduser -D -u 1001 appuser
USER appuser

EXPOSE 8087
HEALTHCHECK --interval=10s --timeout=3s CMD curl -f http://localhost:8087/health || exit 1
ENTRYPOINT ["dotnet", "SearchService.dll"]
