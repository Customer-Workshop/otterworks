package org.ehrbase.service.validation;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import org.ehrbase.configuration.config.validation.ExternalValidationProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Low-level FHIR terminology validation client. Validates individual (system, code) pairs
 * against a FHIR terminology server's $validate-code operation.
 */
@Service
public class FhirTerminologyValidation {

    private static final Logger LOG = LoggerFactory.getLogger(FhirTerminologyValidation.class);

    private static final Duration REQUEST_TIMEOUT = Duration.ofSeconds(10);

    private final ExternalValidationProperties properties;

    private final HttpClient httpClient;

    public FhirTerminologyValidation(ExternalValidationProperties properties) {
        this.properties = properties;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();
    }

    FhirTerminologyValidation(ExternalValidationProperties properties, HttpClient httpClient) {
        this.properties = properties;
        this.httpClient = httpClient;
    }

    /**
     * Validates a single code against its code system on the configured FHIR terminology server.
     *
     * @param codeSystem the code system URI (e.g. "http://hl7.org/fhir/sid/icd-10-cm")
     * @param code       the code to validate (e.g. "E11.9")
     * @return true if the code is valid in the given code system
     */
    public boolean validate(String codeSystem, String code) {
        if (!properties.isEnabled()) {
            LOG.debug("External terminology validation disabled, skipping validation for {}|{}", codeSystem, code);
            return true;
        }

        String fhirUrl = properties.getFhirUrl();
        String requestUrl = fhirUrl + "/CodeSystem/$validate-code?url="
                + encodeUri(codeSystem) + "&code=" + encodeUri(code);

        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(requestUrl))
                    .timeout(REQUEST_TIMEOUT)
                    .header("Accept", "application/fhir+json")
                    .GET()
                    .build();

            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() == 200) {
                return parseValidationResult(response.body());
            }

            LOG.warn(
                    "FHIR terminology server returned status {} for {}|{}: {}",
                    response.statusCode(),
                    codeSystem,
                    code,
                    response.body());
            return handleError(codeSystem, code);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            LOG.error("Interrupted during FHIR validation for {}|{}", codeSystem, code);
            return handleError(codeSystem, code);
        } catch (Exception e) {
            LOG.error("Error validating {}|{} against FHIR server: {}", codeSystem, code, e.getMessage());
            return handleError(codeSystem, code);
        }
    }

    private boolean parseValidationResult(String responseBody) {
        return responseBody.contains("\"result\"")
                && responseBody.contains("\"valueBoolean\"")
                && responseBody.contains("true");
    }

    private boolean handleError(String codeSystem, String code) {
        if (properties.isFailOnError()) {
            throw new FhirValidationException(
                    "FHIR terminology validation failed for " + codeSystem + "|" + code);
        }
        return true;
    }

    private static String encodeUri(String value) {
        return value.replace(" ", "%20")
                .replace("|", "%7C")
                .replace("#", "%23");
    }

    public static class FhirValidationException extends RuntimeException {
        public FhirValidationException(String message) {
            super(message);
        }

        public FhirValidationException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
