package com.otterworks.auth.config;

import java.security.SecureRandom;
import java.util.Base64;
import java.util.Map;
import org.flywaydb.core.api.output.ValidateResult;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.flyway.FlywayConfigurationCustomizer;
import org.springframework.boot.autoconfigure.flyway.FlywayMigrationStrategy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

/**
 * Supplies the {@code seed_admin_password_hash} Flyway placeholder used by the initial users
 * migration. The hash is derived at startup from {@code auth.seed.admin-password}; when that
 * property is empty the seeded admin account gets an unusable random password.
 */
@Configuration
public class SeedAdminFlywayConfig {

  private static final String PLACEHOLDER = "seed_admin_password_hash";

  private final String seedAdminPassword;

  public SeedAdminFlywayConfig(@Value("${auth.seed.admin-password:}") String seedAdminPassword) {
    this.seedAdminPassword = seedAdminPassword;
  }

  @Bean
  public FlywayConfigurationCustomizer seedAdminPlaceholderCustomizer() {
    String password =
        seedAdminPassword == null || seedAdminPassword.isBlank()
            ? randomPassword()
            : seedAdminPassword;
    String hash = new BCryptPasswordEncoder(10).encode(password);
    return configuration -> configuration.placeholders(Map.of(PLACEHOLDER, hash));
  }

  /**
   * Repairs the schema history before migrating when validation fails, so databases that applied
   * the previous checksum of the initial users migration still start.
   */
  @Bean
  public FlywayMigrationStrategy repairThenMigrateStrategy() {
    return flyway -> {
      ValidateResult validation = flyway.validateWithResult();
      if (!validation.validationSuccessful) {
        flyway.repair();
      }
      flyway.migrate();
    };
  }

  private static String randomPassword() {
    byte[] bytes = new byte[32];
    new SecureRandom().nextBytes(bytes);
    return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
  }
}
