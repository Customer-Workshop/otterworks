# syntax=docker/dockerfile:1
# Build: Maven + Temurin 21. Pull the two base images once (docker pull …) and reuse: public.ecr.aws is rate-limited.
FROM public.ecr.aws/docker/library/maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY docker/maven-settings.xml /root/.m2/settings.xml
COPY pom.xml .
RUN mvn -q -B -DskipTests dependency:go-offline || true
COPY src ./src
RUN mvn -q -B -DskipTests package && \
    java -Djarmode=tools -jar target/confirmations.jar extract --layers --destination /layers --launcher

# Run: non-root Temurin 21 JRE, Spring Boot layered so dependency layers cache across releases.
FROM public.ecr.aws/docker/library/eclipse-temurin:21-jre-jammy
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --home /app --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=build --chown=app:app /layers/dependencies/ ./
COPY --from=build --chown=app:app /layers/spring-boot-loader/ ./
COPY --from=build --chown=app:app /layers/snapshot-dependencies/ ./
COPY --from=build --chown=app:app /layers/application/ ./
USER 10001:10001
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=70 -Djava.security.egd=file:/dev/./urandom" \
    SERVER_PORT=8080
EXPOSE 8080
ENTRYPOINT ["java", "org.springframework.boot.loader.launch.JarLauncher"]
