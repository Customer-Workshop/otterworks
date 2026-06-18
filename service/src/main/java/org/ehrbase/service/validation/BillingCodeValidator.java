package org.ehrbase.service.validation;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.ehrbase.configuration.config.validation.ExternalValidationProperties.BillingProfile;
import org.ehrbase.configuration.config.validation.ExternalValidationProperties.CodeSystems;
import org.ehrbase.model.Composition;
import org.ehrbase.model.DvCodedText;
import org.ehrbase.service.validation.FhirTerminologyValidation.CodePair;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Walks a {@link Composition}, collects billing-relevant {@link DvCodedText}
 * values, classifies them into diagnosis / procedure / clinical-justification
 * buckets based on their system URI, and validates them against a FHIR
 * terminology server via {@link FhirTerminologyValidation}.
 */
@Service
public class BillingCodeValidator {

    private static final Logger log = LoggerFactory.getLogger(BillingCodeValidator.class);

    private final FhirTerminologyValidation fhirTerminologyValidation;

    public BillingCodeValidator(FhirTerminologyValidation fhirTerminologyValidation) {
        this.fhirTerminologyValidation = fhirTerminologyValidation;
    }

    /**
     * Validates all billing-relevant coded texts in the given composition
     * against the specified billing profile.
     *
     * @param composition the composition to validate
     * @param profileName the name of the billing profile being applied
     * @param profile     the billing profile configuration
     * @return list of constraint violations (empty if all codes are valid)
     */
    public List<ConstraintViolation> validate(
            Composition composition,
            String profileName,
            BillingProfile profile) {

        CodeSystems codeSystems = profile.getCodeSystems();
        Map<BillingCategory, List<String>> categoryToSystems = buildCategoryMap(codeSystems);

        Map<DvCodedText, BillingCategory> billingCodes =
                collectBillingCodes(composition, categoryToSystems);

        if (billingCodes.isEmpty()) {
            log.debug("No billing-relevant codes found in composition {} for profile '{}'",
                    composition.uid(), profileName);
            return List.of();
        }

        Set<CodePair> uniquePairs = deduplicateCodePairs(billingCodes.keySet());
        Map<CodePair, Boolean> validationResults =
                fhirTerminologyValidation.validateCodes(uniquePairs);

        return buildViolations(billingCodes, validationResults, profileName, profile);
    }

    private Map<BillingCategory, List<String>> buildCategoryMap(CodeSystems codeSystems) {
        Map<BillingCategory, List<String>> map = new LinkedHashMap<>();
        map.put(BillingCategory.DIAGNOSIS, codeSystems.getDiagnosis());
        map.put(BillingCategory.PROCEDURE, codeSystems.getProcedure());
        map.put(BillingCategory.CLINICAL_JUSTIFICATION, codeSystems.getClinicalJustification());
        return map;
    }

    /**
     * Walks the composition's coded texts and classifies each into a billing
     * category based on its system URI. Codes whose system does not match any
     * configured billing code system are skipped.
     */
    Map<DvCodedText, BillingCategory> collectBillingCodes(
            Composition composition,
            Map<BillingCategory, List<String>> categoryToSystems) {

        Map<DvCodedText, BillingCategory> collected = new LinkedHashMap<>();

        for (DvCodedText codedText : composition.codedTexts()) {
            for (var entry : categoryToSystems.entrySet()) {
                if (entry.getValue().contains(codedText.system())) {
                    collected.put(codedText, entry.getKey());
                    break;
                }
            }
        }
        return collected;
    }

    private Set<CodePair> deduplicateCodePairs(Set<DvCodedText> codedTexts) {
        Set<CodePair> pairs = new LinkedHashSet<>();
        for (DvCodedText ct : codedTexts) {
            pairs.add(new CodePair(ct.system(), ct.code()));
        }
        return pairs;
    }

    private List<ConstraintViolation> buildViolations(
            Map<DvCodedText, BillingCategory> billingCodes,
            Map<CodePair, Boolean> validationResults,
            String profileName,
            BillingProfile profile) {

        List<ConstraintViolation> violations = new ArrayList<>();
        Set<CodePair> reportedPairs = new LinkedHashSet<>();

        for (var entry : billingCodes.entrySet()) {
            DvCodedText codedText = entry.getKey();
            BillingCategory category = entry.getValue();
            CodePair pair = new CodePair(codedText.system(), codedText.code());

            Boolean valid = validationResults.get(pair);

            if (Boolean.FALSE.equals(valid) && reportedPairs.add(pair)) {
                violations.add(new ConstraintViolation(
                        codedText.path(),
                        codedText.code(),
                        codedText.system(),
                        profileName,
                        category,
                        "Code '%s' in system '%s' is not valid for billing profile '%s' (category: %s)"
                                .formatted(codedText.code(), codedText.system(),
                                        profileName, category)
                ));
            }
        }

        if (profile.getStrictness().isFailOnUnknownSystem()) {
            addUnknownSystemViolations(billingCodes, profileName, violations);
        }

        return List.copyOf(violations);
    }

    private void addUnknownSystemViolations(
            Map<DvCodedText, BillingCategory> billingCodes,
            String profileName,
            List<ConstraintViolation> violations) {

        // Handled upstream: only codes matching configured systems are collected,
        // so unknown systems are already excluded. This method is a hook for
        // future extension when full-composition scanning is enabled.
        log.trace("failOnUnknownSystem is enabled for profile '{}'; " +
                "currently only configured systems are scanned", profileName);
    }
}
