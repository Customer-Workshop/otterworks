package com.otterworks.auth.config;

import java.util.Arrays;
import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.MigrationInfo;
import org.flywaydb.core.api.output.RepairResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.flyway.FlywayMigrationStrategy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class FlywayConfig {

  private static final Logger log = LoggerFactory.getLogger(FlywayConfig.class);

  /**
   * Checksum Flyway recorded for V1 while it still seeded the default admin account. Databases
   * carrying it were migrated before the seed was removed and need their history realigned before
   * validation, otherwise startup stops and V5 never removes the account.
   */
  static final int SEEDED_ADMIN_V1_CHECKSUM = -1077113232;

  @Bean
  public FlywayMigrationStrategy flywayMigrationStrategy() {
    return flyway -> {
      if (appliedWithSeededAdminV1(flyway)) {
        log.warn("Realigning Flyway history for V1 applied with the seeded admin account");
        RepairResult result = flyway.repair();
        log.info("Flyway repair aligned migrations: {}", result.migrationsAligned);
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

  private static boolean isVersionOne(MigrationInfo info) {
    return info.getVersion() != null && "1".equals(info.getVersion().getVersion());
  }
}
