# Java 17 / Spring Boot 3.2 — the modernized stack for the feedback context extracted out of
# legacy-portal (which stays on Java 11 / Boot 2.7).
FROM maven:3.9-eclipse-temurin-17 AS builder

WORKDIR /app
COPY pom.xml .
# Download dependencies first for Docker layer caching.
RUN mvn -B dependency:go-offline

COPY src/ src/
RUN mvn -B package -DskipTests

FROM eclipse-temurin:17-jre-jammy

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app/target/feedback-service.jar app.jar

RUN useradd -r -u 1001 appuser
USER appuser

EXPOSE 8096
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8096/health || exit 1

ENTRYPOINT ["java", "-jar", "app.jar"]
