FROM gradle:8.6-jdk17 AS builder

WORKDIR /app
COPY build.gradle settings.gradle ./
COPY gradle ./gradle
RUN gradle dependencies --no-daemon || true

COPY src ./src
RUN gradle bootJar --no-daemon

FROM eclipse-temurin:17-jre-alpine
RUN apk --no-cache add curl
WORKDIR /app
COPY --from=builder /app/build/libs/*.jar app.jar

EXPOSE 8081
HEALTHCHECK --interval=15s --timeout=5s CMD curl -f http://localhost:8081/health || exit 1
ENTRYPOINT ["java", "-jar", "app.jar"]
