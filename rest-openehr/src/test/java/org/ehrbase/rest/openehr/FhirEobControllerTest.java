package org.ehrbase.rest.openehr;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.ehrbase.api.service.FhirEobService;
import org.ehrbase.service.fhir.FhirJsonSerializer;
import org.hl7.fhir.r4.model.Bundle;
import org.hl7.fhir.r4.model.Bundle.BundleType;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(FhirEobController.class)
class FhirEobControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private FhirEobService fhirEobService;

    @MockitoBean
    private FhirJsonSerializer fhirJsonSerializer;

    @Nested
    class RequestValidation {

        @Test
        void shouldReturn400WhenPatientParameterMissing() throws Exception {
            mockMvc.perform(get("/rest/fhir/r4/ExplanationOfBenefit"))
                    .andExpect(status().isBadRequest());
        }

        @Test
        void shouldReturn400WhenPatientParameterBlank() throws Exception {
            mockMvc.perform(get("/rest/fhir/r4/ExplanationOfBenefit")
                            .param("patient", "  "))
                    .andExpect(status().isBadRequest())
                    .andExpect(header().string("Content-Type", FhirEobController.FHIR_JSON_MEDIA_TYPE));
        }

        @Test
        void shouldAcceptValidPatientParameter() throws Exception {
            Bundle emptyBundle = new Bundle();
            emptyBundle.setType(BundleType.SEARCHSET);
            emptyBundle.setTotal(0);

            when(fhirEobService.searchByPatient(eq("patient-123"), isNull(), isNull(), anyString()))
                    .thenReturn(emptyBundle);
            when(fhirJsonSerializer.serialize(any(Bundle.class)))
                    .thenReturn("{\"resourceType\":\"Bundle\",\"type\":\"searchset\",\"total\":0}");

            mockMvc.perform(get("/rest/fhir/r4/ExplanationOfBenefit")
                            .param("patient", "patient-123"))
                    .andExpect(status().isOk());
        }
    }

    @Nested
    class MediaType {

        @Test
        void shouldReturnFhirJsonContentType() throws Exception {
            Bundle emptyBundle = new Bundle();
            emptyBundle.setType(BundleType.SEARCHSET);
            emptyBundle.setTotal(0);

            when(fhirEobService.searchByPatient(anyString(), any(), any(), anyString()))
                    .thenReturn(emptyBundle);
            when(fhirJsonSerializer.serialize(any(Bundle.class)))
                    .thenReturn("{\"resourceType\":\"Bundle\",\"type\":\"searchset\",\"total\":0}");

            mockMvc.perform(get("/rest/fhir/r4/ExplanationOfBenefit")
                            .param("patient", "patient-123"))
                    .andExpect(header().string("Content-Type", FhirEobController.FHIR_JSON_MEDIA_TYPE));
        }
    }

    @Nested
    class EmptyBundle {

        @Test
        void shouldReturnEmptySearchsetBundle() throws Exception {
            Bundle emptyBundle = new Bundle();
            emptyBundle.setType(BundleType.SEARCHSET);
            emptyBundle.setTotal(0);

            when(fhirEobService.searchByPatient(eq("unknown-patient"), isNull(), isNull(), anyString()))
                    .thenReturn(emptyBundle);
            when(fhirJsonSerializer.serialize(any(Bundle.class)))
                    .thenReturn("{\"resourceType\":\"Bundle\",\"type\":\"searchset\",\"total\":0,\"entry\":[]}");

            mockMvc.perform(get("/rest/fhir/r4/ExplanationOfBenefit")
                            .param("patient", "unknown-patient"))
                    .andExpect(status().isOk())
                    .andExpect(content().json(
                            "{\"resourceType\":\"Bundle\",\"type\":\"searchset\",\"total\":0}"));
        }
    }

    @Nested
    class Pagination {

        @Test
        void shouldPassCountAndOffsetToService() throws Exception {
            Bundle bundle = new Bundle();
            bundle.setType(BundleType.SEARCHSET);
            bundle.setTotal(0);

            when(fhirEobService.searchByPatient(eq("patient-123"), eq(5), eq(10), anyString()))
                    .thenReturn(bundle);
            when(fhirJsonSerializer.serialize(any(Bundle.class)))
                    .thenReturn("{\"resourceType\":\"Bundle\",\"type\":\"searchset\",\"total\":0}");

            mockMvc.perform(get("/rest/fhir/r4/ExplanationOfBenefit")
                            .param("patient", "patient-123")
                            .param("_count", "5")
                            .param("_offset", "10"))
                    .andExpect(status().isOk());

            verify(fhirEobService).searchByPatient(eq("patient-123"), eq(5), eq(10), anyString());
        }

        @Test
        void shouldDefaultCountAndOffsetWhenNotProvided() throws Exception {
            Bundle bundle = new Bundle();
            bundle.setType(BundleType.SEARCHSET);
            bundle.setTotal(0);

            when(fhirEobService.searchByPatient(eq("patient-123"), isNull(), isNull(), anyString()))
                    .thenReturn(bundle);
            when(fhirJsonSerializer.serialize(any(Bundle.class)))
                    .thenReturn("{\"resourceType\":\"Bundle\",\"type\":\"searchset\",\"total\":0}");

            mockMvc.perform(get("/rest/fhir/r4/ExplanationOfBenefit")
                            .param("patient", "patient-123"))
                    .andExpect(status().isOk());

            verify(fhirEobService).searchByPatient(eq("patient-123"), isNull(), isNull(), anyString());
        }
    }
}
