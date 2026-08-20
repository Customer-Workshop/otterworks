package com.otterworks.legacyportal.userpreferences;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.otterworks.legacyportal.common.CallerIdentity;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

/** Preferences are scoped to the caller, not to the path variable. */
@SpringBootTest
@AutoConfigureMockMvc
class UserPreferenceAuthorizationTest {

    private static final String BODY =
            "{\"theme\":\"dark\",\"locale\":\"fr-FR\",\"emailNotifications\":false}";

    @Autowired private MockMvc mockMvc;

    @Test
    void anonymousReadIsRejected() throws Exception {
        mockMvc.perform(get("/api/preferences/victim")).andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousWriteIsRejected() throws Exception {
        mockMvc.perform(put("/api/preferences/victim").contentType(MediaType.APPLICATION_JSON).content(BODY))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void readingAnotherUsersPreferencesIsForbidden() throws Exception {
        mockMvc.perform(get("/api/preferences/victim").header(CallerIdentity.HEADER, "attacker"))
                .andExpect(status().isForbidden());
    }

    @Test
    void writingAnotherUsersPreferencesIsForbidden() throws Exception {
        mockMvc.perform(
                        put("/api/preferences/victim")
                                .header(CallerIdentity.HEADER, "attacker")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(BODY))
                .andExpect(status().isForbidden());

        // The victim's stored preferences are untouched: still the defaults.
        mockMvc.perform(get("/api/preferences/victim").header(CallerIdentity.HEADER, "victim"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.theme").value("light"))
                .andExpect(jsonPath("$.locale").value("en-US"))
                .andExpect(jsonPath("$.emailNotifications").value(true));
    }

    @Test
    void ownPreferencesRoundTripUnchanged() throws Exception {
        mockMvc.perform(get("/api/preferences/owner-1").header(CallerIdentity.HEADER, "owner-1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId").value("owner-1"))
                .andExpect(jsonPath("$.theme").value("light"));

        mockMvc.perform(
                        put("/api/preferences/owner-1")
                                .header(CallerIdentity.HEADER, "owner-1")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(BODY))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.theme").value("dark"))
                .andExpect(jsonPath("$.locale").value("fr-FR"))
                .andExpect(jsonPath("$.emailNotifications").value(false));

        mockMvc.perform(get("/api/preferences/owner-1").header(CallerIdentity.HEADER, "owner-1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.theme").value("dark"));
    }
}
