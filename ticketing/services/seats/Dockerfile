# syntax=docker/dockerfile:1
# Build stage — the base images are rate-limited; log in to public ECR first
# (aws ecr-public get-login-password | docker login public.ecr.aws) and reuse the pulled layers.
FROM public.ecr.aws/docker/library/maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build
COPY docker/maven-settings.xml /build/maven-settings.xml
COPY pom.xml .
RUN --mount=type=cache,target=/root/.m2 mvn -B -q -s /build/maven-settings.xml -DskipTests dependency:go-offline || true
COPY src ./src
RUN --mount=type=cache,target=/root/.m2 mvn -B -q -s /build/maven-settings.xml -DskipTests package && cp target/seats.jar /build/app.jar

FROM public.ecr.aws/docker/library/eclipse-temurin:21-jre-alpine
RUN addgroup -S seats && adduser -S -G seats -h /app seats
WORKDIR /app
COPY --from=build --chown=seats:seats /build/app.jar /app/app.jar
USER seats
EXPOSE 8080
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=75 -XX:+UseSerialGC -Djava.security.egd=file:/dev/./urandom"
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s CMD wget -q -O- http://127.0.0.1:8080/actuator/health || exit 1
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
