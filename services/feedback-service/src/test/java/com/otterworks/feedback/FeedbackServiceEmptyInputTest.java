package com.otterworks.feedback;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

/** Empty-input semantics of the average rating, carried over from the monolith: 0.0, not null. */
class FeedbackServiceEmptyInputTest {

    @Test
    void averageRatingIsZeroWhenThereIsNoFeedback() {
        FeedbackRepository repository = Mockito.mock(FeedbackRepository.class);
        given(repository.findAll()).willReturn(List.of());

        assertThat(new FeedbackService(repository).averageRating()).isEqualTo(0.0);
    }
}
