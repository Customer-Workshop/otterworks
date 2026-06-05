package com.otterworks.auth.migration;

import java.sql.PreparedStatement;
import org.flywaydb.core.api.migration.BaseJavaMigration;
import org.flywaydb.core.api.migration.Context;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

/**
 * Replaces the hardcoded bcrypt hash inserted by V1 with a freshly generated
 * one so the plaintext seed password no longer appears in the migration SQL.
 *
 * <p>The password is read from the {@code ADMIN_SEED_PASSWORD} environment
 * variable (defaults to {@code Admin123!} for local development).
 */
public class V5__RotateSeedAdminPassword extends BaseJavaMigration {

  private static final String SEED_ADMIN_ID = "a0000000-0000-0000-0000-000000000001";
  private static final String DEFAULT_PASSWORD = "Admin123!";

  @Override
  public void migrate(Context context) throws Exception {
    String password = System.getenv("ADMIN_SEED_PASSWORD");
    if (password == null || password.isEmpty()) {
      password = DEFAULT_PASSWORD;
    }

    BCryptPasswordEncoder encoder = new BCryptPasswordEncoder(12);
    String hash = encoder.encode(password);

    try (PreparedStatement stmt =
        context
            .getConnection()
            .prepareStatement(
                "UPDATE users SET password_hash = ?, updated_at = NOW() WHERE id = ?")) {
      stmt.setString(1, hash);
      stmt.setString(2, SEED_ADMIN_ID);
      stmt.executeUpdate();
    }
  }
}
