package org.ehrbase.configuration.config.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * Configuration properties for external FHIR terminology validation,
 * including billing-specific code system profiles.
 *
 * <pre>
 * ehrbase:
 *   validation:
 *     external:
 *       enabled: true
 *       fhir-url: http://localhost:8080/fhir
 *       billing-profiles:
 *         us-hospital:
 *           enabled: true
 *           code-systems:
 *             diagnosis:
 *               - http://hl7.org/fhir/sid/icd-10-cm
 *             procedure:
 *               - http://www.ama-assn.org/go/cpt
 *               - https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets
 *             clinical-justification:
 *               - http://snomed.info/sct
 *           strictness:
 *             fail-on-unknown-system: false
 *             require-all-categories: false
 * </pre>
 */
@Validated
@ConfigurationProperties(prefix = "ehrbase.validation.external")
public class ExternalValidationProperties {

    private boolean enabled;

    private String fhirUrl;

    @Valid
    private Map<String, BillingProfile> billingProfiles = new LinkedHashMap<>();

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getFhirUrl() {
        return fhirUrl;
    }

    public void setFhirUrl(String fhirUrl) {
        this.fhirUrl = fhirUrl;
    }

    public Map<String, BillingProfile> getBillingProfiles() {
        return billingProfiles;
    }

    public void setBillingProfiles(Map<String, BillingProfile> billingProfiles) {
        this.billingProfiles = billingProfiles;
    }

    public static class BillingProfile {

        private boolean enabled;

        @Valid
        private CodeSystems codeSystems = new CodeSystems();

        @Valid
        private Strictness strictness = new Strictness();

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public CodeSystems getCodeSystems() {
            return codeSystems;
        }

        public void setCodeSystems(CodeSystems codeSystems) {
            this.codeSystems = codeSystems;
        }

        public Strictness getStrictness() {
            return strictness;
        }

        public void setStrictness(Strictness strictness) {
            this.strictness = strictness;
        }
    }

    public static class CodeSystems {

        private List<@NotBlank String> diagnosis = List.of();

        private List<@NotBlank String> procedure = List.of();

        private List<@NotBlank String> clinicalJustification = List.of();

        public List<String> getDiagnosis() {
            return diagnosis;
        }

        public void setDiagnosis(List<String> diagnosis) {
            this.diagnosis = diagnosis;
        }

        public List<String> getProcedure() {
            return procedure;
        }

        public void setProcedure(List<String> procedure) {
            this.procedure = procedure;
        }

        public List<String> getClinicalJustification() {
            return clinicalJustification;
        }

        public void setClinicalJustification(List<String> clinicalJustification) {
            this.clinicalJustification = clinicalJustification;
        }

        public List<String> allSystems() {
            var all = new java.util.ArrayList<String>();
            all.addAll(diagnosis);
            all.addAll(procedure);
            all.addAll(clinicalJustification);
            return List.copyOf(all);
        }
    }

    public static class Strictness {

        private boolean failOnUnknownSystem;

        private boolean requireAllCategories;

        public boolean isFailOnUnknownSystem() {
            return failOnUnknownSystem;
        }

        public void setFailOnUnknownSystem(boolean failOnUnknownSystem) {
            this.failOnUnknownSystem = failOnUnknownSystem;
        }

        public boolean isRequireAllCategories() {
            return requireAllCategories;
        }

        public void setRequireAllCategories(boolean requireAllCategories) {
            this.requireAllCategories = requireAllCategories;
        }
    }
}
