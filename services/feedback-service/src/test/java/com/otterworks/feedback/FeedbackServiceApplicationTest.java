package com.otterworks.feedback;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

/** Full-context test: the service boots and serves the three feedback routes plus /health. */
@SpringBootTest
@AutoConfigureMockMvc
// Its own in-memory database: this test commits rows, and the repository tests assert over the
// whole table.
@TestPropertySource(
        properties =
                "spring.datasource.url=jdbc:h2:mem:feedback_apptest;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE;INIT=CREATE SCHEMA IF NOT EXISTS FEEDBACK")
class FeedbackServiceApplicationTest {

    @Autowired private MockMvc mockMvc;

    @Test
    void healthEndpointReportsUp() throws Exception {
        mockMvc.perform(get("/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.service").value("feedback-service"));
    }

    @Test
    void actuatorHealthIsUp() throws Exception {
        mockMvc.perform(get("/actuator/health")).andExpect(status().isOk());
    }

    @Test
    void submitAndListRoundTrips() throws Exception {
        mockMvc.perform(
                        post("/api/feedback")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(
                                        "{\"userId\":\"roundtrip\",\"rating\":5,\"message\":\"great\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").isNumber())
                .andExpect(jsonPath("$.userId").value("roundtrip"))
                .andExpect(jsonPath("$.rating").value(5))
                .andExpect(jsonPath("$.message").value("great"))
                .andExpect(jsonPath("$.createdAt").exists());

        mockMvc.perform(get("/api/feedback").param("userId", "roundtrip"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].userId").value("roundtrip"))
                .andExpect(jsonPath("$[0].rating").value(5));
    }

    @Test
    void validatesRating() throws Exception {
        mockMvc.perform(
                        post("/api/feedback")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"userId\":\"u1\",\"rating\":9,\"message\":\"bad rating\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void averageRatingIsAlwaysANumber() throws Exception {
        mockMvc.perform(get("/api/feedback/average-rating"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.averageRating").isNumber());
    }
}
