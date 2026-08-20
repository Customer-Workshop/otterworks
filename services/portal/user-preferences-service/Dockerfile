# User Preferences service image, copied from services/portal/skeleton/Dockerfile.
#
# The build context is services/portal (see docker-compose.portal.yml) because the module
# needs the parent pom and portal-common. Do not build from the module directory.
#
# The image contains only this service: the parent is installed non-recursively (-N) and each
# module is built with -f, so the other services listed in <modules> are never copied and their
# absence from the context is not an error. Do not switch to a -pl/-am reactor build; that
# collects every module and fails on the ones this image deliberately leaves out.
FROM maven:3.9-eclipse-temurin-21 AS builder

WORKDIR /build
COPY pom.xml .
RUN mvn -B -N install

COPY portal-common/pom.xml portal-common/
RUN mvn -B -f portal-common/pom.xml dependency:go-offline
COPY portal-common/src portal-common/src
RUN mvn -B -f portal-common/pom.xml install -DskipTests

COPY user-preferences-service/pom.xml user-preferences-service/
RUN mvn -B -f user-preferences-service/pom.xml dependency:go-offline
COPY user-preferences-service/src user-preferences-service/src
RUN mvn -B -f user-preferences-service/pom.xml package -DskipTests

FROM eclipse-temurin:21-jre-jammy

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /build/user-preferences-service/target/app.jar app.jar

RUN useradd -r -u 1001 appuser
USER appuser

EXPOSE 8102
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8102/health || exit 1

ENTRYPOINT ["java", "-jar", "app.jar"]
