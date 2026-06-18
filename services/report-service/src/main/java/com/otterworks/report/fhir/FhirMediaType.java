package com.otterworks.report.fhir;

import org.springframework.http.MediaType;

public final class FhirMediaType {

    public static final String APPLICATION_FHIR_JSON_VALUE = "application/fhir+json";

    public static final MediaType APPLICATION_FHIR_JSON =
            MediaType.parseMediaType(APPLICATION_FHIR_JSON_VALUE);

    private FhirMediaType() {
    }
}
