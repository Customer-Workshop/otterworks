package com.otterworks.report.repository.ehr;

import com.otterworks.report.model.ehr.Ehr;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface EhrRepository extends JpaRepository<Ehr, UUID> {

    List<Ehr> findByPatientId(String patientId);

    @Query("SELECT e.queryable FROM Ehr e WHERE e.ehrId = :ehrId")
    Boolean fetchIsQueryable(@Param("ehrId") UUID ehrId);

    List<Ehr> findByPatientIdAndQueryableTrue(String patientId);
}
