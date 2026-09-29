package com.otterworks.ticketing.orders.support;

import io.zonky.test.db.postgres.embedded.EmbeddedPostgres;
import java.io.IOException;
import java.io.UncheckedIOException;
import org.springframework.boot.test.util.TestPropertyValues;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;

/** Starts one embedded PostgreSQL per JVM (no Docker) and points the datasource at it. */
public class EmbeddedPostgresInitializer implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    private static final EmbeddedPostgres POSTGRES = start();

    private static EmbeddedPostgres start() {
        try {
            EmbeddedPostgres pg = EmbeddedPostgres.builder().start();
            Runtime.getRuntime().addShutdownHook(new Thread(() -> {
                try {
                    pg.close();
                } catch (IOException ignored) {
                    // JVM is exiting
                }
            }));
            return pg;
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        TestPropertyValues.of(
                "spring.datasource.url=" + POSTGRES.getJdbcUrl("postgres", "postgres"),
                "spring.datasource.username=postgres",
                "spring.datasource.password=postgres"
        ).applyTo(context.getEnvironment());
    }
}
