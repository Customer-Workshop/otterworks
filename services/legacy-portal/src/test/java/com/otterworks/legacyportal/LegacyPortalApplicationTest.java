package com.otterworks.legacyportal;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

/** The shell boots and serves only its own plumbing: no bounded context is wired any more. */
@SpringBootTest
@AutoConfigureMockMvc
class LegacyPortalApplicationTest {

    @Autowired private MockMvc mockMvc;

    @Test
    void healthEndpointReportsUp() throws Exception {
        mockMvc.perform(get("/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.service").value("legacy-portal"));
    }

    @Test
    void actuatorHealthIsUp() throws Exception {
        mockMvc.perform(get("/actuator/health")).andExpect(status().isOk());
    }

    @Test
    void announcementRoutesAreGone() throws Exception {
        mockMvc.perform(get("/api/announcements")).andExpect(status().isNotFound());
    }

    @Test
    void preferenceRoutesAreGone() throws Exception {
        mockMvc.perform(get("/api/preferences/someone")).andExpect(status().isNotFound());
    }

    @Test
    void feedbackRoutesAreGone() throws Exception {
        mockMvc.perform(get("/api/feedback/average-rating")).andExpect(status().isNotFound());
    }
}
