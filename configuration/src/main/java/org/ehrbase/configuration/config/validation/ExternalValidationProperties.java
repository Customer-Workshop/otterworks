package org.ehrbase.configuration.config.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "ehrbase.validation.external-terminology")
public class ExternalValidationProperties {

    private boolean enabled;

    @NotBlank
    private String fhirUrl;

    private boolean failOnError;

    @Valid
    private Map<String, BillingProfile> billingProfiles = Map.of();

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

    public boolean isFailOnError() {
        return failOnError;
    }

    public void setFailOnError(boolean failOnError) {
        this.failOnError = failOnError;
    }

    public Map<String, BillingProfile> getBillingProfiles() {
        return billingProfiles;
    }

    public void setBillingProfiles(Map<String, BillingProfile> billingProfiles) {
        this.billingProfiles = billingProfiles;
    }

    public static class BillingProfile {

        private boolean enabled;

        private List<String> diagnosis = List.of();

        private List<String> procedure = List.of();

        private List<String> clinicalJustification = List.of();

        @Valid
        private StrictnessSettings strictness = new StrictnessSettings();

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

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

        public StrictnessSettings getStrictness() {
            return strictness;
        }

        public void setStrictness(StrictnessSettings strictness) {
            this.strictness = strictness;
        }

        public List<String> allCodeSystems() {
            var systems = new java.util.ArrayList<String>();
            systems.addAll(diagnosis);
            systems.addAll(procedure);
            systems.addAll(clinicalJustification);
            return List.copyOf(systems);
        }

        public String categoryFor(String codeSystemUri) {
            if (diagnosis.contains(codeSystemUri)) {
                return "diagnosis";
            }
            if (procedure.contains(codeSystemUri)) {
                return "procedure";
            }
            if (clinicalJustification.contains(codeSystemUri)) {
                return "clinicalJustification";
            }
            return null;
        }
    }

    public static class StrictnessSettings {

        private List<String> requiredCategories = List.of();

        private boolean validateOnlyKnownBillingSystems = true;

        private boolean failUnknownBillingSystem;

        public List<String> getRequiredCategories() {
            return requiredCategories;
        }

        public void setRequiredCategories(List<String> requiredCategories) {
            this.requiredCategories = requiredCategories;
        }

        public boolean isValidateOnlyKnownBillingSystems() {
            return validateOnlyKnownBillingSystems;
        }

        public void setValidateOnlyKnownBillingSystems(boolean validateOnlyKnownBillingSystems) {
            this.validateOnlyKnownBillingSystems = validateOnlyKnownBillingSystems;
        }

        public boolean isFailUnknownBillingSystem() {
            return failUnknownBillingSystem;
        }

        public void setFailUnknownBillingSystem(boolean failUnknownBillingSystem) {
            this.failUnknownBillingSystem = failUnknownBillingSystem;
        }
    }
}
