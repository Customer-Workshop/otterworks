package org.ehrbase.service.fhir;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.UUID;
import org.ehrbase.model.Composition;
import org.ehrbase.model.DvCodedText;
import org.hl7.fhir.r4.model.ExplanationOfBenefit;
import org.hl7.fhir.r4.model.ExplanationOfBenefit.ExplanationOfBenefitStatus;
import org.hl7.fhir.r4.model.ExplanationOfBenefit.Use;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

class EobMappingServiceTest {

    private static final String ICD10_SYSTEM = "http://hl7.org/fhir/sid/icd-10-cm";
    private static final String CPT_SYSTEM = "http://www.ama-assn.org/go/cpt";
    private static final String HCPCS_SYSTEM = "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets";
    private static final String SNOMED_SYSTEM = "http://snomed.info/sct";
    private static final String PATIENT_ID = "patient-123";

    private EobMappingService mappingService;

    @BeforeEach
    void setUp() {
        mappingService = new EobMappingService();
    }

    @Nested
    class BasicMapping {

        @Test
        void shouldMapCompositionToEobWithCorrectMetadata() {
            UUID uid = UUID.randomUUID();
            UUID ehrId = UUID.randomUUID();
            Composition composition = new Composition(uid, List.of(
                    new DvCodedText(ICD10_SYSTEM, "J06.9", "Acute URI", "/content[0]")));

            ExplanationOfBenefit eob = mappingService.mapToEob(composition, ehrId, PATIENT_ID);

            assertThat(eob.getId()).isEqualTo(uid.toString());
            assertThat(eob.getStatus()).isEqualTo(ExplanationOfBenefitStatus.ACTIVE);
            assertThat(eob.getUse()).isEqualTo(Use.CLAIM);
            assertThat(eob.getPatient().getReference()).isEqualTo("Patient/" + PATIENT_ID);
            assertThat(eob.getCreated()).isNotNull();
            assertThat(eob.getProvider().getReference()).isEqualTo("Organization/" + ehrId);
            assertThat(eob.getFacility().getReference()).isEqualTo("Location/" + ehrId);
        }

        @Test
        void shouldMapEmptyCompositionToEobWithNoEntries() {
            UUID uid = UUID.randomUUID();
            UUID ehrId = UUID.randomUUID();
            Composition composition = new Composition(uid, List.of());

            ExplanationOfBenefit eob = mappingService.mapToEob(composition, ehrId, PATIENT_ID);

            assertThat(eob.getDiagnosis()).isEmpty();
            assertThat(eob.getProcedure()).isEmpty();
            assertThat(eob.getItem()).isEmpty();
        }
    }

    @Nested
    class DiagnosisMapping {

        @Test
        void shouldMapIcd10CodeToDiagnosis() {
            Composition composition = compositionWith(
                    new DvCodedText(ICD10_SYSTEM, "J06.9", "Acute upper respiratory infection", "/content[0]"));

            ExplanationOfBenefit eob = mappingService.mapToEob(
                    composition, UUID.randomUUID(), PATIENT_ID);

            assertThat(eob.getDiagnosis()).hasSize(1);
            var diag = eob.getDiagnosis().getFirst();
            assertThat(diag.getSequence()).isEqualTo(1);
            assertThat(diag.getDiagnosisCodeableConcept().getCodingFirstRep().getSystem())
                    .isEqualTo(ICD10_SYSTEM);
            assertThat(diag.getDiagnosisCodeableConcept().getCodingFirstRep().getCode())
                    .isEqualTo("J06.9");
            assertThat(diag.getDiagnosisCodeableConcept().getCodingFirstRep().getDisplay())
                    .isEqualTo("Acute upper respiratory infection");
        }

        @Test
        void shouldAssignSequentialDiagnosisNumbers() {
            Composition composition = compositionWith(
                    new DvCodedText(ICD10_SYSTEM, "J06.9", "Acute URI", "/content[0]"),
                    new DvCodedText(ICD10_SYSTEM, "E11.9", "Type 2 diabetes", "/content[1]"));

            ExplanationOfBenefit eob = mappingService.mapToEob(
                    composition, UUID.randomUUID(), PATIENT_ID);

            assertThat(eob.getDiagnosis()).hasSize(2);
            assertThat(eob.getDiagnosis().get(0).getSequence()).isEqualTo(1);
            assertThat(eob.getDiagnosis().get(1).getSequence()).isEqualTo(2);
        }
    }

    @Nested
    class ProcedureMapping {

        @Test
        void shouldMapCptCodeToProcedureAndItem() {
            Composition composition = compositionWith(
                    new DvCodedText(CPT_SYSTEM, "99213", "Office visit", "/content[0]"));

            ExplanationOfBenefit eob = mappingService.mapToEob(
                    composition, UUID.randomUUID(), PATIENT_ID);

            assertThat(eob.getProcedure()).hasSize(1);
            var proc = eob.getProcedure().getFirst();
            assertThat(proc.getSequence()).isEqualTo(1);
            assertThat(proc.getProcedureCodeableConcept().getCodingFirstRep().getSystem())
                    .isEqualTo(CPT_SYSTEM);
            assertThat(proc.getProcedureCodeableConcept().getCodingFirstRep().getCode())
                    .isEqualTo("99213");

            assertThat(eob.getItem()).hasSize(1);
            assertThat(eob.getItem().getFirst().getProductOrService()
                    .getCodingFirstRep().getCode()).isEqualTo("99213");
        }

