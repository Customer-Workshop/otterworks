package org.ehrbase.service.validation;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.io.IOException;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.ehrbase.configuration.config.validation.ExternalValidationProperties;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class FhirTerminologyValidationTest {

    private ExternalValidationProperties properties;
    private HttpClient mockHttpClient;
    private FhirTerminologyValidation fhirValidation;

    @SuppressWarnings("unchecked")
    private final HttpResponse<String> mockResponse = mock(HttpResponse.class);

    @BeforeEach
    void setUp() {
        properties = new ExternalValidationProperties();
        properties.setEnabled(true);
        properties.setFhirUrl("https://tx.fhir.org/r4");
        properties.setFailOnError(false);

        mockHttpClient = mock(HttpClient.class);
        fhirValidation = new FhirTerminologyValidation(properties, mockHttpClient);
    }

    @Test
    @SuppressWarnings("unchecked")
    void shouldReturnTrueForValidCode() throws Exception {
        String validResponse = """
                {
                  "resourceType": "Parameters",
                  "parameter": [
                    {
                      "name": "result",
                      "valueBoolean": true
                    }
                  ]
                }
                """;

        when(mockResponse.statusCode()).thenReturn(200);
        when(mockResponse.body()).thenReturn(validResponse);
        when(mockHttpClient.send(any(HttpRequest.class), any(HttpResponse.BodyHandler.class)))
                .thenReturn(mockResponse);

        boolean result = fhirValidation.validate("http://hl7.org/fhir/sid/icd-10-cm", "E11.9");

        assertThat(result).isTrue();
    }

    @Test
    @SuppressWarnings("unchecked")
    void shouldReturnFalseForInvalidCode() throws Exception {
        String invalidResponse = """
                {
                  "resourceType": "Parameters",
                  "parameter": [
                    {
                      "name": "result",
                      "valueBoolean": false
                    },
                    {
                      "name": "message",
                      "valueString": "Code not found"
                    }
                  ]
                }
                """;

        when(mockResponse.statusCode()).thenReturn(200);
        when(mockResponse.body()).thenReturn(invalidResponse);
        when(mockHttpClient.send(any(HttpRequest.class), any(HttpResponse.BodyHandler.class)))
                .thenReturn(mockResponse);

        boolean result = fhirValidation.validate("http://hl7.org/fhir/sid/icd-10-cm", "INVALID");

        assertThat(result).isFalse();
    }

    @Test
    @SuppressWarnings("unchecked")
    void shouldReturnTrueOnErrorWhenFailOnErrorIsFalse() throws Exception {
        when(mockResponse.statusCode()).thenReturn(500);
        when(mockResponse.body()).thenReturn("Internal Server Error");
        when(mockHttpClient.send(any(HttpRequest.class), any(HttpResponse.BodyHandler.class)))
                .thenReturn(mockResponse);

        boolean result = fhirValidation.validate("http://hl7.org/fhir/sid/icd-10-cm", "E11.9");

        assertThat(result).isTrue();
    }

    @Test
    @SuppressWarnings("unchecked")
    void shouldThrowOnErrorWhenFailOnErrorIsTrue() throws Exception {
        properties.setFailOnError(true);
        fhirValidation = new FhirTerminologyValidation(properties, mockHttpClient);

        when(mockResponse.statusCode()).thenReturn(500);
        when(mockResponse.body()).thenReturn("Internal Server Error");
        when(mockHttpClient.send(any(HttpRequest.class), any(HttpResponse.BodyHandler.class)))
                .thenReturn(mockResponse);

        assertThatThrownBy(() -> fhirValidation.validate("http://hl7.org/fhir/sid/icd-10-cm", "E11.9"))
                .isInstanceOf(FhirTerminologyValidation.FhirValidationException.class);
    }

    @Test
    @SuppressWarnings("unchecked")
    void shouldReturnTrueOnNetworkErrorWhenFailOnErrorIsFalse() throws Exception {
        when(mockHttpClient.send(any(HttpRequest.class), any(HttpResponse.BodyHandler.class)))
                .thenThrow(new IOException("Connection refused"));

        boolean result = fhirValidation.validate("http://hl7.org/fhir/sid/icd-10-cm", "E11.9");

        assertThat(result).isTrue();
    }

    @Test
    @SuppressWarnings("unchecked")
    void shouldThrowOnNetworkErrorWhenFailOnErrorIsTrue() throws Exception {
        properties.setFailOnError(true);
        fhirValidation = new FhirTerminologyValidation(properties, mockHttpClient);

        when(mockHttpClient.send(any(HttpRequest.class), any(HttpResponse.BodyHandler.class)))
                .thenThrow(new IOException("Connection refused"));

        assertThatThrownBy(() -> fhirValidation.validate("http://hl7.org/fhir/sid/icd-10-cm", "E11.9"))
                .isInstanceOf(FhirTerminologyValidation.FhirValidationException.class);
    }

    @Test
    void shouldSkipValidationWhenDisabled() {
        properties.setEnabled(false);
        fhirValidation = new FhirTerminologyValidation(properties, mockHttpClient);

        boolean result = fhirValidation.validate("http://hl7.org/fhir/sid/icd-10-cm", "E11.9");

        assertThat(result).isTrue();
    }

    @Test
    @SuppressWarnings("unchecked")
    void shouldHandleNon200SuccessResponse() throws Exception {
        when(mockResponse.statusCode()).thenReturn(404);
        when(mockResponse.body()).thenReturn("Not Found");
        when(mockHttpClient.send(any(HttpRequest.class), any(HttpResponse.BodyHandler.class)))
                .thenReturn(mockResponse);

        boolean result = fhirValidation.validate("http://hl7.org/fhir/sid/icd-10-cm", "E11.9");

        assertThat(result).isTrue();
    }
}
