# Skeleton Dockerfile for an extracted portal service. Copy to
# services/portal/<context>-service/Dockerfile and replace <context> and <port>.
#
# The build context is services/portal (see docker-compose.portal.yml) because the module
# needs the parent pom and portal-common. Do not build from the module directory.
FROM maven:3.9-eclipse-temurin-21 AS builder

WORKDIR /build
COPY pom.xml .
COPY portal-common/pom.xml portal-common/
COPY <context>-service/pom.xml <context>-service/
RUN mvn -B -pl portal-common,<context>-service -am dependency:go-offline

COPY portal-common/src portal-common/src
COPY <context>-service/src <context>-service/src
RUN mvn -B -pl portal-common,<context>-service -am package -DskipTests

FROM eclipse-temurin:21-jre-jammy

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /build/<context>-service/target/app.jar app.jar

RUN useradd -r -u 1001 appuser
USER appuser

EXPOSE <port>
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:<port>/health || exit 1

ENTRYPOINT ["java", "-jar", "app.jar"]
