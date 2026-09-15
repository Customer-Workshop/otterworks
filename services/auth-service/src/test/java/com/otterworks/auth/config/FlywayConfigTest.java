package com.otterworks.auth.config;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.MigrationInfo;
import org.flywaydb.core.api.MigrationInfoService;
import org.flywaydb.core.api.MigrationVersion;
import org.flywaydb.core.api.output.RepairResult;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;

class FlywayConfigTest {

  private Flyway flyway;
  private MigrationInfoService infoService;

  @BeforeEach
  void setUp() {
    flyway = mock(Flyway.class);
    infoService = mock(MigrationInfoService.class);
    when(flyway.info()).thenReturn(infoService);
    when(flyway.repair()).thenReturn(new RepairResult("10", "otterworks"));
  }

  @Test
  void freshDatabase_shouldOnlyMigrate() {
    when(infoService.applied()).thenReturn(new MigrationInfo[0]);

    new FlywayConfig().flywayMigrationStrategy().migrate(flyway);

    verify(flyway, never()).repair();
    verify(flyway).migrate();
  }

  @Test
  void databaseWithCurrentV1_shouldOnlyMigrate() {
    MigrationInfo[] applied = {applied("1", 123456)};
    when(infoService.applied()).thenReturn(applied);

    new FlywayConfig().flywayMigrationStrategy().migrate(flyway);

    verify(flyway, never()).repair();
    verify(flyway).migrate();
  }

  @Test
  void databaseWithSeededAdminV1_shouldRepairBeforeMigrating() {
    MigrationInfo[] applied = {
      applied("1", FlywayConfig.SEEDED_ADMIN_V1_CHECKSUM), applied("2", 42)
    };
    when(infoService.applied()).thenReturn(applied);

    new FlywayConfig().flywayMigrationStrategy().migrate(flyway);

    InOrder order = inOrder(flyway);
    order.verify(flyway).repair();
    order.verify(flyway).migrate();
  }

  @Test
  void seededChecksumOnOtherVersion_shouldNotRepair() {
    MigrationInfo[] applied = {applied("2", FlywayConfig.SEEDED_ADMIN_V1_CHECKSUM)};
    when(infoService.applied()).thenReturn(applied);

    assertThat(FlywayConfig.appliedWithSeededAdminV1(flyway)).isFalse();
  }

  private static MigrationInfo applied(String version, int checksum) {
    MigrationInfo info = mock(MigrationInfo.class);
    when(info.getVersion()).thenReturn(MigrationVersion.fromVersion(version));
    when(info.getChecksum()).thenReturn(checksum);
    return info;
  }
}
