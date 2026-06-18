package org.ehrbase.service.validation;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.Map;
import org.ehrbase.configuration.config.validation.ExternalValidationProperties;
import org.ehrbase.configuration.config.validation.ExternalValidationProperties.BillingProfile;
import org.ehrbase.configuration.config.validation.ExternalValidationProperties.StrictnessSettings;
import org.ehrbase.service.model.CodePhrase;
import org.ehrbase.service.model.Composition;
import org.ehrbase.service.model.Composition.CompositionEntry;
import org.ehrbase.service.model.DvCodedText;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class BillingCodeValidatorTest {

    private static final String ICD10_CM = "http://hl7.org/fhir/sid/icd-10-cm";
    private static final String CPT = "http://www.ama-assn.org/go/cpt";
    private static final String HCPCS = "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets";
    private static final String SNOMED = "http://snomed.info/sct";
    private static final String PROFILE_NAME = "us-hospital";

    private FhirTerminologyValidation fhirValidation;
    private ExternalValidationProperties properties;
    private BillingCodeValidator validator;

    @BeforeEach
    void setUp() {
        fhirValidation = mock(FhirTerminologyValidation.class);
        properties = new ExternalValidationProperties();
        properties.setEnabled(true);
        properties.setFhirUrl("https://tx.fhir.org/r4");

        BillingProfile profile = createUsHospitalProfile();
        properties.setBillingProfiles(Map.of(PROFILE_NAME, profile));

        validator = new BillingCodeValidator(properties, fhirValidation);
    }

    @Test
    void validIcd10CodeShouldProduceNoViolations() {
        when(fhirValidation.validate(ICD10_CM, "E11.9")).thenReturn(true);

        Composition composition = compositionWith(
                entry("/content[at0001]/data/diagnosis", ICD10_CM, "E11.9", "Type 2 diabetes mellitus"));

        List<ConstraintViolation> violations = validator.validate(composition);

        assertThat(violations).isEmpty();
        verify(fhirValidation).validate(ICD10_CM, "E11.9");
    }

    @Test
    void invalidIcd10CodeShouldProduceViolation() {
        when(fhirValidation.validate(ICD10_CM, "INVALID")).thenReturn(false);

        Composition composition = compositionWith(
                entry("/content[at0001]/data/diagnosis", ICD10_CM, "INVALID", "Invalid diagnosis"));

        List<ConstraintViolation> violations = validator.validate(composition);

        assertThat(violations).hasSize(1);
        ConstraintViolation v = violations.get(0);
        assertThat(v.aqlPath()).isEqualTo("/content[at0001]/data/diagnosis");
        assertThat(v.failedCode()).isEqualTo("INVALID");
        assertThat(v.codeSystem()).isEqualTo(ICD10_CM);
        assertThat(v.billingProfile()).isEqualTo(PROFILE_NAME);
        assertThat(v.category()).isEqualTo("diagnosis");
        assertThat(v.message()).contains("INVALID").contains(ICD10_CM);
    }

    @Test
    void validCptCodeShouldProduceNoViolations() {
        when(fhirValidation.validate(CPT, "99213")).thenReturn(true);

        Composition composition = compositionWith(
                entry("/content[at0002]/data/procedure", CPT, "99213", "Office visit"));

        List<ConstraintViolation> violations = validator.validate(composition);

        assertThat(violations).isEmpty();
        verify(fhirValidation).validate(CPT, "99213");
    }

    @Test
    void validHcpcsCodeShouldProduceNoViolations() {
        when(fhirValidation.validate(HCPCS, "G0101")).thenReturn(true);

        Composition composition = compositionWith(
                entry("/content[at0003]/data/procedure", HCPCS, "G0101", "Cervical screening"));

        List<ConstraintViolation> violations = validator.validate(composition);

        assertThat(violations).isEmpty();
    }

    @Test
    void snomedSubsetValidationShouldWork() {
        when(fhirValidation.validate(SNOMED, "73211009")).thenReturn(true);

        Composition composition = compositionWith(
                entry("/content[at0004]/data/justification", SNOMED, "73211009", "Diabetes mellitus"));

        List<ConstraintViolation> violations = validator.validate(composition);

        assertThat(violations).isEmpty();
        verify(fhirValidation).validate(SNOMED, "73211009");
    }

    @Test
    void invalidSnomedCodeShouldProduceViolation() {
        when(fhirValidation.validate(SNOMED, "0000000")).thenReturn(false);

        Composition composition = compositionWith(
                entry("/content[at0004]/data/justification", SNOMED, "0000000", "Unknown concept"));

        List<ConstraintViolation> violations = validator.validate(composition);

        assertThat(violations).hasSize(1);
        assertThat(violations.get(0).category()).isEqualTo("clinicalJustification");
    }

    @Test
    void disabledProfileShouldDoNothing() {
        BillingProfile disabledProfile = new BillingProfile();
        disabledProfile.setEnabled(false);
        disabledProfile.setDiagnosis(List.of(ICD10_CM));
        properties.setBillingProfiles(Map.of("disabled-profile", disabledProfile));
        validator = new BillingCodeValidator(properties, fhirValidation);

        Composition composition = compositionWith(
                entry("/content[at0001]/data/diagnosis", ICD10_CM, "E11.9", "Diabetes"));

        List<ConstraintViolation> violations = validator.validate(composition);

        assertThat(violations).isEmpty();
        verify(fhirValidation, never()).validate(anyString(), anyString());
    }

    @Test
    void unknownCodeSystemShouldBeIgnoredByDefault() {
        Composition composition = compositionWith(
                entry("/content[at0005]/data/other", "http://unknown.system", "XYZ", "Unknown"));

        List<ConstraintViolation> violations = validator.validate(composition);

        assertThat(violations).isEmpty();
        verify(fhirValidation, never()).validate(anyString(), anyString());
    }

    @Test
    void unknownCodeSystemShouldFailWhenConfiguredStrict() {
        BillingProfile strictProfile = createUsHospitalProfile();
        strictProfile.getStrictness().setFailUnknownBillingSystem(true);
        strictProfile.getStrictness().setValidateOnlyKnownBillingSystems(false);
        properties.setBillingProfiles(Map.of(PROFILE_NAME, strictProfile));
        validator = new BillingCodeValidator(properties, fhirValidation);

        Composition composition = compositionWith(
                entry("/content[at0005]/data/other", "http://unknown.system", "XYZ", "Unknown"));

        List<ConstraintViolation> violations = validator.validate(composition);

        assertThat(violations).hasSize(1);
        assertThat(violations.get(0).category()).isEqualTo("unknown");
        assertThat(violations.get(0).message()).contains("Unknown billing code system");
    }

    @Test
    void duplicateCodesShouldBeDeduplicatedBeforeValidation() {
        when(fhirValidation.validate(ICD10_CM, "E11.9")).thenReturn(true);

        Composition composition = compositionWith(
                entry("/content[at0001]/data/diag1", ICD10_CM, "E11.9", "Diabetes 1"),
                entry("/content[at0002]/data/diag2", ICD10_CM, "E11.9", "Diabetes 2"),
                entry("/content[at0003]/data/diag3", ICD10_CM, "E11.9", "Diabetes 3"));

        List<ConstraintViolation> violations = validator.validate(composition);

        assertThat(violations).isEmpty();
        verify(fhirValidation, times(1)).validate(ICD10_CM, "E11.9");
    }

    @Test
    void duplicateInvalidCodesShouldProduceOneViolation() {
        when(fhirValidation.validate(ICD10_CM, "BAD")).thenReturn(false);

        Composition composition = compositionWith(
                entry("/content[at0001]/data/diag1", ICD10_CM, "BAD", "Bad code 1"),
                entry("/content[at0002]/data/diag2", ICD10_CM, "BAD", "Bad code 2"));

        List<ConstraintViolation> violations = validator.validate(composition);

        assertThat(violations).hasSize(1);
        verify(fhirValidation, times(1)).validate(ICD10_CM, "BAD");
    }

    @Test
    void multipleCodeSystemsShouldAllBeValidated() {
        when(fhirValidation.validate(ICD10_CM, "E11.9")).thenReturn(true);
        when(fhirValidation.validate(CPT, "99213")).thenReturn(true);
        when(fhirValidation.validate(SNOMED, "73211009")).thenReturn(true);

        Composition composition = compositionWith(
                entry("/content[at0001]/data/diagnosis", ICD10_CM, "E11.9", "Diabetes"),
                entry("/content[at0002]/data/procedure", CPT, "99213", "Office visit"),
                entry("/content[at0003]/data/justification", SNOMED, "73211009", "Diabetes mellitus"));

        List<ConstraintViolation> violations = validator.validate(composition);

        assertThat(violations).isEmpty();
        verify(fhirValidation).validate(ICD10_CM, "E11.9");
        verify(fhirValidation).validate(CPT, "99213");
        verify(fhirValidation).validate(SNOMED, "73211009");
    }

    @Test
    void emptyCompositionShouldProduceNoViolations() {
        Composition composition = new Composition();
        List<ConstraintViolation> violations = validator.validate(composition);
        assertThat(violations).isEmpty();
    }

    @Test
    void noBillingProfilesShouldProduceNoViolations() {
        properties.setBillingProfiles(Map.of());
        validator = new BillingCodeValidator(properties, fhirValidation);

        Composition composition = compositionWith(
                entry("/content[at0001]/data/diagnosis", ICD10_CM, "E11.9", "Diabetes"));

        List<ConstraintViolation> violations = validator.validate(composition);
        assertThat(violations).isEmpty();
    }

    @Test
    void mixedValidAndInvalidCodesShouldOnlyReportInvalid() {
        when(fhirValidation.validate(ICD10_CM, "E11.9")).thenReturn(true);
        when(fhirValidation.validate(eq(ICD10_CM), eq("INVALID"))).thenReturn(false);
        when(fhirValidation.validate(CPT, "99213")).thenReturn(true);

        Composition composition = compositionWith(
                entry("/content[at0001]/data/diag1", ICD10_CM, "E11.9", "Diabetes"),
                entry("/content[at0002]/data/diag2", ICD10_CM, "INVALID", "Bad code"),
                entry("/content[at0003]/data/proc1", CPT, "99213", "Office visit"));

        List<ConstraintViolation> violations = validator.validate(composition);

        assertThat(violations).hasSize(1);
        assertThat(violations.get(0).failedCode()).isEqualTo("INVALID");
    }

    private static BillingProfile createUsHospitalProfile() {
        BillingProfile profile = new BillingProfile();
        profile.setEnabled(true);
        profile.setDiagnosis(List.of(ICD10_CM));
        profile.setProcedure(List.of(CPT, HCPCS));
        profile.setClinicalJustification(List.of(SNOMED));

        StrictnessSettings strictness = new StrictnessSettings();
        strictness.setRequiredCategories(List.of("diagnosis", "procedure"));
        strictness.setValidateOnlyKnownBillingSystems(true);
        strictness.setFailUnknownBillingSystem(false);
        profile.setStrictness(strictness);

        return profile;
    }

    private static Composition compositionWith(CompositionEntry... entries) {
        Composition composition = new Composition();
        for (CompositionEntry entry : entries) {
            composition.addEntry(entry);
        }
        return composition;
    }

    private static CompositionEntry entry(String path, String codeSystem, String code, String value) {
        return new CompositionEntry(path, new DvCodedText(value, new CodePhrase(codeSystem, code)));
    }
}
