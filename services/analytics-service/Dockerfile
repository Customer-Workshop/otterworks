FROM sbtscala/scala-sbt:eclipse-temurin-17.0.10_7_1.9.9_3.4.0 AS builder

WORKDIR /app
COPY build.sbt project/ ./project/
COPY project/build.properties project/plugins.sbt ./project/
RUN sbt update || true

COPY src ./src
RUN sbt assembly

FROM eclipse-temurin:17-jre-alpine
RUN apk --no-cache add curl
WORKDIR /app
COPY --from=builder /app/target/scala-3.4.0/analytics-service-assembly-*.jar app.jar

EXPOSE 8088
HEALTHCHECK --interval=10s --timeout=3s CMD curl -f http://localhost:8088/health || exit 1
ENTRYPOINT ["java", "-jar", "app.jar"]