        @Test
        void shouldMapHcpcsCodeToProcedureAndItem() {
            Composition composition = compositionWith(
                    new DvCodedText(HCPCS_SYSTEM, "G0101", "Cervical screening", "/content[0]"));

            ExplanationOfBenefit eob = mappingService.mapToEob(
                    composition, UUID.randomUUID(), PATIENT_ID);

            assertThat(eob.getProcedure()).hasSize(1);
            assertThat(eob.getProcedure().getFirst()
                    .getProcedureCodeableConcept().getCodingFirstRep().getSystem())
                    .isEqualTo(HCPCS_SYSTEM);
            assertThat(eob.getItem()).hasSize(1);
        }
    }

    @Nested
    class ClinicalJustificationMapping {

        @Test
        void shouldMapSnomedCodeToItemOnly() {
            Composition composition = compositionWith(
                    new DvCodedText(SNOMED_SYSTEM, "386661006", "Fever", "/content[0]"));

            ExplanationOfBenefit eob = mappingService.mapToEob(
                    composition, UUID.randomUUID(), PATIENT_ID);

            assertThat(eob.getDiagnosis()).isEmpty();
            assertThat(eob.getProcedure()).isEmpty();
            assertThat(eob.getItem()).hasSize(1);
            assertThat(eob.getItem().getFirst().getProductOrService()
                    .getCodingFirstRep().getSystem()).isEqualTo(SNOMED_SYSTEM);
            assertThat(eob.getItem().getFirst().getProductOrService()
                    .getCodingFirstRep().getCode()).isEqualTo("386661006");
        }
    }

    @Nested
    class MixedCodes {

        @Test
        void shouldCorrectlyClassifyMixedBillingCodes() {
            Composition composition = compositionWith(
                    new DvCodedText(ICD10_SYSTEM, "J06.9", "URI", "/content[0]"),
                    new DvCodedText(CPT_SYSTEM, "99213", "Office visit", "/content[1]"),
                    new DvCodedText(SNOMED_SYSTEM, "386661006", "Fever", "/content[2]"));

            ExplanationOfBenefit eob = mappingService.mapToEob(
                    composition, UUID.randomUUID(), PATIENT_ID);

            assertThat(eob.getDiagnosis()).hasSize(1);
            assertThat(eob.getProcedure()).hasSize(1);
            assertThat(eob.getItem()).hasSize(2); // CPT item + SNOMED item
        }

        @Test
        void shouldIgnoreUnknownCodeSystems() {
            Composition composition = compositionWith(
                    new DvCodedText("http://unknown.system/codes", "XYZ", "Unknown", "/content[0]"),
                    new DvCodedText(ICD10_SYSTEM, "J06.9", "URI", "/content[1]"));

            ExplanationOfBenefit eob = mappingService.mapToEob(
                    composition, UUID.randomUUID(), PATIENT_ID);

            assertThat(eob.getDiagnosis()).hasSize(1);
            assertThat(eob.getProcedure()).isEmpty();
            assertThat(eob.getItem()).isEmpty();
        }
    }

    @Nested
    class CodeClassification {

        @Test
        void shouldClassifyIcd10AsDiagnosis() {
            assertThat(mappingService.classifyCode(ICD10_SYSTEM))
                    .isEqualTo(org.ehrbase.service.validation.BillingCategory.DIAGNOSIS);
        }

        @Test
        void shouldClassifyCptAsProcedure() {
            assertThat(mappingService.classifyCode(CPT_SYSTEM))
                    .isEqualTo(org.ehrbase.service.validation.BillingCategory.PROCEDURE);
        }

        @Test
        void shouldClassifyHcpcsAsProcedure() {
            assertThat(mappingService.classifyCode(HCPCS_SYSTEM))
                    .isEqualTo(org.ehrbase.service.validation.BillingCategory.PROCEDURE);
        }

        @Test
        void shouldClassifySnomedAsClinicalJustification() {
            assertThat(mappingService.classifyCode(SNOMED_SYSTEM))
                    .isEqualTo(org.ehrbase.service.validation.BillingCategory.CLINICAL_JUSTIFICATION);
        }

        @Test
        void shouldReturnNullForUnknownSystem() {
            assertThat(mappingService.classifyCode("http://unknown.system")).isNull();
        }

        @Test
        void shouldReturnNullForNullSystem() {
            assertThat(mappingService.classifyCode(null)).isNull();
        }
    }

    private Composition compositionWith(DvCodedText... codedTexts) {
        return new Composition(UUID.randomUUID(), List.of(codedTexts));
    }
}
