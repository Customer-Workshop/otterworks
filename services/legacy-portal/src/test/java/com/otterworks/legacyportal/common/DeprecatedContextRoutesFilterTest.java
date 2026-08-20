package com.otterworks.legacyportal.common;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

/**
 * The three context prefixes are deprecated but unchanged: the headers are advisory only, and
 * neither the status codes nor the bodies may move (the parity suites replay against them).
 */
@SpringBootTest
@AutoConfigureMockMvc
class DeprecatedContextRoutesFilterTest {

    @Autowired private MockMvc mockMvc;

    @Test
    void announcementRoutesAreMarkedDeprecatedAndStillWork() throws Exception {
        mockMvc.perform(
                        post("/api/announcements")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"title\":\"T\",\"body\":\"B\",\"published\":true}"))
                .andExpect(status().isCreated())
                .andExpect(header().string("Deprecation", "true"))
                .andExpect(header().string("Sunset", DeprecatedContextRoutesFilter.SUNSET))
                .andExpect(jsonPath("$.title").value("T"))
                .andExpect(jsonPath("$.published").value(true));

        mockMvc.perform(get("/api/announcements/999999"))
                .andExpect(status().isNotFound())
                .andExpect(header().string("Deprecation", "true"))
                .andExpect(jsonPath("$.error").value("Not Found"))
                .andExpect(jsonPath("$.message").value("announcement 999999 not found"));
    }

    @Test
    void preferenceRoutesAreMarkedDeprecatedAndStillWork() throws Exception {
        mockMvc.perform(get("/api/preferences/someone"))
                .andExpect(status().isOk())
                .andExpect(header().string("Deprecation", "true"))
                .andExpect(header().string("Sunset", DeprecatedContextRoutesFilter.SUNSET))
                .andExpect(jsonPath("$.theme").value("light"));
    }

    @Test
    void feedbackRoutesAreMarkedDeprecatedAndStillWork() throws Exception {
        mockMvc.perform(get("/api/feedback/average-rating"))
                .andExpect(status().isOk())
                .andExpect(header().string("Deprecation", "true"))
                .andExpect(header().string("Sunset", DeprecatedContextRoutesFilter.SUNSET));
    }

    @Test
    void otherRoutesAreNotMarked() throws Exception {
        mockMvc.perform(get("/health"))
                .andExpect(status().isOk())
                .andExpect(header().doesNotExist("Deprecation"))
                .andExpect(header().doesNotExist("Sunset"));
    }
}
