package com.otterworks.portal.feedback;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/feedback")
public class FeedbackController {

    private final FeedbackService service;

    public FeedbackController(FeedbackService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public FeedbackResponse submit(@Valid @RequestBody SubmitFeedbackRequest request) {
        return FeedbackResponse.from(
                service.submit(request.getUserId(), request.getRating(), request.getMessage()));
    }

    @GetMapping
    public List<FeedbackResponse> listForUser(@RequestParam String userId) {
        return service.listForUser(userId).stream().map(FeedbackResponse::from).toList();
    }

    @GetMapping("/average-rating")
    public AverageRatingResponse averageRating() {
        return new AverageRatingResponse(service.averageRating());
    }

    /** {@code rating} binds to a primitive, so absent or null becomes 0 and fails {@code @Min}. */
    public static class SubmitFeedbackRequest {

        @NotBlank
        @Size(max = 100)
        private String userId;

        @Min(1)
        @Max(5)
        private int rating;

        @NotBlank
        @Size(max = 2000)
        private String message;

        public String getUserId() {
            return userId;
        }

        public void setUserId(String userId) {
            this.userId = userId;
        }

        public int getRating() {
            return rating;
        }

        public void setRating(int rating) {
            this.rating = rating;
        }

        public String getMessage() {
            return message;
        }

        public void setMessage(String message) {
            this.message = message;
        }
    }

    public record FeedbackResponse(
            Long id, String userId, int rating, String message, Instant createdAt) {

        static FeedbackResponse from(Feedback f) {
            return new FeedbackResponse(
                    f.getId(), f.getUserId(), f.getRating(), f.getMessage(), f.getCreatedAt());
        }
    }

    public record AverageRatingResponse(double averageRating) {}
}
