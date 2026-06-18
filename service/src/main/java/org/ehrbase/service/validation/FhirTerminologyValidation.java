package org.ehrbase.service.validation;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.util.UriComponentsBuilder;

/**
 * Low-level FHIR terminology client. Validates individual (system, code)
 * pairs against a remote FHIR terminology server's {@code $validate-code}
 * operation.
 */
@Service
public class FhirTerminologyValidation {

    private static final Logger log = LoggerFactory.getLogger(FhirTerminologyValidation.class);

    private final RestTemplate restTemplate;
    private final String fhirBaseUrl;

    public FhirTerminologyValidation(RestTemplate restTemplate, String fhirBaseUrl) {
        this.restTemplate = restTemplate;
        this.fhirBaseUrl = fhirBaseUrl;
    }

    /**
     * Validates a single code against the FHIR terminology server.
     *
     * @param system the terminology system URI (e.g. {@code http://hl7.org/fhir/sid/icd-10-cm})
     * @param code   the code string to validate
     * @return {@code true} if the code is valid within the system, {@code false} otherwise
     */
    public boolean validateCode(String system, String code) {
        String url = UriComponentsBuilder
                .fromUriString(fhirBaseUrl)
                .pathSegment("CodeSystem", "$validate-code")
                .queryParam("system", system)
                .queryParam("code", code)
                .build()
                .toUriString();

        try {
            ResponseEntity<FhirValidationResponse> response =
                    restTemplate.getForEntity(url, FhirValidationResponse.class);

            if (response.getBody() != null) {
                return response.getBody().result();
            }
            log.warn("Empty response body from FHIR server for system={}, code={}", system, code);
            return false;
        } catch (RestClientException e) {
            log.error("FHIR terminology validation failed for system={}, code={}: {}",
                    system, code, e.getMessage());
            return false;
        }
    }

    /**
     * Validates a batch of (system, code) pairs, de-duplicating before making
     * remote calls. Returns a map from each {@link CodePair} to its validity.
     *
     * @param codePairs the set of unique (system, code) pairs to validate
     * @return map of each code pair to its validation result
     */
    public Map<CodePair, Boolean> validateCodes(Set<CodePair> codePairs) {
        Map<CodePair, Boolean> results = new LinkedHashMap<>();
        for (CodePair pair : codePairs) {
            results.put(pair, validateCode(pair.system(), pair.code()));
        }
        return results;
    }

    /**
     * Immutable (system, code) pair used for de-duplication and batch lookups.
     */
    public record CodePair(String system, String code) {

        public CodePair {
            if (system == null || system.isBlank()) {
                throw new IllegalArgumentException("system must not be blank");
            }
            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException("code must not be blank");
            }
        }
    }

    /**
     * Minimal representation of a FHIR {@code $validate-code} response.
     */
    record FhirValidationResponse(boolean result, String message) {}
}
