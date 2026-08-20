package com.otterworks.legacyportal.announcements;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.otterworks.legacyportal.common.CallerIdentity;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

/** Announcement routes require an authenticated caller; the content itself is portal-wide. */
@SpringBootTest
@AutoConfigureMockMvc
class AnnouncementAuthorizationTest {

    private static final String BODY =
            "{\"title\":\"Maintenance\",\"body\":\"Portal read-only Saturday\",\"published\":false}";

    @Autowired private MockMvc mockMvc;

    @Test
    void anonymousCreateIsRejected() throws Exception {
        mockMvc.perform(post("/api/announcements").contentType(MediaType.APPLICATION_JSON).content(BODY))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.message").value("missing X-User-ID header"));
    }

    @Test
    void anonymousPublishIsRejected() throws Exception {
        mockMvc.perform(post("/api/announcements/1/publish")).andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousReadIsRejected() throws Exception {
        mockMvc.perform(get("/api/announcements")).andExpect(status().isUnauthorized());
    }

    @Test
    void blankIdentityIsRejected() throws Exception {
        mockMvc.perform(get("/api/announcements").header(CallerIdentity.HEADER, "   "))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedCallerCreatesPublishesAndReads() throws Exception {
        String created =
                mockMvc.perform(
                                post("/api/announcements")
                                        .header(CallerIdentity.HEADER, "editor-1")
                                        .contentType(MediaType.APPLICATION_JSON)
                                        .content(BODY))
                        .andExpect(status().isCreated())
                        .andExpect(jsonPath("$.title").value("Maintenance"))
                        .andExpect(jsonPath("$.published").value(false))
                        .andReturn()
                        .getResponse()
                        .getContentAsString();
        long id = Long.parseLong(created.replaceAll(".*\"id\":(\\d+).*", "$1"));

        mockMvc.perform(post("/api/announcements/" + id + "/publish").header(CallerIdentity.HEADER, "editor-1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.published").value(true));

        mockMvc.perform(get("/api/announcements/" + id).header(CallerIdentity.HEADER, "reader-1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Maintenance"));
    }
}
