package com.otterworks.report.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Tests for {@link SecurityConfig} endpoint access rules.
 *
 * All listed endpoints are permit-all (no authentication) and security
 * headers are applied to responses.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
public class SecurityConfigTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    public void healthEndpointIsAccessibleWithoutAuthentication() throws Exception {
        mockMvc.perform(get("/health"))
                .andExpect(status().isOk());
    }

    @Test
    public void actuatorHealthIsAccessibleWithoutAuthentication() throws Exception {
        mockMvc.perform(get("/actuator/health"))
                .andExpect(status().isOk());
    }

    @Test
    public void reportsApiIsAccessibleWithoutAuthentication() throws Exception {
        mockMvc.perform(get("/api/v1/reports"))
                .andExpect(status().isOk());
    }

    @Test
    public void reportsApiSubPathsAreAccessibleWithoutAuthentication() throws Exception {
        // 404 (not 401/403) proves the request passed the security filter
        mockMvc.perform(get("/api/v1/reports/424242"))
                .andExpect(status().isNotFound());
    }

    @Test
    public void responsesIncludeSecurityHeaders() throws Exception {
        mockMvc.perform(get("/health"))
                .andExpect(header().string("X-Frame-Options", "DENY"))
                .andExpect(header().string("X-Content-Type-Options", "nosniff"));
    }
}
