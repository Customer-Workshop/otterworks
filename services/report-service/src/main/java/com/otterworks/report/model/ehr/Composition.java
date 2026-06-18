package com.otterworks.report.model.ehr;

import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.GeneratedValue;
import javax.persistence.GenerationType;
import javax.persistence.Id;
import javax.persistence.Table;
import java.util.Date;
import java.util.UUID;

/**
 * Represents a clinical composition containing billing-relevant data
 * (diagnosis codes, procedure codes, encounter context).
 */
@Entity
@Table(name = "compositions")
public class Composition {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "composition_id", nullable = false, unique = true)
    private UUID compositionId;

    @Column(name = "ehr_id", nullable = false)
    private UUID ehrId;

    @Column(name = "encounter_type")
    private String encounterType;

    @Column(name = "diagnosis_code")
    private String diagnosisCode;

    @Column(name = "diagnosis_display")
    private String diagnosisDisplay;

    @Column(name = "diagnosis_system")
    private String diagnosisSystem;

    @Column(name = "procedure_code")
    private String procedureCode;

    @Column(name = "procedure_display")
    private String procedureDisplay;

    @Column(name = "procedure_system")
    private String procedureSystem;

    @Column(name = "provider_name")
    private String providerName;

    @Column(name = "facility_name")
    private String facilityName;

    @Column(name = "start_time")
    private Date startTime;

    @Column(name = "commit_time", nullable = false)
    private Date commitTime;

    public Composition() {
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public UUID getCompositionId() {
        return compositionId;
    }

    public void setCompositionId(UUID compositionId) {
        this.compositionId = compositionId;
    }

    public UUID getEhrId() {
        return ehrId;
    }

    public void setEhrId(UUID ehrId) {
        this.ehrId = ehrId;
    }

    public String getEncounterType() {
        return encounterType;
    }

    public void setEncounterType(String encounterType) {
        this.encounterType = encounterType;
    }

    public String getDiagnosisCode() {
        return diagnosisCode;
    }

    public void setDiagnosisCode(String diagnosisCode) {
        this.diagnosisCode = diagnosisCode;
    }

    public String getDiagnosisDisplay() {
        return diagnosisDisplay;
    }

    public void setDiagnosisDisplay(String diagnosisDisplay) {
        this.diagnosisDisplay = diagnosisDisplay;
    }

    public String getDiagnosisSystem() {
        return diagnosisSystem;
    }

    public void setDiagnosisSystem(String diagnosisSystem) {
        this.diagnosisSystem = diagnosisSystem;
    }

    public String getProcedureCode() {
        return procedureCode;
    }

    public void setProcedureCode(String procedureCode) {
        this.procedureCode = procedureCode;
    }

    public String getProcedureDisplay() {
        return procedureDisplay;
    }

    public void setProcedureDisplay(String procedureDisplay) {
        this.procedureDisplay = procedureDisplay;
    }

    public String getProcedureSystem() {
        return procedureSystem;
    }

    public void setProcedureSystem(String procedureSystem) {
        this.procedureSystem = procedureSystem;
    }

    public String getProviderName() {
        return providerName;
    }

    public void setProviderName(String providerName) {
        this.providerName = providerName;
    }

    public String getFacilityName() {
        return facilityName;
    }

    public void setFacilityName(String facilityName) {
        this.facilityName = facilityName;
    }

    public Date getStartTime() {
        return startTime;
    }

    public void setStartTime(Date startTime) {
        this.startTime = startTime;
    }

    public Date getCommitTime() {
        return commitTime;
    }

    public void setCommitTime(Date commitTime) {
        this.commitTime = commitTime;
    }
}
