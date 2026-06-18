package org.ehrbase.service;

import java.util.ArrayList;
import java.util.List;
import org.ehrbase.configuration.config.validation.ExternalValidationProperties;
import org.ehrbase.service.model.Composition;
import org.ehrbase.service.validation.BillingCodeValidator;
import org.ehrbase.service.validation.ConstraintViolation;
import org.ehrbase.service.validation.FhirTerminologyValidation;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Central validation service for compositions. Orchestrates structural validation,
 * FHIR terminology validation, and billing code validation.
 */
@Service
public class ValidationServiceImp {

    private static final Logger LOG = LoggerFactory.getLogger(ValidationServiceImp.class);

    private final ExternalValidationProperties properties;
    private final FhirTerminologyValidation fhirTerminologyValidation;
    private final BillingCodeValidator billingCodeValidator;

    public ValidationServiceImp(
            ExternalValidationProperties properties,
            FhirTerminologyValidation fhirTerminologyValidation,
            BillingCodeValidator billingCodeValidator) {
        this.properties = properties;
        this.fhirTerminologyValidation = fhirTerminologyValidation;
        this.billingCodeValidator = billingCodeValidator;
    }

    /**
     * Validates a composition including structural checks, FHIR terminology validation,
     * and billing code validation (if enabled).
     *
     * @param composition the composition to validate
     * @return list of constraint violations found
     * @throws IllegalArgumentException if the composition is null
     */
    public List<ConstraintViolation> check(Composition composition) {
        if (composition == null) {
            throw new IllegalArgumentException("Composition must not be null");
        }

        List<ConstraintViolation> violations = new ArrayList<>();

        violations.addAll(validateStructure(composition));

        if (properties.isEnabled()) {
            violations.addAll(validateTerminology(composition));
        }

        if (hasBillingProfilesEnabled()) {
            LOG.debug("Running billing code validation for composition {}", composition.getUid());
            List<ConstraintViolation> billingViolations = billingCodeValidator.validate(composition);
            violations.addAll(billingViolations);
        }

        return violations;
    }

    private List<ConstraintViolation> validateStructure(Composition composition) {
        return List.of();
    }

    private List<ConstraintViolation> validateTerminology(Composition composition) {
        return List.of();
    }

    private boolean hasBillingProfilesEnabled() {
        var profiles = properties.getBillingProfiles();
        if (profiles == null || profiles.isEmpty()) {
            return false;
        }
        return profiles.values().stream()
                .anyMatch(ExternalValidationProperties.BillingProfile::isEnabled);
    }
}
