package com.otterworks.portal.userpreferences;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
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
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

/** Contract §2 routes and §5 statuses at the web layer. */
@WebMvcTest(UserPreferenceController.class)
class UserPreferenceControllerTest {

    @Autowired private MockMvc mvc;

    @MockBean private UserPreferenceService service;

    @Test
    void getUnknownUserReturns200WithFabricatedDefaultsInContractFieldOrder() throws Exception {
        when(service.getOrDefault("unknown-user"))
                .thenReturn(new UserPreference("unknown-user", "light", "en-US", true));

        mvc.perform(get("/api/preferences/unknown-user"))
                .andExpect(status().isOk())
                .andExpect(
                        content()
                                .json(
                                        "{\"userId\":\"unknown-user\",\"theme\":\"light\","
                                                + "\"locale\":\"en-US\",\"emailNotifications\":true}",
                                        true))
                .andExpect(jsonPath("$.message").doesNotExist());

        verify(service, never()).save(anyString(), anyString(), anyString(), anyBoolean());
    }

    @Test
    void getStoredUserReturns200WithTheStoredRow() throws Exception {
        when(service.getOrDefault("u1"))
                .thenReturn(new UserPreference("u1", "dark", "fr-FR", false));

        mvc.perform(get("/api/preferences/u1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId").value("u1"))
                .andExpect(jsonPath("$.theme").value("dark"))
                .andExpect(jsonPath("$.locale").value("fr-FR"))
                .andExpect(jsonPath("$.emailNotifications").value(false));
    }

    @Test
    void putReturns200EvenWhenItCreatesTheRow() throws Exception {
        when(service.save("new-user", "dark", "fr-FR", false))
                .thenReturn(new UserPreference("new-user", "dark", "fr-FR", false));

        mvc.perform(
                        put("/api/preferences/new-user")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(
                                        "{\"theme\":\"dark\",\"locale\":\"fr-FR\","
                                                + "\"emailNotifications\":false}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId").value("new-user"));
    }

    /** §2.2: emailNotifications binds to a primitive — absent or null becomes false. */
    @Test
    void absentEmailNotificationsBindsToFalse() throws Exception {
        when(service.save(eq("u1"), anyString(), anyString(), anyBoolean()))
                .thenReturn(new UserPreference("u1", "dark", "fr-FR", false));

        mvc.perform(
                        put("/api/preferences/u1")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"theme\":\"dark\",\"locale\":\"fr-FR\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.emailNotifications").value(false));

        verify(service).save("u1", "dark", "fr-FR", false);
    }

    @Test
    void nullEmailNotificationsBindsToFalse() throws Exception {
        when(service.save(eq("u1"), anyString(), anyString(), anyBoolean()))
                .thenReturn(new UserPreference("u1", "dark", "fr-FR", false));

        mvc.perform(
                        put("/api/preferences/u1")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(
                                        "{\"theme\":\"dark\",\"locale\":\"fr-FR\","
                                                + "\"emailNotifications\":null}"))
                .andExpect(status().isOk());

        verify(service).save("u1", "dark", "fr-FR", false);
    }

    /** §2.2: a userId in the body is an unknown field and stays ignored. */
    @Test
    void userIdInTheBodyIsIgnored() throws Exception {
        when(service.save(eq("u1"), anyString(), anyString(), anyBoolean()))
                .thenReturn(new UserPreference("u1", "dark", "fr-FR", true));

        mvc.perform(
                        put("/api/preferences/u1")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(
                                        "{\"userId\":\"someone-else\",\"theme\":\"dark\","
                                                + "\"locale\":\"fr-FR\",\"emailNotifications\":true}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId").value("u1"));

        verify(service).save("u1", "dark", "fr-FR", true);
    }

    /** §1: theme and locale are not enums — any non-blank string up to 20 characters passes. */
    @Test
    void arbitraryThemeAndLocaleAreAccepted() throws Exception {
        when(service.save(eq("u1"), anyString(), anyString(), anyBoolean()))
                .thenReturn(new UserPreference("u1", "chartreuse", "not a locale", true));

        mvc.perform(
                        put("/api/preferences/u1")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(
                                        "{\"theme\":\"chartreuse\",\"locale\":\"not a locale\","
                                                + "\"emailNotifications\":true}"))
                .andExpect(status().isOk());

        verify(service).save("u1", "chartreuse", "not a locale", true);
    }

    @Test
    void blankMissingAndOversizedFieldsAre400AndNeverReachTheService() throws Exception {
        String[] bodies = {
            "{\"theme\":\"\",\"locale\":\"fr-FR\"}",
            "{\"theme\":\"   \",\"locale\":\"fr-FR\"}",
            "{\"locale\":\"fr-FR\"}",
            "{\"theme\":null,\"locale\":\"fr-FR\"}",
            "{\"theme\":\"dark\",\"locale\":\"\"}",
            "{\"theme\":\"dark\"}",
            "{\"theme\":\"twenty-one-chars-long\",\"locale\":\"fr-FR\"}",
            "{\"theme\":\"dark\",\"locale\":\"twenty-one-chars-long\"}"
        };
        for (String body : bodies) {
            mvc.perform(
                            put("/api/preferences/u1")
                                    .contentType(MediaType.APPLICATION_JSON)
                                    .content(body))
                    .andExpect(status().isBadRequest());
        }
        verifyNoInteractions(service);
    }

    @Test
    void twentyCharacterFieldsAreAccepted() throws Exception {
        String twenty = "12345678901234567890";
        assertThat(twenty).hasSize(20);
        when(service.save(eq("u1"), anyString(), anyString(), anyBoolean()))
                .thenReturn(new UserPreference("u1", twenty, twenty, true));

        mvc.perform(
                        put("/api/preferences/u1")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(
                                        "{\"theme\":\""
                                                + twenty
                                                + "\",\"locale\":\""
                                                + twenty
                                                + "\",\"emailNotifications\":true}"))
                .andExpect(status().isOk());
    }

    @Test
    void malformedJsonIs400() throws Exception {
        mvc.perform(
                        put("/api/preferences/u1")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"theme\":"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    /** §2.3: no PATCH, no DELETE, no create, no list route. */
    @Test
    void unmappedMethodsAndPathsAreNotHandled() throws Exception {
        mvc.perform(
                        patch("/api/preferences/u1")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"theme\":\"dark\"}"))
                .andExpect(status().isMethodNotAllowed());
        mvc.perform(delete("/api/preferences/u1")).andExpect(status().isMethodNotAllowed());
        mvc.perform(
                        post("/api/preferences")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"theme\":\"dark\"}"))
                .andExpect(status().isNotFound());
        mvc.perform(get("/api/preferences")).andExpect(status().isNotFound());

        verifyNoInteractions(service);
    }

    /** §2.1: an over-long userId still fabricates defaults on GET; it only fails on PUT. */
    @Test
    void getWithAnOverLongUserIdStillReturns200() throws Exception {
        String longId = "x".repeat(150);
        when(service.getOrDefault(longId))
                .thenReturn(new UserPreference(longId, "light", "en-US", true));

        mvc.perform(get("/api/preferences/" + longId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId").value(longId));
    }

    @Test
    void pathSegmentIsPassedThroughVerbatim() throws Exception {
        when(service.getOrDefault(any())).thenReturn(new UserPreference("ü", "light", "en-US", true));

        mvc.perform(get("/api/preferences/{userId}", "ü")).andExpect(status().isOk());

        ArgumentCaptor<String> captor = ArgumentCaptor.forClass(String.class);
        verify(service).getOrDefault(captor.capture());
        assertThat(captor.getValue()).isEqualTo("ü");
    }
}
