package org.ehrbase.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.ehrbase.configuration.config.validation.ExternalValidationProperties;
import org.ehrbase.configuration.config.validation.ExternalValidationProperties.BillingProfile;
import org.ehrbase.configuration.config.validation.ExternalValidationProperties.CodeSystems;
import org.ehrbase.configuration.config.validation.ExternalValidationProperties.Strictness;
import org.ehrbase.model.Composition;
import org.ehrbase.model.DvCodedText;
import org.ehrbase.service.validation.BillingCategory;
import org.ehrbase.service.validation.BillingCodeValidator;
import org.ehrbase.service.validation.ConstraintViolation;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class ValidationServiceImpTest {

    private static final String ICD10_SYSTEM = "http://hl7.org/fhir/sid/icd-10-cm";

    @Mock
    private BillingCodeValidator billingCodeValidator;

    private ExternalValidationProperties properties;

    @BeforeEach
    void setUp() {
        properties = new ExternalValidationProperties();
    }

    @Nested
    class WhenExternalValidationDisabled {

        @Test
        void shouldNotRunBillingValidation() {
            properties.setEnabled(false);
            var service = new ValidationServiceImp(properties, billingCodeValidator);
            var composition = compositionWithDiagnosisCode();

            List<ConstraintViolation> violations = service.check(composition);

            assertThat(violations).isEmpty();
            verify(billingCodeValidator, never()).validate(any(), any(), any());
        }
    }

    @Nested
    class WhenExternalValidationEnabled {

        @BeforeEach
        void enable() {
            properties.setEnabled(true);
        }

        @Test
        void shouldSkipDisabledBillingProfiles() {
            var disabledProfile = buildProfile(false);
            properties.setBillingProfiles(Map.of("disabled-profile", disabledProfile));
            var service = new ValidationServiceImp(properties, billingCodeValidator);
            var composition = compositionWithDiagnosisCode();

            List<ConstraintViolation> violations = service.check(composition);

            assertThat(violations).isEmpty();
            verify(billingCodeValidator, never()).validate(any(), any(), any());
        }

        @Test
        void shouldRunBillingValidationForEnabledProfile() {
            var enabledProfile = buildProfile(true);
            properties.setBillingProfiles(Map.of("us-hospital", enabledProfile));
            var service = new ValidationServiceImp(properties, billingCodeValidator);
            var composition = compositionWithDiagnosisCode();

            when(billingCodeValidator.validate(composition, "us-hospital", enabledProfile))
                    .thenReturn(List.of());

            List<ConstraintViolation> violations = service.check(composition);

            assertThat(violations).isEmpty();
            verify(billingCodeValidator).validate(composition, "us-hospital", enabledProfile);
        }

        @Test
        void shouldAggregateViolationsFromMultipleProfiles() {
            var profile1 = buildProfile(true);
            var profile2 = buildProfile(true);
            Map<String, BillingProfile> profiles = new LinkedHashMap<>();
            profiles.put("profile-a", profile1);
            profiles.put("profile-b", profile2);
            properties.setBillingProfiles(profiles);

            var service = new ValidationServiceImp(properties, billingCodeValidator);
            var composition = compositionWithDiagnosisCode();

            var violation1 = new ConstraintViolation(
                    "/content[0]", "BAD1", ICD10_SYSTEM, "profile-a",
                    BillingCategory.DIAGNOSIS, "Invalid code BAD1");
            var violation2 = new ConstraintViolation(
                    "/content[1]", "BAD2", ICD10_SYSTEM, "profile-b",
                    BillingCategory.DIAGNOSIS, "Invalid code BAD2");

            when(billingCodeValidator.validate(composition, "profile-a", profile1))
                    .thenReturn(List.of(violation1));
            when(billingCodeValidator.validate(composition, "profile-b", profile2))
                    .thenReturn(List.of(violation2));

            List<ConstraintViolation> violations = service.check(composition);

            assertThat(violations).hasSize(2);
            assertThat(violations).containsExactly(violation1, violation2);
        }

        @Test
        void shouldReturnEmptyWhenNoBillingProfilesConfigured() {
            properties.setBillingProfiles(Map.of());
            var service = new ValidationServiceImp(properties, billingCodeValidator);
            var composition = compositionWithDiagnosisCode();

            List<ConstraintViolation> violations = service.check(composition);

            assertThat(violations).isEmpty();
        }
    }

    @Nested
    class EdgeCases {

        @Test
        void shouldThrowForNullComposition() {
            properties.setEnabled(false);
            var service = new ValidationServiceImp(properties, billingCodeValidator);

            assertThatThrownBy(() -> service.check(null))
                    .isInstanceOf(IllegalArgumentException.class)
                    .hasMessage("composition must not be null");
        }

        @Test
        void shouldHandleCompositionWithNoCodes() {
            properties.setEnabled(true);
            var enabledProfile = buildProfile(true);
            properties.setBillingProfiles(Map.of("us-hospital", enabledProfile));
            var service = new ValidationServiceImp(properties, billingCodeValidator);
            var emptyComposition = new Composition(UUID.randomUUID(), List.of());

            when(billingCodeValidator.validate(emptyComposition, "us-hospital", enabledProfile))
                    .thenReturn(List.of());

            List<ConstraintViolation> violations = service.check(emptyComposition);
            assertThat(violations).isEmpty();
        }
    }

    private static BillingProfile buildProfile(boolean enabled) {
        var codeSystems = new CodeSystems();
        codeSystems.setDiagnosis(List.of(ICD10_SYSTEM));
        codeSystems.setProcedure(List.of("http://www.ama-assn.org/go/cpt"));
        codeSystems.setClinicalJustification(List.of("http://snomed.info/sct"));

        var strictness = new Strictness();
        strictness.setFailOnUnknownSystem(false);
        strictness.setRequireAllCategories(false);

        var profile = new BillingProfile();
        profile.setEnabled(enabled);
        profile.setCodeSystems(codeSystems);
        profile.setStrictness(strictness);
        return profile;
    }

    private static Composition compositionWithDiagnosisCode() {
        return new Composition(UUID.randomUUID(), List.of(
                new DvCodedText(ICD10_SYSTEM, "J06.9", "Acute URI", "/content[0]")));
    }
}
