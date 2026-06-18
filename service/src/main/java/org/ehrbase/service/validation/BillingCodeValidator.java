package org.ehrbase.service.validation;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.ehrbase.configuration.config.validation.ExternalValidationProperties;
import org.ehrbase.configuration.config.validation.ExternalValidationProperties.BillingProfile;
import org.ehrbase.service.model.Composition;
import org.ehrbase.service.model.Composition.CompositionEntry;
import org.ehrbase.service.model.DvCodedText;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Walks a Composition, collects billing-relevant DvCodedText values, classifies them into
 * diagnosis/procedure/clinical justification buckets, and validates them against the configured
 * FHIR terminology server. Produces structured {@link ConstraintViolation}s.
 */
@Service
public class BillingCodeValidator {

    private static final Logger LOG = LoggerFactory.getLogger(BillingCodeValidator.class);

    private final ExternalValidationProperties properties;
    private final FhirTerminologyValidation fhirValidation;

    public BillingCodeValidator(
            ExternalValidationProperties properties, FhirTerminologyValidation fhirValidation) {
        this.properties = properties;
        this.fhirValidation = fhirValidation;
    }

    /**
     * Validates all billing-relevant codes in a composition against configured billing profiles.
     *
     * @param composition the composition to validate
     * @return list of constraint violations (empty if all codes are valid)
     */
    public List<ConstraintViolation> validate(Composition composition) {
        Map<String, BillingProfile> profiles = properties.getBillingProfiles();
        if (profiles == null || profiles.isEmpty()) {
            return List.of();
        }

        List<ConstraintViolation> allViolations = new ArrayList<>();

        for (Map.Entry<String, BillingProfile> profileEntry : profiles.entrySet()) {
            String profileName = profileEntry.getKey();
            BillingProfile profile = profileEntry.getValue();

            if (!profile.isEnabled()) {
                LOG.debug("Billing profile '{}' is disabled, skipping", profileName);
                continue;
            }

            List<ConstraintViolation> violations = validateProfile(composition, profileName, profile);
            allViolations.addAll(violations);
        }

        return allViolations;
    }

    private List<ConstraintViolation> validateProfile(
            Composition composition, String profileName, BillingProfile profile) {
        List<BillingCode> billingCodes = collectBillingCodes(composition, profileName, profile);
        Set<CodePair> uniquePairs = deduplicateCodePairs(billingCodes);
        Map<CodePair, Boolean> validationResults = batchValidate(uniquePairs);
        return buildViolations(billingCodes, validationResults, profileName, profile);
    }

    List<BillingCode> collectBillingCodes(
            Composition composition, String profileName, BillingProfile profile) {
        List<BillingCode> billingCodes = new ArrayList<>();

        for (CompositionEntry entry : composition.getEntries()) {
            DvCodedText codedText = entry.getCodedText();
            if (codedText == null) {
                continue;
            }

            String codeSystem = codedText.codeSystem();
            String category = profile.categoryFor(codeSystem);

            if (category != null) {
                billingCodes.add(new BillingCode(
                        entry.getPath(), codedText.code(), codeSystem, category, profileName));
            } else if (!profile.getStrictness().isValidateOnlyKnownBillingSystems()
                    || profile.getStrictness().isFailUnknownBillingSystem()) {
                handleUnknownCodeSystem(entry, codeSystem, profileName, profile, billingCodes);
            }
        }

        return billingCodes;
    }

    private void handleUnknownCodeSystem(
            CompositionEntry entry,
            String codeSystem,
            String profileName,
            BillingProfile profile,
            List<BillingCode> billingCodes) {
        if (profile.getStrictness().isFailUnknownBillingSystem()) {
            billingCodes.add(new BillingCode(
                    entry.getPath(),
                    entry.getCodedText().code(),
                    codeSystem,
                    "unknown",
                    profileName));
        }
    }

    Set<CodePair> deduplicateCodePairs(List<BillingCode> billingCodes) {
        Set<CodePair> uniquePairs = new LinkedHashSet<>();
        for (BillingCode bc : billingCodes) {
            if (!"unknown".equals(bc.category())) {
                uniquePairs.add(new CodePair(bc.codeSystem(), bc.code()));
            }
        }
        return uniquePairs;
    }

    private Map<CodePair, Boolean> batchValidate(Set<CodePair> uniquePairs) {
        Map<CodePair, Boolean> results = new LinkedHashMap<>();
        for (CodePair pair : uniquePairs) {
            boolean valid = fhirValidation.validate(pair.codeSystem(), pair.code());
            results.put(pair, valid);
        }
        return results;
    }

    private List<ConstraintViolation> buildViolations(
            List<BillingCode> billingCodes,
            Map<CodePair, Boolean> validationResults,
            String profileName,
            BillingProfile profile) {
        List<ConstraintViolation> violations = new ArrayList<>();
        Set<CodePair> reportedPairs = new LinkedHashSet<>();

        for (BillingCode bc : billingCodes) {
            if ("unknown".equals(bc.category())) {
                violations.add(new ConstraintViolation(
                        bc.path(),
                        bc.code(),
                        bc.codeSystem(),
                        profileName,
                        "unknown",
                        "Unknown billing code system '" + bc.codeSystem()
                                + "' not configured in profile '" + profileName + "'"));
                continue;
            }

            CodePair pair = new CodePair(bc.codeSystem(), bc.code());
            Boolean valid = validationResults.get(pair);

            if (valid != null && !valid && reportedPairs.add(pair)) {
                violations.add(new ConstraintViolation(
                        bc.path(),
                        bc.code(),
                        bc.codeSystem(),
                        profileName,
                        bc.category(),
                        "Code '" + bc.code() + "' is not valid in code system '"
                                + bc.codeSystem() + "' for billing profile '" + profileName
                                + "' (category: " + bc.category() + ")"));
            }
        }

        return violations;
    }

    record BillingCode(String path, String code, String codeSystem, String category, String profileName) {}

    record CodePair(String codeSystem, String code) {}
}
