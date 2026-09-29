# Base images from the gcr mirror: Docker Hub and public.ecr.aws are rate-limited on this network.
# Build
FROM mirror.gcr.io/library/maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY docker/maven-settings.xml /root/.m2/settings.xml
COPY pom.xml .
RUN mvn -q -B dependency:go-offline
COPY src ./src
RUN mvn -q -B package -DskipTests

# Run: Temurin 21 JRE, non-root
FROM mirror.gcr.io/library/eclipse-temurin:21-jre
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --no-create-home app
WORKDIR /app
COPY --from=build --chown=app:app /src/target/orders.jar /app/orders.jar
USER 10001
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=70 -Djava.net.preferIPv4Stack=true"
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/orders.jar"]
