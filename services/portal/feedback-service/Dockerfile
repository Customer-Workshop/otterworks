# feedback-service image, from services/portal/skeleton/Dockerfile.
#
# The build context is services/portal (see docker-compose.portal.yml) because the module
# needs the parent pom and portal-common. Do not build from the module directory.
FROM maven:3.9-eclipse-temurin-21 AS builder

WORKDIR /build
COPY pom.xml .
COPY portal-common/pom.xml portal-common/
COPY feedback-service/pom.xml feedback-service/
RUN mvn -B -pl portal-common,feedback-service -am dependency:go-offline

COPY portal-common/src portal-common/src
COPY feedback-service/src feedback-service/src
RUN mvn -B -pl portal-common,feedback-service -am package -DskipTests

FROM eclipse-temurin:21-jre-jammy

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /build/feedback-service/target/app.jar app.jar

RUN useradd -r -u 1001 appuser
USER appuser

EXPOSE 8103
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8103/health || exit 1

ENTRYPOINT ["java", "-jar", "app.jar"]
