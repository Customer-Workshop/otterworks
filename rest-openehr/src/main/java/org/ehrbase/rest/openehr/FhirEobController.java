package org.ehrbase.rest.openehr;

import jakarta.servlet.http.HttpServletRequest;
import org.ehrbase.api.service.FhirEobService;
import org.ehrbase.service.fhir.FhirJsonSerializer;
import org.hl7.fhir.r4.model.Bundle;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * FHIR R4-compliant REST endpoint for ExplanationOfBenefit resource retrieval.
 * Maps EHRbase openEHR composition data to FHIR EOB resources for claims/remittance
 * data exchange.
 */
@RestController
@RequestMapping("${ehrbase.rest.context-path:/rest}/fhir/r4")
public class FhirEobController {

    private static final Logger log = LoggerFactory.getLogger(FhirEobController.class);

    public static final String FHIR_JSON_MEDIA_TYPE = "application/fhir+json";

    private final FhirEobService fhirEobService;
    private final FhirJsonSerializer fhirJsonSerializer;

    public FhirEobController(FhirEobService fhirEobService, FhirJsonSerializer fhirJsonSerializer) {
        this.fhirEobService = fhirEobService;
        this.fhirJsonSerializer = fhirJsonSerializer;
    }

    /**
     * Searches for ExplanationOfBenefit resources by patient identifier.
     *
     * @param patient the patient identifier (required)
     * @param count   maximum entries per page (optional, default 10)
     * @param offset  zero-based pagination offset (optional, default 0)
     * @param request the HTTP request for base URL construction
     * @return FHIR Bundle of type searchset with application/fhir+json content type
     */
    @GetMapping(value = "/ExplanationOfBenefit", produces = FHIR_JSON_MEDIA_TYPE)
    public ResponseEntity<String> searchExplanationOfBenefit(
            @RequestParam("patient") String patient,
            @RequestParam(value = "_count", required = false) Integer count,
            @RequestParam(value = "_offset", required = false) Integer offset,
            HttpServletRequest request) {

        log.info("FHIR EOB search: patient={}, _count={}, _offset={}", patient, count, offset);

        if (patient == null || patient.isBlank()) {
            return ResponseEntity.badRequest()
                    .header("Content-Type", FHIR_JSON_MEDIA_TYPE)
                    .body("{\"resourceType\":\"OperationOutcome\",\"issue\":[{\"severity\":\"error\","
                            + "\"code\":\"required\",\"diagnostics\":\"patient parameter is required\"}]}");
        }

        String baseUrl = buildBaseUrl(request);
        Bundle bundle = fhirEobService.searchByPatient(patient, count, offset, baseUrl);
        String json = fhirJsonSerializer.serialize(bundle);

        return ResponseEntity.ok()
                .header("Content-Type", FHIR_JSON_MEDIA_TYPE)
                .body(json);
    }

    private String buildBaseUrl(HttpServletRequest request) {
        String scheme = request.getScheme();
        String host = request.getServerName();
        int port = request.getServerPort();
        String contextPath = request.getContextPath();

        StringBuilder url = new StringBuilder();
        url.append(scheme).append("://").append(host);
        if (("http".equals(scheme) && port != 80) || ("https".equals(scheme) && port != 443)) {
            url.append(":").append(port);
        }
        url.append(contextPath);
        url.append(request.getServletPath().replaceAll("/ExplanationOfBenefit$", ""));
        return url.toString();
    }
}
