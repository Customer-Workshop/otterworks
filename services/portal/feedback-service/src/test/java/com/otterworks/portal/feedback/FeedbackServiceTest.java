package com.otterworks.portal.feedback;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/** Contract §2.1 (in-process rating guard) and §2.3 (SQL aggregate, empty table → 0.0). */
@ExtendWith(MockitoExtension.class)
class FeedbackServiceTest {

    @Mock private FeedbackRepository repository;

    @InjectMocks private FeedbackService service;

    @Test
    void submitPersistsTheSubmittedFields() {
        when(repository.save(any(Feedback.class))).thenAnswer(call -> call.getArgument(0));

        service.submit("u1", 5, "great");

        ArgumentCaptor<Feedback> saved = ArgumentCaptor.forClass(Feedback.class);
        verify(repository).save(saved.capture());
        assertThat(saved.getValue().getUserId()).isEqualTo("u1");
        assertThat(saved.getValue().getRating()).isEqualTo(5);
        assertThat(saved.getValue().getMessage()).isEqualTo("great");
        assertThat(saved.getValue().getCreatedAt()).isNotNull();
    }

    /**
     * Unreachable over HTTP (bean validation wins), but it is the monolith's in-process guard and
     * the message string is part of the service API.
     */
    @Test
    void submitRejectsOutOfRangeRatingWithThePinnedMessage() {
        assertThatThrownBy(() -> service.submit("u1", 6, "too high"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("rating must be between 1 and 5");
        assertThatThrownBy(() -> service.submit("u1", 0, "too low"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("rating must be between 1 and 5");

        verify(repository, never()).save(any());
    }

    @Test
    void averageRatingMapsANullAggregateToZero() {
        when(repository.averageRating()).thenReturn(null);

        assertThat(service.averageRating()).isEqualTo(0.0);
    }

    @Test
    void averageRatingUsesTheAggregateAndNeverLoadsRows() {
        when(repository.averageRating()).thenReturn(3.5);

        assertThat(service.averageRating()).isEqualTo(3.5);
        verify(repository, never()).findAll();
    }

    @Test
    void listForUserDelegatesToTheNewestFirstQuery() {
        service.listForUser("u1");

        verify(repository).findByUserIdOrderByCreatedAtDesc("u1");
    }
}
