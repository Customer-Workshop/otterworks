package com.otterworks.auth.config;

import static org.assertj.core.api.Assertions.*;

import java.util.List;
import org.flywaydb.core.api.ErrorCode;
import org.flywaydb.core.api.ErrorDetails;
import org.flywaydb.core.api.output.ValidateOutput;
import org.flywaydb.core.api.output.ValidateResult;
import org.junit.jupiter.api.Test;

class FlywayConfigTest {

  private static ValidateResult result(ValidateOutput... invalid) {
    return new ValidateResult(
        "10", "postgresql", null, invalid.length == 0, 0, List.of(invalid), List.of());
  }

  private static ValidateOutput output(String version, ErrorCode code) {
    return new ValidateOutput(
        version, "desc", "V" + version + "__desc.sql", new ErrorDetails(code, "x"));
  }

  @Test
  void repairsOnlyV1ChecksumMismatch() {
    assertThat(
            FlywayConfig.onlyRepairableChecksumMismatch(
                result(output("1", ErrorCode.CHECKSUM_MISMATCH))))
        .isTrue();
  }

  @Test
  void doesNotRepairOtherVersionsOrErrors() {
    assertThat(
            FlywayConfig.onlyRepairableChecksumMismatch(
                result(output("2", ErrorCode.CHECKSUM_MISMATCH))))
        .isFalse();
    assertThat(
            FlywayConfig.onlyRepairableChecksumMismatch(
                result(
                    output("1", ErrorCode.CHECKSUM_MISMATCH),
                    output("3", ErrorCode.RESOLVED_VERSIONED_MIGRATION_NOT_APPLIED))))
        .isFalse();
    assertThat(FlywayConfig.onlyRepairableChecksumMismatch(result())).isFalse();
  }
}
