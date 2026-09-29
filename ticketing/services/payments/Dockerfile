# Build: Maven + Temurin 21. Registries are rate-limited on this network: pull both bases once and reuse them.
FROM docker.io/library/maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY docker/maven-settings.xml /root/.m2/settings.xml
COPY pom.xml .
RUN mvn -q -B dependency:go-offline
COPY src ./src
RUN mvn -q -B -DskipTests package

# Run: Temurin 21 JRE, non-root
FROM docker.io/library/eclipse-temurin:21-jre
RUN groupadd --system --gid 10001 payments && useradd --system --uid 10001 --gid payments --home /app payments
WORKDIR /app
COPY --from=build --chown=payments:payments /src/target/payments.jar /app/payments.jar
USER 10001
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=70 -Djava.net.preferIPv4Stack=true"
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/payments.jar"]
