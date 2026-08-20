package com.otterworks.portal.feedback;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface FeedbackRepository extends JpaRepository<Feedback, Long> {

    List<Feedback> findByUserIdOrderByCreatedAtDesc(String userId);

    /**
     * SQL aggregate instead of the monolith's {@code findAll()} + stream average. Returns
     * {@code null} for an empty table, which the service maps to {@code 0.0}.
     */
    @Query("select avg(f.rating) from Feedback f")
    Double averageRating();
}
