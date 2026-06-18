package com.otterworks.report.model.ehr;

import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;
import java.util.Date;
import java.util.UUID;

/**
 * Represents an Electronic Health Record (EHR) with access control flags.
 */
@Entity
@Table(name = "ehrs")
public class Ehr {

    @Id
    @Column(name = "ehr_id", nullable = false, updatable = false)
    private UUID ehrId;

    @Column(name = "patient_id", nullable = false)
    private String patientId;

    @Column(name = "is_queryable", nullable = false)
    private boolean queryable;

    @Column(name = "created_at", nullable = false)
    private Date createdAt;

    public Ehr() {
    }

    public UUID getEhrId() {
        return ehrId;
    }

    public void setEhrId(UUID ehrId) {
        this.ehrId = ehrId;
    }

    public String getPatientId() {
        return patientId;
    }

    public void setPatientId(String patientId) {
        this.patientId = patientId;
    }

    public boolean isQueryable() {
        return queryable;
    }

    public void setQueryable(boolean queryable) {
        this.queryable = queryable;
    }

    public Date getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Date createdAt) {
        this.createdAt = createdAt;
    }
}
