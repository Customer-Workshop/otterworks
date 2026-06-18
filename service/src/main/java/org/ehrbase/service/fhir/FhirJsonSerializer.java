package org.ehrbase.service.fhir;

import ca.uhn.fhir.context.FhirContext;
import ca.uhn.fhir.parser.IParser;
import org.hl7.fhir.r4.model.Resource;
import org.springframework.stereotype.Service;

/**
 * FHIR JSON serialization service using HAPI FHIR R4 context.
 * Provides thread-safe serialization of FHIR resources to JSON format.
 */
@Service
public class FhirJsonSerializer {

    private final FhirContext fhirContext;

    public FhirJsonSerializer() {
        this.fhirContext = FhirContext.forR4();
    }

    /**
     * Serializes a FHIR resource to its JSON representation.
     *
     * @param resource the FHIR resource to serialize
     * @return JSON string representation
     */
    public String serialize(Resource resource) {
        IParser parser = fhirContext.newJsonParser();
        parser.setPrettyPrint(false);
        return parser.encodeResourceToString(resource);
    }

    /**
     * Serializes a FHIR resource to pretty-printed JSON.
     *
     * @param resource the FHIR resource to serialize
     * @return pretty-printed JSON string
     */
    public String serializePretty(Resource resource) {
        IParser parser = fhirContext.newJsonParser();
        parser.setPrettyPrint(true);
        return parser.encodeResourceToString(resource);
    }
}
