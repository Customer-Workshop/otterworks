package com.otterworks.auth.config;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.zip.CRC32;
import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.MigrationInfo;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.flyway.FlywayMigrationStrategy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration
public class FlywayConfig {

  private static final Logger log = LoggerFactory.getLogger(FlywayConfig.class);

  static final String V1_RESOURCE = "db/migration/V1__create_users_table.sql";

  /**
   * Checksum Flyway recorded for V1 while it still seeded the default admin account. Databases
   * carrying it were migrated before the seed was removed and need that one history row realigned
   * before validation, otherwise startup stops and V5 never removes the account. Only this row is
   * touched; every other applied migration keeps normal checksum validation.
   */
  static final int SEEDED_ADMIN_V1_CHECKSUM = -1077113232;

  @Bean
  public FlywayMigrationStrategy flywayMigrationStrategy() {
    return flyway -> {
      if (appliedWithSeededAdminV1(flyway)) {
        log.warn("Realigning Flyway history row for V1 applied with the seeded admin account");
        realignVersionOne(
            flyway, SEEDED_ADMIN_V1_CHECKSUM, checksumOf(new ClassPathResource(V1_RESOURCE)));
      }
      flyway.migrate();
    };
  }

  static boolean appliedWithSeededAdminV1(Flyway flyway) {
    return Arrays.stream(flyway.info().applied())
        .anyMatch(
            m ->
                isVersionOne(m)
                    && Integer.valueOf(SEEDED_ADMIN_V1_CHECKSUM).equals(m.getChecksum()));
  }

  static int realignVersionOne(Flyway flyway, int fromChecksum, int toChecksum) {
    org.flywaydb.core.api.configuration.Configuration config = flyway.getConfiguration();
    return new JdbcTemplate(config.getDataSource())
        .update(
            "UPDATE \""
                + config.getTable()
                + "\" SET \"checksum\" = ? WHERE \"version\" = '1' AND \"checksum\" = ?",
            toChecksum,
            fromChecksum);
  }

  /** Same algorithm Flyway uses for SQL migrations: CRC32 over each line, BOM stripped. */
  static int checksumOf(Resource resource) {
    CRC32 crc32 = new CRC32();
    try (BufferedReader reader =
        new BufferedReader(
            new InputStreamReader(resource.getInputStream(), StandardCharsets.UTF_8))) {
      String line = reader.readLine();
      if (line != null) {
        if (line.startsWith("\uFEFF")) {
          line = line.substring(1);
        }
        do {
          crc32.update(line.getBytes(StandardCharsets.UTF_8));
        } while ((line = reader.readLine()) != null);
      }
    } catch (IOException e) {
      throw new UncheckedIOException("Unable to checksum " + resource.getDescription(), e);
    }
    return (int) crc32.getValue();
  }

  private static boolean isVersionOne(MigrationInfo info) {
    return info.getVersion() != null && "1".equals(info.getVersion().getVersion());
  }
}
