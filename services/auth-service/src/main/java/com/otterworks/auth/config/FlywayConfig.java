package com.otterworks.auth.config;

import org.flywaydb.core.api.ErrorCode;
import org.flywaydb.core.api.output.ValidateOutput;
import org.flywaydb.core.api.output.ValidateResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.flyway.FlywayMigrationStrategy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class FlywayConfig {

  private static final Logger log = LoggerFactory.getLogger(FlywayConfig.class);

  /** V1 was rewritten to drop a committed credential; realign only that checksum. */
  static final String REPAIRABLE_VERSION = "1";

  @Bean
  public FlywayMigrationStrategy flywayMigrationStrategy() {
    return flyway -> {
      ValidateResult result = flyway.validateWithResult();
      if (!result.validationSuccessful && onlyRepairableChecksumMismatch(result)) {
        log.warn("Repairing Flyway checksum for migration V{}", REPAIRABLE_VERSION);
        flyway.repair();
      }
      flyway.migrate();
    };
  }

  static boolean onlyRepairableChecksumMismatch(ValidateResult result) {
    return result.invalidMigrations != null
        && !result.invalidMigrations.isEmpty()
        && result.invalidMigrations.stream().allMatch(FlywayConfig::isRepairable);
  }

  private static boolean isRepairable(ValidateOutput output) {
    return REPAIRABLE_VERSION.equals(output.version)
        && output.errorDetails != null
        && output.errorDetails.errorCode == ErrorCode.CHECKSUM_MISMATCH;
  }
}
