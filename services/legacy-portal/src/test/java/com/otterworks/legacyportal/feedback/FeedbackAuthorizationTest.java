package com.otterworks.legacyportal.feedback;

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

/** Feedback is read and written under the caller's identity, never a client-supplied one. */
@SpringBootTest
@AutoConfigureMockMvc
class FeedbackAuthorizationTest {

    @Autowired private MockMvc mockMvc;

    @Test
    void anonymousListIsRejected() throws Exception {
        mockMvc.perform(get("/api/feedback").param("userId", "victim"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousSubmitIsRejected() throws Exception {
        mockMvc.perform(
                        post("/api/feedback")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"userId\":\"victim\",\"rating\":1,\"message\":\"spoofed\"}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void listingAnotherUsersFeedbackIsForbidden() throws Exception {
        mockMvc.perform(
                        get("/api/feedback")
                                .param("userId", "victim")
                                .header(CallerIdentity.HEADER, "attacker"))
                .andExpect(status().isForbidden());
    }

    @Test
    void submittingFeedbackForAnotherUserIsForbidden() throws Exception {
        mockMvc.perform(
                        post("/api/feedback")
                                .header(CallerIdentity.HEADER, "attacker")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"userId\":\"victim\",\"rating\":1,\"message\":\"spoofed\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void feedbackIsAttributedToTheCallerWhenTheBodyOmitsTheUserId() throws Exception {
        mockMvc.perform(
                        post("/api/feedback")
                                .header(CallerIdentity.HEADER, "author-1")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"rating\":5,\"message\":\"no user id in body\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.userId").value("author-1"));
    }

    @Test
    void ownFeedbackRoundTripsUnchanged() throws Exception {
        mockMvc.perform(
                        post("/api/feedback")
                                .header(CallerIdentity.HEADER, "author-2")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"userId\":\"author-2\",\"rating\":4,\"message\":\"portal is usable\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.userId").value("author-2"))
                .andExpect(jsonPath("$.rating").value(4));

        mockMvc.perform(
                        get("/api/feedback")
                                .param("userId", "author-2")
                                .header(CallerIdentity.HEADER, "author-2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].message").value("portal is usable"));
    }

    @Test
    void averageRatingRequiresAnIdentityButStaysPortalWide() throws Exception {
        mockMvc.perform(get("/api/feedback/average-rating")).andExpect(status().isUnauthorized());

        mockMvc.perform(get("/api/feedback/average-rating").header(CallerIdentity.HEADER, "anyone"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.averageRating").isNumber());
    }
}
