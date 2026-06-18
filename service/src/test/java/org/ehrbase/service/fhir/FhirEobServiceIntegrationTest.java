package org.ehrbase.service.fhir;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.UUID;
import org.ehrbase.api.service.EhrService;
import org.ehrbase.model.Composition;
import org.ehrbase.model.DvCodedText;
import org.hl7.fhir.r4.model.Bundle;
import org.hl7.fhir.r4.model.Bundle.BundleLinkComponent;
import org.hl7.fhir.r4.model.ExplanationOfBenefit;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class FhirEobServiceIntegrationTest {

    private static final String ICD10_SYSTEM = "http://hl7.org/fhir/sid/icd-10-cm";
    private static final String CPT_SYSTEM = "http://www.ama-assn.org/go/cpt";
    private static final String SNOMED_SYSTEM = "http://snomed.info/sct";
    private static final String PATIENT_ID = "patient-integration-test";
    private static final String BASE_URL = "http://localhost:8080/rest/fhir/r4";

    @Mock
    private EhrService ehrService;

    @Mock
    private CompositionQueryService compositionQueryService;

    private FhirEobServiceImp fhirEobService;

    @BeforeEach
    void setUp() {
        EobMappingService mappingService = new EobMappingService();
        fhirEobService = new FhirEobServiceImp(ehrService, compositionQueryService, mappingService);
    }

    @Nested
    class WithQueryableEhr {

        @Test
        void shouldReturnBundleWithEobForValidBillingComposition() {
            UUID ehrId = UUID.randomUUID();
            UUID compositionUid = UUID.randomUUID();

            Composition composition = new Composition(compositionUid, List.of(
                    new DvCodedText(ICD10_SYSTEM, "J06.9", "Acute URI", "/content[0]"),
                    new DvCodedText(CPT_SYSTEM, "99213", "Office visit", "/content[1]"),
                    new DvCodedText(SNOMED_SYSTEM, "386661006", "Fever", "/content[2]")));

            when(ehrService.resolvePatientEhrIds(PATIENT_ID)).thenReturn(List.of(ehrId));
            when(ehrService.checkEhrExistsAndIsQueryable(ehrId)).thenReturn(true);
            when(compositionQueryService.findBillingCompositions(ehrId))
                    .thenReturn(List.of(composition));

            Bundle result = fhirEobService.searchByPatient(PATIENT_ID, null, null, BASE_URL);

            assertThat(result.getType()).isEqualTo(Bundle.BundleType.SEARCHSET);
            assertThat(result.getTotal()).isEqualTo(1);
            assertThat(result.getEntry()).hasSize(1);

            ExplanationOfBenefit eob = (ExplanationOfBenefit) result.getEntry().getFirst().getResource();
            assertThat(eob.getId()).isEqualTo(compositionUid.toString());
            assertThat(eob.getDiagnosis()).hasSize(1);
            assertThat(eob.getProcedure()).hasSize(1);
            assertThat(eob.getItem()).hasSize(2);
        }

        @Test
        void shouldReturnEmptyBundleWhenNoCompositionsExist() {
            UUID ehrId = UUID.randomUUID();

            when(ehrService.resolvePatientEhrIds(PATIENT_ID)).thenReturn(List.of(ehrId));
            when(ehrService.checkEhrExistsAndIsQueryable(ehrId)).thenReturn(true);
            when(compositionQueryService.findBillingCompositions(ehrId)).thenReturn(List.of());

            Bundle result = fhirEobService.searchByPatient(PATIENT_ID, null, null, BASE_URL);

            assertThat(result.getType()).isEqualTo(Bundle.BundleType.SEARCHSET);
            assertThat(result.getTotal()).isEqualTo(0);
            assertThat(result.getEntry()).isEmpty();
        }
    }

    @Nested
    class NonQueryableEhr {

        @Test
        void shouldReturnEmptyBundleForNonQueryableEhr() {
            UUID ehrId = UUID.randomUUID();

            when(ehrService.resolvePatientEhrIds(PATIENT_ID)).thenReturn(List.of(ehrId));
            when(ehrService.checkEhrExistsAndIsQueryable(ehrId)).thenReturn(false);

            Bundle result = fhirEobService.searchByPatient(PATIENT_ID, null, null, BASE_URL);

            assertThat(result.getType()).isEqualTo(Bundle.BundleType.SEARCHSET);
            assertThat(result.getTotal()).isEqualTo(0);
            assertThat(result.getEntry()).isEmpty();
        }

        @Test
        void shouldSkipNonQueryableEhrButIncludeQueryableOnes() {
            UUID queryableEhrId = UUID.randomUUID();
            UUID nonQueryableEhrId = UUID.randomUUID();
            UUID compositionUid = UUID.randomUUID();

            Composition composition = new Composition(compositionUid, List.of(
                    new DvCodedText(ICD10_SYSTEM, "E11.9", "Type 2 diabetes", "/content[0]")));

            when(ehrService.resolvePatientEhrIds(PATIENT_ID))
                    .thenReturn(List.of(nonQueryableEhrId, queryableEhrId));
            when(ehrService.checkEhrExistsAndIsQueryable(nonQueryableEhrId)).thenReturn(false);
            when(ehrService.checkEhrExistsAndIsQueryable(queryableEhrId)).thenReturn(true);
            when(compositionQueryService.findBillingCompositions(queryableEhrId))
                    .thenReturn(List.of(composition));

            Bundle result = fhirEobService.searchByPatient(PATIENT_ID, null, null, BASE_URL);

            assertThat(result.getTotal()).isEqualTo(1);
            assertThat(result.getEntry()).hasSize(1);
        }
    }

    @Nested
    class PaginationBehavior {

        @Test
        void shouldPaginateResultsWithNextLink() {
            UUID ehrId = UUID.randomUUID();

            List<Composition> compositions = List.of(
                    new Composition(UUID.randomUUID(), List.of(
                            new DvCodedText(ICD10_SYSTEM, "J06.9", "URI", "/c[0]"))),
                    new Composition(UUID.randomUUID(), List.of(
                            new DvCodedText(ICD10_SYSTEM, "E11.9", "Diabetes", "/c[0]"))),
                    new Composition(UUID.randomUUID(), List.of(
                            new DvCodedText(ICD10_SYSTEM, "I10", "Hypertension", "/c[0]"))));

            when(ehrService.resolvePatientEhrIds(PATIENT_ID)).thenReturn(List.of(ehrId));
            when(ehrService.checkEhrExistsAndIsQueryable(ehrId)).thenReturn(true);
            when(compositionQueryService.findBillingCompositions(ehrId)).thenReturn(compositions);

            Bundle result = fhirEobService.searchByPatient(PATIENT_ID, 2, 0, BASE_URL);

            assertThat(result.getTotal()).isEqualTo(3);
            assertThat(result.getEntry()).hasSize(2);

            BundleLinkComponent nextLink = result.getLink("next");
            assertThat(nextLink).isNotNull();
            assertThat(nextLink.getUrl()).contains("_offset=2");
            assertThat(nextLink.getUrl()).contains("_count=2");
        }

        @Test
        void shouldNotIncludeNextLinkOnLastPage() {
            UUID ehrId = UUID.randomUUID();

            List<Composition> compositions = List.of(
                    new Composition(UUID.randomUUID(), List.of(
                            new DvCodedText(ICD10_SYSTEM, "J06.9", "URI", "/c[0]"))),
                    new Composition(UUID.randomUUID(), List.of(
                            new DvCodedText(ICD10_SYSTEM, "E11.9", "Diabetes", "/c[0]"))));

            when(ehrService.resolvePatientEhrIds(PATIENT_ID)).thenReturn(List.of(ehrId));
            when(ehrService.checkEhrExistsAndIsQueryable(ehrId)).thenReturn(true);
            when(compositionQueryService.findBillingCompositions(ehrId)).thenReturn(compositions);

            Bundle result = fhirEobService.searchByPatient(PATIENT_ID, 10, 0, BASE_URL);

            assertThat(result.getTotal()).isEqualTo(2);
            assertThat(result.getEntry()).hasSize(2);
            assertThat(result.getLink("next")).isNull();
        }

        @Test
        void shouldReturnEmptyPageWhenOffsetExceedsTotal() {
            UUID ehrId = UUID.randomUUID();

            List<Composition> compositions = List.of(
                    new Composition(UUID.randomUUID(), List.of(
                            new DvCodedText(ICD10_SYSTEM, "J06.9", "URI", "/c[0]"))));

            when(ehrService.resolvePatientEhrIds(PATIENT_ID)).thenReturn(List.of(ehrId));
            when(ehrService.checkEhrExistsAndIsQueryable(ehrId)).thenReturn(true);
            when(compositionQueryService.findBillingCompositions(ehrId)).thenReturn(compositions);

            Bundle result = fhirEobService.searchByPatient(PATIENT_ID, 10, 100, BASE_URL);

            assertThat(result.getTotal()).isEqualTo(1);
            assertThat(result.getEntry()).isEmpty();
        }

        @Test
        void shouldIncludeSelfLink() {
            UUID ehrId = UUID.randomUUID();

            when(ehrService.resolvePatientEhrIds(PATIENT_ID)).thenReturn(List.of(ehrId));
            when(ehrService.checkEhrExistsAndIsQueryable(ehrId)).thenReturn(true);
            when(compositionQueryService.findBillingCompositions(ehrId)).thenReturn(List.of());

            Bundle result = fhirEobService.searchByPatient(PATIENT_ID, 10, 0, BASE_URL);

            BundleLinkComponent selfLink = result.getLink("self");
            assertThat(selfLink).isNotNull();
            assertThat(selfLink.getUrl()).contains("patient=" + PATIENT_ID);
        }
    }

    @Nested
    class PatientResolution {

        @Test
        void shouldReturnEmptyBundleWhenNoEhrsFoundForPatient() {
            when(ehrService.resolvePatientEhrIds("unknown-patient")).thenReturn(List.of());

            Bundle result = fhirEobService.searchByPatient("unknown-patient", null, null, BASE_URL);

            assertThat(result.getType()).isEqualTo(Bundle.BundleType.SEARCHSET);
            assertThat(result.getTotal()).isEqualTo(0);
            assertThat(result.getEntry()).isEmpty();
        }
    }
}
