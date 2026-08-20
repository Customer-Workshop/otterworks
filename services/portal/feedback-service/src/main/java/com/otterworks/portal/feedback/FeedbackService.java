package com.otterworks.portal.feedback;

import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class FeedbackService {

    static final int MIN_RATING = 1;
    static final int MAX_RATING = 5;

    private final FeedbackRepository repository;

    public FeedbackService(FeedbackRepository repository) {
        this.repository = repository;
    }

    /**
     * The bounds check is unreachable over HTTP — bean validation on the request DTO runs first
     * — but it is the in-process guard the monolith ships and removing it changes the service
     * API. Its message string is pinned by a unit test.
     */
    @Transactional
    public Feedback submit(String userId, int rating, String message) {
        if (rating < MIN_RATING || rating > MAX_RATING) {
            throw new IllegalArgumentException(
                    "rating must be between " + MIN_RATING + " and " + MAX_RATING);
        }
        return repository.save(new Feedback(userId, rating, message));
    }

    @Transactional(readOnly = true)
    public List<Feedback> listForUser(String userId) {
        return repository.findByUserIdOrderByCreatedAtDesc(userId);
    }

    @Transactional(readOnly = true)
    public double averageRating() {
        Double average = repository.averageRating();
        return average == null ? 0.0 : average;
    }
}
