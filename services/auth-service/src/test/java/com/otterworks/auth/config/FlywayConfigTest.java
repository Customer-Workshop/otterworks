package com.otterworks.auth.config;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;
import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.FlywayException;
import org.flywaydb.core.api.MigrationInfo;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.FileSystemResource;

class FlywayConfigTest {

  private static final String OLD_V1 =
      "CREATE TABLE t1 (id INT);\n-- seed: INSERT INTO t1 VALUES (1);\n";
  private static final String NEW_V1 = "CREATE TABLE t1 (id INT);\n";
  private static final String V2 = "CREATE TABLE t2 (id INT);\n";
  private static final String V3 = "CREATE TABLE t3 (id INT);\n";

  @TempDir Path tmp;

  @Test
  void checksumOf_matchesFlywayChecksumForCurrentV1() throws IOException {
    Path pending = migrations("pending", Map.of("V1__create_users_table.sql", currentV1()));
    Flyway flyway = flyway("checksum", pending);

    MigrationInfo v1 = flyway.info().pending()[0];
    assertThat(v1.getChecksum())
        .isEqualTo(FlywayConfig.checksumOf(new ClassPathResource(FlywayConfig.V1_RESOURCE)));
  }

  @Test
  void seededAdminChecksum_isNotTheCurrentV1Checksum() {
    assertThat(FlywayConfig.checksumOf(new ClassPathResource(FlywayConfig.V1_RESOURCE)))
        .isNotEqualTo(FlywayConfig.SEEDED_ADMIN_V1_CHECKSUM);
  }

  @Test
  void legacyV1_isRealignedAndLaterMigrationsRun() throws IOException {
    Path old = migrations("old", Map.of("V1__init.sql", OLD_V1, "V2__two.sql", V2));
    Path current =
        migrations("cur", Map.of("V1__init.sql", NEW_V1, "V2__two.sql", V2, "V3__three.sql", V3));
    flyway("upgrade", old).migrate();

    Flyway flyway = flyway("upgrade", current);
    int oldChecksum = FlywayConfig.checksumOf(new FileSystemResource(old.resolve("V1__init.sql")));
    int newChecksum =
        FlywayConfig.checksumOf(new FileSystemResource(current.resolve("V1__init.sql")));
    assertThat(checksums(flyway)).containsEntry("1", oldChecksum);
    assertThatThrownBy(flyway::validate).isInstanceOf(FlywayException.class);

    assertThat(FlywayConfig.realignVersionOne(flyway, oldChecksum, newChecksum)).isEqualTo(1);
    flyway.migrate();

    Map<String, Integer> after = checksums(flyway);
    assertThat(after).containsEntry("1", newChecksum);
    assertThat(after).containsKey("3");
  }

  @Test
  void realign_leavesUnrelatedDriftToNormalValidation() throws IOException {
    Path old = migrations("old2", Map.of("V1__init.sql", OLD_V1, "V2__two.sql", V2));
    Path drifted =
        migrations("drift", Map.of("V1__init.sql", NEW_V1, "V2__two.sql", V2 + "-- edited\n"));
    flyway("drift", old).migrate();

    Flyway flyway = flyway("drift", drifted);
    Map<String, Integer> before = checksums(flyway);
    int oldChecksum = FlywayConfig.checksumOf(new FileSystemResource(old.resolve("V1__init.sql")));
    int newChecksum =
        FlywayConfig.checksumOf(new FileSystemResource(drifted.resolve("V1__init.sql")));

    assertThat(FlywayConfig.realignVersionOne(flyway, oldChecksum, newChecksum)).isEqualTo(1);
    assertThat(checksums(flyway)).containsEntry("2", before.get("2"));
    assertThatThrownBy(flyway::migrate).isInstanceOf(FlywayException.class);
  }

  @Test
  void realign_isNoOpWhenV1HasAnotherChecksum() throws IOException {
    Path current = migrations("noop", Map.of("V1__init.sql", NEW_V1));
    Flyway flyway = flyway("noop", current);
    flyway.migrate();

    assertThat(FlywayConfig.appliedWithSeededAdminV1(flyway)).isFalse();
    assertThat(FlywayConfig.realignVersionOne(flyway, 12345, 6789)).isZero();
    flyway.migrate();
  }

  private Flyway flyway(String db, Path location) {
    return Flyway.configure()
        .dataSource("jdbc:h2:mem:flyway_" + db + ";DB_CLOSE_DELAY=-1", "sa", "")
        .locations("filesystem:" + location)
        .load();
  }

  private Path migrations(String name, Map<String, String> files) throws IOException {
    Path dir = Files.createDirectories(tmp.resolve(name));
    for (Map.Entry<String, String> e : files.entrySet()) {
      Files.writeString(dir.resolve(e.getKey()), e.getValue(), StandardCharsets.UTF_8);
    }
    return dir;
  }

  private static String currentV1() throws IOException {
    return new ClassPathResource(FlywayConfig.V1_RESOURCE)
        .getContentAsString(StandardCharsets.UTF_8);
  }

  private static Map<String, Integer> checksums(Flyway flyway) {
    return Arrays.stream(flyway.info().applied())
        .collect(Collectors.toMap(m -> m.getVersion().getVersion(), MigrationInfo::getChecksum));
  }
}
