# Build
FROM public.ecr.aws/docker/library/maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY docker/maven-settings.xml /root/.m2/settings.xml
COPY pom.xml .
RUN mvn -q -B dependency:go-offline
COPY src ./src
RUN mvn -q -B package && \
    mvn -q -B dependency:copy -Dartifact=org.postgresql:postgresql:42.7.4 -DoutputDirectory=/src/target/lib

# Run: WildFly (Jakarta EE 10) with a Postgres datasource
FROM quay.io/wildfly/wildfly:32.0.1.Final-jdk21
USER root
COPY --from=build /src/target/lib/postgresql-42.7.4.jar /opt/jboss/postgresql.jar
COPY docker/configure-datasource.cli /opt/jboss/configure-datasource.cli
RUN chown jboss:jboss /opt/jboss/postgresql.jar && \
    /opt/jboss/wildfly/bin/jboss-cli.sh --file=/opt/jboss/configure-datasource.cli && \
    rm -rf /opt/jboss/wildfly/standalone/configuration/standalone_xml_history /opt/jboss/wildfly/standalone/data /opt/jboss/wildfly/standalone/log && \
    chown -R jboss:jboss /opt/jboss/wildfly
USER jboss
COPY --from=build --chown=jboss:jboss /src/target/boxoffice.war /opt/jboss/wildfly/standalone/deployments/ROOT.war
ENV JAVA_OPTS="-XX:MaxRAMPercentage=70 -Djava.net.preferIPv4Stack=true"
EXPOSE 8080
CMD ["/opt/jboss/wildfly/bin/standalone.sh", "-b", "0.0.0.0"]
