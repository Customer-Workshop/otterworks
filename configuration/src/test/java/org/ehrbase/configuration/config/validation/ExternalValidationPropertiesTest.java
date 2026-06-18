package org.ehrbase.configuration.config.validation;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.ehrbase.configuration.config.validation.ExternalValidationProperties.BillingProfile;
import org.ehrbase.configuration.config.validation.ExternalValidationProperties.StrictnessSettings;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

@SpringBootTest(classes = ExternalValidationPropertiesTest.TestConfig.class)
@TestPropertySource(properties = {
    "ehrbase.validation.external-terminology.enabled=true",
    "ehrbase.validation.external-terminology.fhir-url=https://tx.fhir.org/r4",
    "ehrbase.validation.external-terminology.fail-on-error=false",
    "ehrbase.validation.external-terminology.billing-profiles.us-hospital.enabled=true",
    "ehrbase.validation.external-terminology.billing-profiles.us-hospital.diagnosis[0]=http://hl7.org/fhir/sid/icd-10-cm",
    "ehrbase.validation.external-terminology.billing-profiles.us-hospital.diagnosis[1]=http://hl7.org/fhir/sid/icd-10",
    "ehrbase.validation.external-terminology.billing-profiles.us-hospital.procedure[0]=http://www.ama-assn.org/go/cpt",
    "ehrbase.validation.external-terminology.billing-profiles.us-hospital.procedure[1]=https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets",
    "ehrbase.validation.external-terminology.billing-profiles.us-hospital.clinical-justification[0]=http://snomed.info/sct",
    "ehrbase.validation.external-terminology.billing-profiles.us-hospital.strictness.required-categories[0]=diagnosis",
    "ehrbase.validation.external-terminology.billing-profiles.us-hospital.strictness.required-categories[1]=procedure",
    "ehrbase.validation.external-terminology.billing-profiles.us-hospital.strictness.validate-only-known-billing-systems=true",
    "ehrbase.validation.external-terminology.billing-profiles.us-hospital.strictness.fail-unknown-billing-system=false",
    "ehrbase.validation.external-terminology.billing-profiles.eu-clinic.enabled=false",
    "ehrbase.validation.external-terminology.billing-profiles.eu-clinic.diagnosis[0]=http://hl7.org/fhir/sid/icd-10"
})
class ExternalValidationPropertiesTest {

    @EnableConfigurationProperties(ExternalValidationProperties.class)
    static class TestConfig {}

    @Autowired
    private ExternalValidationProperties properties;

    @Test
    void shouldBindTopLevelProperties() {
        assertThat(properties.isEnabled()).isTrue();
        assertThat(properties.getFhirUrl()).isEqualTo("https://tx.fhir.org/r4");
        assertThat(properties.isFailOnError()).isFalse();
    }

    @Test
    void shouldBindBillingProfiles() {
        assertThat(properties.getBillingProfiles()).containsKeys("us-hospital", "eu-clinic");
    }

    @Test
    void shouldBindEnabledUsHospitalProfile() {
        BillingProfile usHospital = properties.getBillingProfiles().get("us-hospital");

        assertThat(usHospital.isEnabled()).isTrue();
        assertThat(usHospital.getDiagnosis()).containsExactly(
                "http://hl7.org/fhir/sid/icd-10-cm",
                "http://hl7.org/fhir/sid/icd-10");
        assertThat(usHospital.getProcedure()).containsExactly(
                "http://www.ama-assn.org/go/cpt",
                "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets");
        assertThat(usHospital.getClinicalJustification()).containsExactly("http://snomed.info/sct");
    }

    @Test
    void shouldBindStrictnessSettings() {
        StrictnessSettings strictness =
                properties.getBillingProfiles().get("us-hospital").getStrictness();

        assertThat(strictness.getRequiredCategories()).containsExactly("diagnosis", "procedure");
        assertThat(strictness.isValidateOnlyKnownBillingSystems()).isTrue();
        assertThat(strictness.isFailUnknownBillingSystem()).isFalse();
    }

    @Test
    void shouldBindDisabledProfile() {
        BillingProfile euClinic = properties.getBillingProfiles().get("eu-clinic");

        assertThat(euClinic.isEnabled()).isFalse();
        assertThat(euClinic.getDiagnosis()).containsExactly("http://hl7.org/fhir/sid/icd-10");
    }

    @Test
    void allCodeSystemsShouldReturnAllConfiguredSystems() {
        BillingProfile usHospital = properties.getBillingProfiles().get("us-hospital");
        List<String> all = usHospital.allCodeSystems();

        assertThat(all).containsExactly(
                "http://hl7.org/fhir/sid/icd-10-cm",
                "http://hl7.org/fhir/sid/icd-10",
                "http://www.ama-assn.org/go/cpt",
                "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets",
                "http://snomed.info/sct");
    }

    @Test
    void categoryForShouldClassifyCodeSystems() {
        BillingProfile usHospital = properties.getBillingProfiles().get("us-hospital");

        assertThat(usHospital.categoryFor("http://hl7.org/fhir/sid/icd-10-cm")).isEqualTo("diagnosis");
        assertThat(usHospital.categoryFor("http://www.ama-assn.org/go/cpt")).isEqualTo("procedure");
        assertThat(usHospital.categoryFor("http://snomed.info/sct")).isEqualTo("clinicalJustification");
        assertThat(usHospital.categoryFor("http://unknown.system")).isNull();
    }

    @Test
    void defaultStrictnessSettingsShouldHaveSensibleDefaults() {
        StrictnessSettings defaults = new StrictnessSettings();

        assertThat(defaults.getRequiredCategories()).isEmpty();
        assertThat(defaults.isValidateOnlyKnownBillingSystems()).isTrue();
        assertThat(defaults.isFailUnknownBillingSystem()).isFalse();
    }
}
