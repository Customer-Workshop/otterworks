package com.otterworks.ticketing.seats.support;

import io.zonky.test.db.postgres.embedded.EmbeddedPostgres;
import java.io.IOException;
import java.io.UncheckedIOException;
import javax.sql.DataSource;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

/** A real PostgreSQL (zonky embedded binaries, no Docker) so Flyway, the seed and SKIP LOCKED run as in production. */
@TestConfiguration
public class EmbeddedPostgresConfig {

    private static final class Holder {
        static final EmbeddedPostgres PG = start();

        private static EmbeddedPostgres start() {
            try {
                EmbeddedPostgres pg = EmbeddedPostgres.builder().start();
                Runtime.getRuntime().addShutdownHook(new Thread(() -> {
                    try {
                        pg.close();
                    } catch (IOException ignored) {
                        // shutting down anyway
                    }
                }));
                return pg;
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        }
    }

    @Bean
    @Primary
    DataSource dataSource() {
        return Holder.PG.getPostgresDatabase();
    }
}
