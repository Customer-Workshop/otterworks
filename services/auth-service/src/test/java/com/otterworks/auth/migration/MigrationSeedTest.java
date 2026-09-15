package com.otterworks.auth.migration;

import static org.assertj.core.api.Assertions.*;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;

/** Migrations must never seed login credentials: accounts are bootstrapped from the environment. */
class MigrationSeedTest {

  private static final Pattern USER_INSERT =
      Pattern.compile("INSERT\\s+INTO\\s+users\\b", Pattern.CASE_INSENSITIVE);
  private static final Pattern BCRYPT_HASH = Pattern.compile("\\$2[aby]\\$\\d{2}\\$");

  @Test
  void migrations_shouldNotSeedUsersOrPasswordHashes() throws IOException {
    Resource[] migrations =
        new PathMatchingResourcePatternResolver().getResources("classpath:db/migration/*.sql");
    assertThat(migrations).isNotEmpty();

    for (Resource migration : migrations) {
      String sql = migration.getContentAsString(StandardCharsets.UTF_8);
      assertThat(USER_INSERT.matcher(sql).find())
          .as("%s inserts into users", migration.getFilename())
          .isFalse();
      assertThat(BCRYPT_HASH.matcher(sql).find())
          .as("%s contains a bcrypt password hash", migration.getFilename())
          .isFalse();
    }
  }
}
