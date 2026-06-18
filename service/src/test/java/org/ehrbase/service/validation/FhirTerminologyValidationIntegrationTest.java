package org.ehrbase.service.validation;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.ExpectedCount.once;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServerError;

import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import org.ehrbase.service.validation.FhirTerminologyValidation.CodePair;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

class FhirTerminologyValidationIntegrationTest {

    private static final String FHIR_BASE = "http://mock-fhir:8080/fhir";

    private RestTemplate restTemplate;
    private MockRestServiceServer mockServer;
    private FhirTerminologyValidation fhirValidation;

    @BeforeEach
    void setUp() {
        restTemplate = new RestTemplate();
        mockServer = MockRestServiceServer.createServer(restTemplate);
        fhirValidation = new FhirTerminologyValidation(restTemplate, FHIR_BASE);
    }

    @Nested
    class SingleCodeValidation {

        @Test
        void shouldReturnTrueForValidCode() {
            mockServer.expect(requestTo(
                            FHIR_BASE + "/CodeSystem/$validate-code?system=http://hl7.org/fhir/sid/icd-10-cm&code=J06.9"))
                    .andRespond(withSuccess(
                            """
                            {"result": true, "message": "Code is valid"}
                            """,
                            MediaType.APPLICATION_JSON));

            boolean result = fhirValidation.validateCode(
                    "http://hl7.org/fhir/sid/icd-10-cm", "J06.9");

            assertThat(result).isTrue();
            mockServer.verify();
        }

        @Test
        void shouldReturnFalseForInvalidCode() {
            mockServer.expect(requestTo(
                            FHIR_BASE + "/CodeSystem/$validate-code?system=http://hl7.org/fhir/sid/icd-10-cm&code=INVALID"))
                    .andRespond(withSuccess(
                            """
                            {"result": false, "message": "Code not found"}
                            """,
                            MediaType.APPLICATION_JSON));

            boolean result = fhirValidation.validateCode(
                    "http://hl7.org/fhir/sid/icd-10-cm", "INVALID");

            assertThat(result).isFalse();
            mockServer.verify();
        }

        @Test
        void shouldReturnFalseOnServerError() {
            mockServer.expect(requestTo(
                            FHIR_BASE + "/CodeSystem/$validate-code?system=http://www.ama-assn.org/go/cpt&code=99213"))
                    .andRespond(withServerError());

            boolean result = fhirValidation.validateCode(
                    "http://www.ama-assn.org/go/cpt", "99213");

            assertThat(result).isFalse();
            mockServer.verify();
        }
    }

    @Nested
    class BatchValidation {

        @Test
        void shouldValidateMultipleCodePairs() {
            var icdPair = new CodePair("http://hl7.org/fhir/sid/icd-10-cm", "J06.9");
            var cptPair = new CodePair("http://www.ama-assn.org/go/cpt", "BADCPT");

            mockServer.expect(once(), requestTo(
                            FHIR_BASE + "/CodeSystem/$validate-code?system=http://hl7.org/fhir/sid/icd-10-cm&code=J06.9"))
                    .andRespond(withSuccess(
                            """
                            {"result": true, "message": "Valid"}
                            """,
                            MediaType.APPLICATION_JSON));

            mockServer.expect(once(), requestTo(
                            FHIR_BASE + "/CodeSystem/$validate-code?system=http://www.ama-assn.org/go/cpt&code=BADCPT"))
                    .andRespond(withSuccess(
                            """
                            {"result": false, "message": "Not found"}
                            """,
                            MediaType.APPLICATION_JSON));

            var orderedPairs = new LinkedHashSet<CodePair>();
            orderedPairs.add(icdPair);
            orderedPairs.add(cptPair);
            Map<CodePair, Boolean> results =
                    fhirValidation.validateCodes(orderedPairs);

            assertThat(results).containsEntry(icdPair, true);
            assertThat(results).containsEntry(cptPair, false);
            mockServer.verify();
        }

        @Test
        void shouldReturnEmptyMapForEmptyInput() {
            Map<CodePair, Boolean> results =
                    fhirValidation.validateCodes(Set.of());

            assertThat(results).isEmpty();
        }
    }

    @Nested
    class CptHcpcsValidation {

        @Test
        void shouldValidateCptCode() {
            mockServer.expect(requestTo(
                            FHIR_BASE + "/CodeSystem/$validate-code?system=http://www.ama-assn.org/go/cpt&code=99213"))
                    .andRespond(withSuccess(
                            """
                            {"result": true, "message": "Valid CPT code"}
                            """,
                            MediaType.APPLICATION_JSON));

            boolean result = fhirValidation.validateCode(
                    "http://www.ama-assn.org/go/cpt", "99213");

            assertThat(result).isTrue();
            mockServer.verify();
        }

        @Test
        void shouldValidateHcpcsCode() {
            String hcpcsSystem = "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets";
            mockServer.expect(requestTo(
                            FHIR_BASE + "/CodeSystem/$validate-code?system=" + hcpcsSystem + "&code=G0101"))
                    .andRespond(withSuccess(
                            """
                            {"result": true, "message": "Valid HCPCS code"}
                            """,
                            MediaType.APPLICATION_JSON));

            boolean result = fhirValidation.validateCode(hcpcsSystem, "G0101");

            assertThat(result).isTrue();
            mockServer.verify();
        }
    }

    @Nested
    class SnomedValidation {

        @Test
        void shouldValidateSnomedCode() {
            mockServer.expect(requestTo(
                            FHIR_BASE + "/CodeSystem/$validate-code?system=http://snomed.info/sct&code=386661006"))
                    .andRespond(withSuccess(
                            """
                            {"result": true, "message": "Valid SNOMED code"}
                            """,
                            MediaType.APPLICATION_JSON));

            boolean result = fhirValidation.validateCode(
                    "http://snomed.info/sct", "386661006");

            assertThat(result).isTrue();
            mockServer.verify();
        }

        @Test
        void shouldReturnFalseForInvalidSnomedCode() {
            mockServer.expect(requestTo(
                            FHIR_BASE + "/CodeSystem/$validate-code?system=http://snomed.info/sct&code=0000000"))
                    .andRespond(withSuccess(
                            """
                            {"result": false, "message": "Unknown SNOMED concept"}
                            """,
                            MediaType.APPLICATION_JSON));

            boolean result = fhirValidation.validateCode(
                    "http://snomed.info/sct", "0000000");

            assertThat(result).isFalse();
            mockServer.verify();
        }
    }
}
