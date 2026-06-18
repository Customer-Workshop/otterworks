package org.ehrbase.service.validation;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.ehrbase.configuration.config.validation.ExternalValidationProperties.BillingProfile;
import org.ehrbase.configuration.config.validation.ExternalValidationProperties.CodeSystems;
import org.ehrbase.configuration.config.validation.ExternalValidationProperties.Strictness;
import org.ehrbase.model.Composition;
import org.ehrbase.model.DvCodedText;
import org.ehrbase.service.validation.FhirTerminologyValidation.CodePair;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Captor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class BillingCodeValidatorTest {

    private static final String ICD10_SYSTEM = "http://hl7.org/fhir/sid/icd-10-cm";
    private static final String CPT_SYSTEM = "http://www.ama-assn.org/go/cpt";
    private static final String HCPCS_SYSTEM = "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets";
    private static final String SNOMED_SYSTEM = "http://snomed.info/sct";

    @Mock
    private FhirTerminologyValidation fhirTerminologyValidation;

    @Captor
    private ArgumentCaptor<Set<CodePair>> codePairsCaptor;

    private BillingCodeValidator validator;
    private BillingProfile usHospitalProfile;

    @BeforeEach
    void setUp() {
        validator = new BillingCodeValidator(fhirTerminologyValidation);
        usHospitalProfile = buildUsHospitalProfile();
    }

    @Nested
    class ValidCodes {

        @Test
        void shouldReturnNoViolationsForValidIcd10Code() {
            var composition = compositionWith(
                    new DvCodedText(ICD10_SYSTEM, "J06.9", "Acute upper respiratory infection", "/content[0]"));

            when(fhirTerminologyValidation.validateCodes(any()))
                    .thenReturn(Map.of(new CodePair(ICD10_SYSTEM, "J06.9"), true));

            List<ConstraintViolation> violations =
                    validator.validate(composition, "us-hospital", usHospitalProfile);

            assertThat(violations).isEmpty();
        }

        @Test
        void shouldReturnNoViolationsForValidCptCode() {
            var composition = compositionWith(
                    new DvCodedText(CPT_SYSTEM, "99213", "Office visit", "/content[1]"));

            when(fhirTerminologyValidation.validateCodes(any()))
                    .thenReturn(Map.of(new CodePair(CPT_SYSTEM, "99213"), true));

            List<ConstraintViolation> violations =
                    validator.validate(composition, "us-hospital", usHospitalProfile);

            assertThat(violations).isEmpty();
        }

        @Test
        void shouldReturnNoViolationsForValidHcpcsCode() {
            var composition = compositionWith(
                    new DvCodedText(HCPCS_SYSTEM, "G0101", "Cervical cancer screening", "/content[2]"));

            when(fhirTerminologyValidation.validateCodes(any()))
                    .thenReturn(Map.of(new CodePair(HCPCS_SYSTEM, "G0101"), true));

            List<ConstraintViolation> violations =
                    validator.validate(composition, "us-hospital", usHospitalProfile);

            assertThat(violations).isEmpty();
        }

        @Test
        void shouldReturnNoViolationsForValidSnomedCode() {
            var composition = compositionWith(
                    new DvCodedText(SNOMED_SYSTEM, "386661006", "Fever", "/content[3]"));

            when(fhirTerminologyValidation.validateCodes(any()))
                    .thenReturn(Map.of(new CodePair(SNOMED_SYSTEM, "386661006"), true));

            List<ConstraintViolation> violations =
                    validator.validate(composition, "us-hospital", usHospitalProfile);

            assertThat(violations).isEmpty();
        }
    }

    @Nested
    class InvalidCodes {

        @Test
        void shouldReturnViolationForInvalidIcd10Code() {
            var composition = compositionWith(
                    new DvCodedText(ICD10_SYSTEM, "INVALID", "Bad code", "/content[0]"));

            when(fhirTerminologyValidation.validateCodes(any()))
                    .thenReturn(Map.of(new CodePair(ICD10_SYSTEM, "INVALID"), false));

            List<ConstraintViolation> violations =
                    validator.validate(composition, "us-hospital", usHospitalProfile);

            assertThat(violations).hasSize(1);
            ConstraintViolation violation = violations.getFirst();
            assertThat(violation.failedCode()).isEqualTo("INVALID");
            assertThat(violation.codeSystem()).isEqualTo(ICD10_SYSTEM);
            assertThat(violation.billingProfile()).isEqualTo("us-hospital");
            assertThat(violation.category()).isEqualTo(BillingCategory.DIAGNOSIS);
            assertThat(violation.path()).isEqualTo("/content[0]");
        }

        @Test
        void shouldReturnViolationForInvalidCptCode() {
            var composition = compositionWith(
                    new DvCodedText(CPT_SYSTEM, "00000", "Unknown procedure", "/content[1]"));

            when(fhirTerminologyValidation.validateCodes(any()))
                    .thenReturn(Map.of(new CodePair(CPT_SYSTEM, "00000"), false));

            List<ConstraintViolation> violations =
                    validator.validate(composition, "us-hospital", usHospitalProfile);

            assertThat(violations).hasSize(1);
            assertThat(violations.getFirst().category()).isEqualTo(BillingCategory.PROCEDURE);
        }

        @Test
        void shouldReturnViolationForInvalidSnomedCode() {
            var composition = compositionWith(
                    new DvCodedText(SNOMED_SYSTEM, "0000000", "Invalid SNOMED", "/content[3]"));

            when(fhirTerminologyValidation.validateCodes(any()))
                    .thenReturn(Map.of(new CodePair(SNOMED_SYSTEM, "0000000"), false));

            List<ConstraintViolation> violations =
                    validator.validate(composition, "us-hospital", usHospitalProfile);

            assertThat(violations).hasSize(1);
            assertThat(violations.getFirst().category())
                    .isEqualTo(BillingCategory.CLINICAL_JUSTIFICATION);
        }
    }

    @Nested
    class Deduplication {

        @Test
        void shouldDeduplicateIdenticalCodePairsBeforeValidation() {
            var composition = compositionWith(
                    new DvCodedText(ICD10_SYSTEM, "J06.9", "Acute URI", "/content[0]"),
                    new DvCodedText(ICD10_SYSTEM, "J06.9", "Acute URI duplicate", "/content[1]"));

            when(fhirTerminologyValidation.validateCodes(codePairsCaptor.capture()))
                    .thenReturn(Map.of(new CodePair(ICD10_SYSTEM, "J06.9"), true));

            validator.validate(composition, "us-hospital", usHospitalProfile);

            assertThat(codePairsCaptor.getValue()).hasSize(1);
        }

        @Test
        void shouldReportOneViolationPerFailedUniquePair() {
            var composition = compositionWith(
                    new DvCodedText(ICD10_SYSTEM, "BAD", "Bad 1", "/content[0]"),
                    new DvCodedText(ICD10_SYSTEM, "BAD", "Bad 2", "/content[1]"));

            when(fhirTerminologyValidation.validateCodes(any()))
                    .thenReturn(Map.of(new CodePair(ICD10_SYSTEM, "BAD"), false));

            List<ConstraintViolation> violations =
                    validator.validate(composition, "us-hospital", usHospitalProfile);

            assertThat(violations).hasSize(1);
        }
    }

    @Nested
    class MixedCodes {

        @Test
        void shouldValidateMultipleCategoriesAndReportOnlyFailures() {
            var composition = compositionWith(
                    new DvCodedText(ICD10_SYSTEM, "J06.9", "Valid diagnosis", "/content[0]"),
                    new DvCodedText(CPT_SYSTEM, "BADCPT", "Invalid procedure", "/content[1]"),
                    new DvCodedText(SNOMED_SYSTEM, "386661006", "Valid SNOMED", "/content[2]"));

            when(fhirTerminologyValidation.validateCodes(any()))
                    .thenReturn(Map.of(
                            new CodePair(ICD10_SYSTEM, "J06.9"), true,
                            new CodePair(CPT_SYSTEM, "BADCPT"), false,
                            new CodePair(SNOMED_SYSTEM, "386661006"), true));

            List<ConstraintViolation> violations =
                    validator.validate(composition, "us-hospital", usHospitalProfile);

            assertThat(violations).hasSize(1);
            assertThat(violations.getFirst().failedCode()).isEqualTo("BADCPT");
            assertThat(violations.getFirst().category()).isEqualTo(BillingCategory.PROCEDURE);
        }

        @Test
        void shouldSkipCodesWithUnknownSystems() {
            var composition = compositionWith(
                    new DvCodedText("http://unknown.org/system", "XYZ", "Unknown", "/content[0]"),
                    new DvCodedText(ICD10_SYSTEM, "J06.9", "Valid", "/content[1]"));

            when(fhirTerminologyValidation.validateCodes(codePairsCaptor.capture()))
                    .thenReturn(Map.of(new CodePair(ICD10_SYSTEM, "J06.9"), true));

            List<ConstraintViolation> violations =
                    validator.validate(composition, "us-hospital", usHospitalProfile);

            assertThat(violations).isEmpty();
            assertThat(codePairsCaptor.getValue()).hasSize(1)
                    .containsExactly(new CodePair(ICD10_SYSTEM, "J06.9"));
        }
    }

    @Nested
    class EmptyComposition {

        @Test
        void shouldReturnEmptyViolationsForCompositionWithNoCodes() {
            var composition = new Composition(UUID.randomUUID(), List.of());

            List<ConstraintViolation> violations =
                    validator.validate(composition, "us-hospital", usHospitalProfile);

            assertThat(violations).isEmpty();
            verify(fhirTerminologyValidation, never()).validateCodes(any());
        }

        @Test
        void shouldReturnEmptyViolationsWhenNoCodesMatchProfile() {
            var composition = compositionWith(
                    new DvCodedText("http://other.org", "ABC", "Other", "/content[0]"));

            List<ConstraintViolation> violations =
                    validator.validate(composition, "us-hospital", usHospitalProfile);

            assertThat(violations).isEmpty();
            verify(fhirTerminologyValidation, never()).validateCodes(any());
        }
    }

    private static BillingProfile buildUsHospitalProfile() {
        var codeSystems = new CodeSystems();
        codeSystems.setDiagnosis(List.of(ICD10_SYSTEM));
        codeSystems.setProcedure(List.of(CPT_SYSTEM, HCPCS_SYSTEM));
        codeSystems.setClinicalJustification(List.of(SNOMED_SYSTEM));

        var strictness = new Strictness();
        strictness.setFailOnUnknownSystem(false);
        strictness.setRequireAllCategories(false);

        var profile = new BillingProfile();
        profile.setEnabled(true);
        profile.setCodeSystems(codeSystems);
        profile.setStrictness(strictness);
        return profile;
    }

    private static Composition compositionWith(DvCodedText... codedTexts) {
        return new Composition(UUID.randomUUID(), List.of(codedTexts));
    }
}
