package com.otterworks.report.repository.ehr;

import com.otterworks.report.model.ehr.Composition;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.Collection;
import java.util.UUID;

@Repository
public interface CompositionRepository extends JpaRepository<Composition, Long> {

    Page<Composition> findByEhrIdIn(Collection<UUID> ehrIds, Pageable pageable);

    @Query("SELECT COUNT(c) FROM Composition c WHERE c.ehrId IN :ehrIds")
    long countByEhrIds(@Param("ehrIds") Collection<UUID> ehrIds);
}
