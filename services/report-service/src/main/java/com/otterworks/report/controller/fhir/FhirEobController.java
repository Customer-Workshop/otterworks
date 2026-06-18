package com.otterworks.report.controller.fhir;

import com.otterworks.report.fhir.FhirEobService;
import com.otterworks.report.fhir.FhirJsonService;
import com.otterworks.report.fhir.FhirMediaType;
import org.hl7.fhir.r4.model.Bundle;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import javax.servlet.http.HttpServletRequest;

/**
 * FHIR R4 ExplanationOfBenefit resource endpoint.
 *
 * GET /rest/fhir/r4/ExplanationOfBenefit?patient={id}
 */
@RestController
@RequestMapping("${fhir-api.context-path:/rest/fhir/r4}")
public class FhirEobController {

    private static final Logger logger = LoggerFactory.getLogger(FhirEobController.class);

    private static final int DEFAULT_COUNT = 10;
    private static final int MAX_COUNT = 100;

    private final FhirEobService fhirEobService;
    private final FhirJsonService fhirJsonService;

    public FhirEobController(FhirEobService fhirEobService,
                             FhirJsonService fhirJsonService) {
        this.fhirEobService = fhirEobService;
        this.fhirJsonService = fhirJsonService;
    }

    @GetMapping(value = "/ExplanationOfBenefit",
            produces = FhirMediaType.APPLICATION_FHIR_JSON_VALUE)
    public ResponseEntity<String> searchExplanationOfBenefit(
            @RequestParam("patient") String patientId,
            @RequestParam(value = "_count", required = false) Integer count,
            @RequestParam(value = "_offset", required = false) Integer offset,
            HttpServletRequest request) {

        int effectiveCount = (count != null && count > 0)
                ? Math.min(count, MAX_COUNT)
                : DEFAULT_COUNT;
        int effectiveOffset = (offset != null && offset >= 0) ? offset : 0;

        logger.info("FHIR EOB search: patient={}, _count={}, _offset={}",
                patientId, effectiveCount, effectiveOffset);

        String baseUrl = buildBaseUrl(request);
        Bundle bundle = fhirEobService.searchByPatient(
                patientId, effectiveCount, effectiveOffset, baseUrl);

        String json = fhirJsonService.encodeBundle(bundle);

        return ResponseEntity.ok()
                .contentType(FhirMediaType.APPLICATION_FHIR_JSON)
                .body(json);
    }

    private String buildBaseUrl(HttpServletRequest request) {
        String scheme = request.getScheme();
        String host = request.getServerName();
        int port = request.getServerPort();
        String contextPath = request.getContextPath();
        String servletPath = request.getServletPath();

        StringBuilder url = new StringBuilder();
        url.append(scheme).append("://").append(host);
        if (("http".equals(scheme) && port != 80)
                || ("https".equals(scheme) && port != 443)) {
            url.append(":").append(port);
        }
        url.append(contextPath);

        String fullPath = servletPath;
        int eobIdx = fullPath.indexOf("/ExplanationOfBenefit");
        if (eobIdx > 0) {
            url.append(fullPath, 0, eobIdx);
        } else {
            url.append(fullPath);
        }
        return url.toString();
    }
}
