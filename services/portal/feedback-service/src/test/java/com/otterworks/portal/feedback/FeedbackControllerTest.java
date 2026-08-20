package com.otterworks.portal.feedback;

import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.lang.reflect.Field;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

/** Contract §1 (field set/order), §2.1–2.4 and §5 (status codes) over the HTTP surface. */
@WebMvcTest(FeedbackController.class)
class FeedbackControllerTest {

    private static final Instant CREATED_AT = Instant.parse("2026-08-20T20:46:26.381878Z");

    @Autowired private MockMvc mvc;

    @MockBean private FeedbackService service;

    @Test
    void createReturns201WithTheFiveFieldsInOrderAndNoLocationHeader() throws Exception {
        when(service.submit("u1", 5, "great")).thenReturn(feedback(1L, "u1", 5, "great"));

        mvc.perform(
                        post("/api/feedback")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"userId\":\"u1\",\"rating\":5,\"message\":\"great\"}"))
                .andExpect(status().isCreated())
                .andExpect(
                        content()
                                .string(
                                        "{\"id\":1,\"userId\":\"u1\",\"rating\":5,"
                                                + "\"message\":\"great\","
                                                + "\"createdAt\":\"2026-08-20T20:46:26.381878Z\"}"))
                .andExpect(header().doesNotExist("Location"));
    }

    @Test
    void createIgnoresUnknownFields() throws Exception {
        when(service.submit("u1", 5, "great")).thenReturn(feedback(1L, "u1", 5, "great"));

        mvc.perform(
                        post("/api/feedback")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(
                                        "{\"userId\":\"u1\",\"rating\":5,\"message\":\"great\","
                                                + "\"moderated\":true,\"id\":99}"))
                .andExpect(status().isCreated());
    }

    @Test
    void createRejectsRatingOutsideOneToFiveBeforeReachingTheService() throws Exception {
        for (String rating : List.of("0", "6", "-1", "100")) {
            mvc.perform(
                            post("/api/feedback")
                                    .contentType(MediaType.APPLICATION_JSON)
                                    .content(
                                            "{\"userId\":\"u1\",\"rating\":"
                                                    + rating
                                                    + ",\"message\":\"m\"}"))
                    .andExpect(status().isBadRequest());
        }
        verify(service, never()).submit(anyString(), anyInt(), anyString());
    }

    /** Primitive binding: absent or null rating becomes 0, which then fails @Min(1). */
    @Test
    void createRejectsAbsentOrNullRating() throws Exception {
        mvc.perform(
                        post("/api/feedback")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"userId\":\"u1\",\"message\":\"m\"}"))
                .andExpect(status().isBadRequest());

        mvc.perform(
                        post("/api/feedback")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"userId\":\"u1\",\"rating\":null,\"message\":\"m\"}"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void createRejectsBlankMissingAndOversizedUserId() throws Exception {
        String oversized = "u".repeat(101);
        for (String userId : List.of("\"\"", "\"   \"", "null", "\"" + oversized + "\"")) {
            mvc.perform(
                            post("/api/feedback")
                                    .contentType(MediaType.APPLICATION_JSON)
                                    .content(
                                            "{\"userId\":"
                                                    + userId
                                                    + ",\"rating\":3,\"message\":\"m\"}"))
                    .andExpect(status().isBadRequest());
        }
        mvc.perform(
                        post("/api/feedback")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"rating\":3,\"message\":\"m\"}"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void createRejectsBlankMissingAndOversizedMessage() throws Exception {
        String oversized = "m".repeat(2001);
        for (String message : List.of("\"\"", "\"   \"", "null", "\"" + oversized + "\"")) {
            mvc.perform(
                            post("/api/feedback")
                                    .contentType(MediaType.APPLICATION_JSON)
                                    .content(
                                            "{\"userId\":\"u1\",\"rating\":3,\"message\":"
                                                    + message
                                                    + "}"))
                    .andExpect(status().isBadRequest());
        }
        mvc.perform(
                        post("/api/feedback")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"userId\":\"u1\",\"rating\":3}"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void createAcceptsBoundaryLengthsAndRatings() throws Exception {
        String userId = "u".repeat(100);
        String message = "m".repeat(2000);
        when(service.submit(eq(userId), anyInt(), eq(message)))
                .thenReturn(feedback(1L, userId, 1, message));

        for (int rating : new int[] {1, 5}) {
            mvc.perform(
                            post("/api/feedback")
                                    .contentType(MediaType.APPLICATION_JSON)
                                    .content(
                                            "{\"userId\":\""
                                                    + userId
                                                    + "\",\"rating\":"
                                                    + rating
                                                    + ",\"message\":\""
                                                    + message
                                                    + "\"}"))
                    .andExpect(status().isCreated());
        }
    }

    @Test
    void createRejectsMalformedJson() throws Exception {
        mvc.perform(
                        post("/api/feedback")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"userId\":\"u1\",\"rating\":"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void listReturnsTheUsersFeedbackNewestFirst() throws Exception {
        when(service.listForUser("u1"))
                .thenReturn(List.of(feedback(2L, "u1", 1, "bad"), feedback(1L, "u1", 5, "great")));

        mvc.perform(get("/api/feedback").param("userId", "u1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2))
                .andExpect(jsonPath("$[0].id").value(2))
                .andExpect(jsonPath("$[1].id").value(1));
    }

    @Test
    void listWithoutTheUserIdParameterIs400() throws Exception {
        mvc.perform(get("/api/feedback")).andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void listForAnUnknownUserIsAnEmptyArrayNotA404() throws Exception {
        when(service.listForUser("nobody")).thenReturn(List.of());

        mvc.perform(get("/api/feedback").param("userId", "nobody"))
                .andExpect(status().isOk())
                .andExpect(content().string("[]"));
    }

    @Test
    void averageRatingIsSerialisedAsAJsonNumber() throws Exception {
        when(service.averageRating()).thenReturn(3.0);

        mvc.perform(get("/api/feedback/average-rating"))
                .andExpect(status().isOk())
                .andExpect(content().string("{\"averageRating\":3.0}"));
    }

    @Test
    void averageRatingOverAnEmptyTableIsZero() throws Exception {
        when(service.averageRating()).thenReturn(0.0);

        mvc.perform(get("/api/feedback/average-rating"))
                .andExpect(status().isOk())
                .andExpect(content().string("{\"averageRating\":0.0}"));
    }

    /** Append-only: no update, delete or moderation route exists. */
    @Test
    void mutatingMethodsAreNotMapped() throws Exception {
        mvc.perform(put("/api/feedback/1").contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isNotFound());
        mvc.perform(patch("/api/feedback/1").contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isNotFound());
        mvc.perform(delete("/api/feedback/1")).andExpect(status().isNotFound());
        mvc.perform(delete("/api/feedback")).andExpect(status().isMethodNotAllowed());
        mvc.perform(put("/api/feedback").contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isMethodNotAllowed());

        verifyNoInteractions(service);
    }

    /** There is no GET /api/feedback/{id} in the monolith; nothing may add one. */
    @Test
    void thereIsNoGetByIdRoute() throws Exception {
        mvc.perform(get("/api/feedback/1")).andExpect(status().isNotFound());
    }

    private static Feedback feedback(Long id, String userId, int rating, String message) {
        Feedback feedback = new Feedback(userId, rating, message);
        set(feedback, "id", id);
        set(feedback, "createdAt", CREATED_AT);
        return feedback;
    }

    private static void set(Feedback feedback, String name, Object value) {
        try {
            Field field = Feedback.class.getDeclaredField(name);
            field.setAccessible(true);
            field.set(feedback, value);
        } catch (ReflectiveOperationException e) {
            throw new IllegalStateException(e);
        }
    }
}
