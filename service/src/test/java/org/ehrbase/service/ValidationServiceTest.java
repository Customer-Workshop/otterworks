package org.ehrbase.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.Map;
import org.ehrbase.configuration.config.validation.ExternalValidationProperties;
import org.ehrbase.configuration.config.validation.ExternalValidationProperties.BillingProfile;
import org.ehrbase.service.model.CodePhrase;
import org.ehrbase.service.model.Composition;
import org.ehrbase.service.model.Composition.CompositionEntry;
import org.ehrbase.service.model.DvCodedText;
import org.ehrbase.service.validation.BillingCodeValidator;
import org.ehrbase.service.validation.ConstraintViolation;
import org.ehrbase.service.validation.FhirTerminologyValidation;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ValidationServiceTest {

    private ExternalValidationProperties properties;
    private FhirTerminologyValidation fhirValidation;
    private BillingCodeValidator billingCodeValidator;
    private ValidationServiceImp validationService;

    @BeforeEach
    void setUp() {
        properties = new ExternalValidationProperties();
        properties.setEnabled(true);
        properties.setFhirUrl("https://tx.fhir.org/r4");

        fhirValidation = mock(FhirTerminologyValidation.class);
        billingCodeValidator = mock(BillingCodeValidator.class);
        validationService = new ValidationServiceImp(properties, fhirValidation, billingCodeValidator);
    }

    @Test
    void checkShouldInvokeBillingValidationWhenEnabled() {
        BillingProfile profile = new BillingProfile();
        profile.setEnabled(true);
        profile.setDiagnosis(List.of("http://hl7.org/fhir/sid/icd-10-cm"));
        properties.setBillingProfiles(Map.of("us-hospital", profile));

        Composition composition = new Composition();
        when(billingCodeValidator.validate(composition)).thenReturn(List.of());

        validationService.check(composition);

        verify(billingCodeValidator).validate(composition);
    }

    @Test
    void checkShouldNotInvokeBillingValidationWhenDisabled() {
        properties.setBillingProfiles(Map.of());

        Composition composition = new Composition();

        validationService.check(composition);

        verify(billingCodeValidator, never()).validate(any());
    }

    @Test
    void checkShouldNotInvokeBillingValidationWhenAllProfilesDisabled() {
        BillingProfile profile = new BillingProfile();
        profile.setEnabled(false);
        properties.setBillingProfiles(Map.of("disabled", profile));

        Composition composition = new Composition();

        validationService.check(composition);

        verify(billingCodeValidator, never()).validate(any());
    }

    @Test
    void checkShouldReturnBillingViolations() {
        BillingProfile profile = new BillingProfile();
        profile.setEnabled(true);
        profile.setDiagnosis(List.of("http://hl7.org/fhir/sid/icd-10-cm"));
        properties.setBillingProfiles(Map.of("us-hospital", profile));

        Composition composition = new Composition();

        ConstraintViolation violation = new ConstraintViolation(
                "/content[at0001]/data/diagnosis",
                "INVALID",
                "http://hl7.org/fhir/sid/icd-10-cm",
                "us-hospital",
                "diagnosis",
                "Code 'INVALID' is not valid");
        when(billingCodeValidator.validate(composition)).thenReturn(List.of(violation));

        List<ConstraintViolation> violations = validationService.check(composition);

        assertThat(violations).hasSize(1);
        assertThat(violations.get(0).failedCode()).isEqualTo("INVALID");
    }

    @Test
    void checkShouldThrowForNullComposition() {
        assertThatThrownBy(() -> validationService.check(null))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Composition must not be null");
    }

    @Test
    void checkShouldReturnEmptyListForValidComposition() {
        BillingProfile profile = new BillingProfile();
        profile.setEnabled(true);
        profile.setDiagnosis(List.of("http://hl7.org/fhir/sid/icd-10-cm"));
        properties.setBillingProfiles(Map.of("us-hospital", profile));

        Composition composition = new Composition();
        when(billingCodeValidator.validate(composition)).thenReturn(List.of());

        List<ConstraintViolation> violations = validationService.check(composition);

        assertThat(violations).isEmpty();
    }

    @Test
    void checkShouldInvokeBillingValidationOnlyWhenAtLeastOneProfileEnabled() {
        BillingProfile enabledProfile = new BillingProfile();
        enabledProfile.setEnabled(true);
        enabledProfile.setDiagnosis(List.of("http://hl7.org/fhir/sid/icd-10-cm"));

        BillingProfile disabledProfile = new BillingProfile();
        disabledProfile.setEnabled(false);

        properties.setBillingProfiles(Map.of(
                "enabled-profile", enabledProfile,
                "disabled-profile", disabledProfile));

        Composition composition = new Composition();
        when(billingCodeValidator.validate(composition)).thenReturn(List.of());

        validationService.check(composition);

        verify(billingCodeValidator).validate(composition);
    }
}
