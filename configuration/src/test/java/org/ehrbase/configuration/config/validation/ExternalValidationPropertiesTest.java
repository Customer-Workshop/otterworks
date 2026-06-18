package org.ehrbase.configuration.config.validation;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(classes = ExternalValidationPropertiesTest.TestConfig.class)
@ActiveProfiles("test")
class ExternalValidationPropertiesTest {

    @EnableConfigurationProperties(ExternalValidationProperties.class)
    static class TestConfig {}

    @Autowired
    private ExternalValidationProperties properties;

    @Test
    void shouldBindEnabled() {
        assertThat(properties.isEnabled()).isTrue();
    }

    @Test
    void shouldBindFhirUrl() {
        assertThat(properties.getFhirUrl()).isEqualTo("http://test-fhir:8080/fhir");
    }

    @Test
    void shouldBindBillingProfileKeys() {
        assertThat(properties.getBillingProfiles()).containsKeys("us-hospital", "eu-clinic");
    }

    @Test
    void shouldBindUsHospitalProfile() {
        var profile = properties.getBillingProfiles().get("us-hospital");
        assertThat(profile).isNotNull();
        assertThat(profile.isEnabled()).isTrue();

        var codeSystems = profile.getCodeSystems();
        assertThat(codeSystems.getDiagnosis())
                .containsExactly("http://hl7.org/fhir/sid/icd-10-cm");
        assertThat(codeSystems.getProcedure())
                .containsExactly(
                        "http://www.ama-assn.org/go/cpt",
                        "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets");
        assertThat(codeSystems.getClinicalJustification())
                .containsExactly("http://snomed.info/sct");
    }

    @Test
    void shouldBindStrictnessSettings() {
        var strictness = properties.getBillingProfiles().get("us-hospital").getStrictness();
        assertThat(strictness.isFailOnUnknownSystem()).isFalse();
        assertThat(strictness.isRequireAllCategories()).isTrue();
    }

    @Test
    void shouldBindDisabledProfile() {
        var profile = properties.getBillingProfiles().get("eu-clinic");
        assertThat(profile).isNotNull();
        assertThat(profile.isEnabled()).isFalse();
    }

    @Test
    void shouldReturnAllSystemsFromCodeSystems() {
        var codeSystems = properties.getBillingProfiles().get("us-hospital").getCodeSystems();
        var all = codeSystems.allSystems();
        assertThat(all).hasSize(4);
        assertThat(all).contains(
                "http://hl7.org/fhir/sid/icd-10-cm",
                "http://www.ama-assn.org/go/cpt",
                "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets",
                "http://snomed.info/sct"
        );
    }

    @Test
    void shouldDefaultToEmptyBillingProfilesWhenNotConfigured() {
        var props = new ExternalValidationProperties();
        assertThat(props.getBillingProfiles()).isEmpty();
        assertThat(props.isEnabled()).isFalse();
    }

    @Test
    void shouldDefaultToEmptyCodeSystemLists() {
        var codeSystems = new ExternalValidationProperties.CodeSystems();
        assertThat(codeSystems.getDiagnosis()).isEmpty();
        assertThat(codeSystems.getProcedure()).isEmpty();
        assertThat(codeSystems.getClinicalJustification()).isEmpty();
    }
}
