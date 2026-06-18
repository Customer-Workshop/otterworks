package com.otterworks.report.fhir;

import ca.uhn.fhir.context.FhirContext;
import ca.uhn.fhir.parser.IParser;
import org.hl7.fhir.r4.model.Bundle;
import org.springframework.stereotype.Service;

/**
 * Provides FHIR R4 JSON serialization via HAPI FhirContext.
 * FhirContext is expensive to create, so a single instance is shared.
 */
@Service
public class FhirJsonService {

    private final FhirContext fhirContext;

    public FhirJsonService() {
        this.fhirContext = FhirContext.forR4();
    }

    public String encodeBundle(Bundle bundle) {
        IParser parser = fhirContext.newJsonParser();
        parser.setPrettyPrint(true);
        return parser.encodeResourceToString(bundle);
    }

    public FhirContext getFhirContext() {
        return fhirContext;
    }
}
