package com.otterworks.feedback.common;

import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.otterworks.feedback.FeedbackController;
import com.otterworks.feedback.FeedbackService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

/**
 * The {@code {"error": <reason phrase>, "message": <exception message>}} body the monolith's
 * handler produced for a service-level {@link IllegalArgumentException}.
 */
@WebMvcTest(FeedbackController.class)
@Import(GlobalExceptionHandler.class)
class GlobalExceptionHandlerTest {

    @Autowired private MockMvc mockMvc;

    @MockBean private FeedbackService service;

    @Test
    void illegalArgumentBecomesBadRequestWithErrorAndMessage() throws Exception {
        given(service.submit("u1", 3, "ok"))
                .willThrow(new IllegalArgumentException("rating must be between 1 and 5"));

        mockMvc.perform(
                        post("/api/feedback")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"userId\":\"u1\",\"rating\":3,\"message\":\"ok\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("Bad Request"))
                .andExpect(jsonPath("$.message").value("rating must be between 1 and 5"));
    }
}
