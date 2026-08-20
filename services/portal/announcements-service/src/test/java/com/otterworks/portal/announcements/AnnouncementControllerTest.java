package com.otterworks.portal.announcements;

import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.otterworks.portal.common.PortalCommonAutoConfiguration;
import java.util.List;
import java.util.NoSuchElementException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

/**
 * Route-level cover for the announcements contract: §2.1 listing and its default, §2.2 read,
 * §2.3 create, §2.4 publish, and the legacy error envelope on both conversion failures.
 *
 * <p>{@link PortalCommonAutoConfiguration} is imported because a slice test does not apply
 * auto-configurations contributed by libraries; nothing is re-declared.
 */
@WebMvcTest(controllers = AnnouncementController.class)
@Import(PortalCommonAutoConfiguration.class)
class AnnouncementControllerTest {

    @Autowired private MockMvc mvc;

    @MockBean private AnnouncementService service;

    private static Announcement announcement(String title, boolean published) {
        return new Announcement(title, "body", published);
    }

    /** §2.1: publishedOnly defaults to true. */
    @Test
    void listWithoutParameterReturnsPublishedOnly() throws Exception {
        when(service.listPublished()).thenReturn(List.of(announcement("A", true)));

        mvc.perform(get("/api/announcements"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].title").value("A"))
                .andExpect(jsonPath("$[0].published").value(true));

        verify(service, never()).listAll();
    }

    /** §2.1: publishedOnly=false returns every row, via findAll(). */
    @Test
    void listWithPublishedOnlyFalseReturnsEverything() throws Exception {
        when(service.listAll())
                .thenReturn(List.of(announcement("A", false), announcement("B", true)));

        mvc.perform(get("/api/announcements").param("publishedOnly", "false"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2));

        verify(service, never()).listPublished();
    }

    /** §2.1: empty result is [], never 204 and never an envelope object. */
    @Test
    void emptyListingIsAnEmptyArray() throws Exception {
        when(service.listPublished()).thenReturn(List.of());

        mvc.perform(get("/api/announcements"))
                .andExpect(status().isOk())
                .andExpect(content().json("[]", true));
    }

    /** §2.1: unrecognised query parameters stay ignored. */
    @Test
    void unknownQueryParameterIsIgnored() throws Exception {
        when(service.listPublished()).thenReturn(List.of());

        mvc.perform(get("/api/announcements").param("page", "2"))
                .andExpect(status().isOk())
                .andExpect(content().json("[]", true));
    }

    /** §2.1: an unparseable publishedOnly is the legacy envelope with the converter message. */
    @Test
    void unparseablePublishedOnlyIsLegacyBadRequest() throws Exception {
        mvc.perform(get("/api/announcements").param("publishedOnly", "maybe"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("Bad Request"))
                .andExpect(jsonPath("$.message").value("Invalid boolean value [maybe]"))
                .andExpect(jsonPath("$.timestamp").doesNotExist());
    }

    /** §1: the wire representation is exactly these five fields. */
    @Test
    void readReturnsTheContractFieldSet() throws Exception {
        Announcement a = announcement("A", true);
        when(service.get(1L)).thenReturn(a);

        mvc.perform(get("/api/announcements/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("A"))
                .andExpect(jsonPath("$.body").value("body"))
                .andExpect(jsonPath("$.published").value(true))
                .andExpect(jsonPath("$.createdAt").exists())
                .andExpect(jsonPath("$.updatedAt").doesNotExist())
                .andExpect(jsonPath("$._links").doesNotExist());
    }

    /** §2.2: unknown id is the legacy 404 envelope with a byte-exact message. */
    @Test
    void unknownIdIsLegacyNotFound() throws Exception {
        when(service.get(999999L))
                .thenThrow(new NoSuchElementException("announcement 999999 not found"));

        mvc.perform(get("/api/announcements/999999"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").value("Not Found"))
                .andExpect(jsonPath("$.message").value("announcement 999999 not found"))
                .andExpect(jsonPath("$.timestamp").doesNotExist());
    }

    /** §2.2: a non-numeric id is the legacy 400 envelope carrying NumberFormatException. */
    @Test
    void nonNumericIdIsLegacyBadRequest() throws Exception {
        mvc.perform(get("/api/announcements/abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("Bad Request"))
                .andExpect(jsonPath("$.message").value("For input string: \"abc\""))
                .andExpect(jsonPath("$.timestamp").doesNotExist());
    }

    /** §2.3: absent published binds to the primitive default, false. */
    @Test
    void createDefaultsPublishedToFalse() throws Exception {
        when(service.create("A", "body", false)).thenReturn(announcement("A", false));

        mvc.perform(
                        post("/api/announcements")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"title\":\"A\",\"body\":\"body\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.published").value(false));

        verify(service).create("A", "body", false);
    }

    /** §2.3: an explicit null published also binds to false. */
    @Test
    void createWithNullPublishedBindsToFalse() throws Exception {
        when(service.create("A", "body", false)).thenReturn(announcement("A", false));

        mvc.perform(
                        post("/api/announcements")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"title\":\"A\",\"body\":\"body\",\"published\":null}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.published").value(false));

        verify(service).create("A", "body", false);
    }

    /** §2.3: published:true is honoured, not forced to false. */
    @Test
    void createHonoursPublishedTrue() throws Exception {
        when(service.create("A", "body", true)).thenReturn(announcement("A", true));

        mvc.perform(
                        post("/api/announcements")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"title\":\"A\",\"body\":\"body\",\"published\":true}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.published").value(true));

        verify(service).create("A", "body", true);
    }

    /** §2.3: unknown request fields are ignored. */
    @Test
    void createIgnoresUnknownFields() throws Exception {
        when(service.create("A", "body", false)).thenReturn(announcement("A", false));

        mvc.perform(
                        post("/api/announcements")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"title\":\"A\",\"body\":\"body\",\"nope\":1}"))
                .andExpect(status().isCreated());
    }

    /**
     * §2.3: bean-validation failures must not reach the legacy advice — no {@code error}/{@code
     * message} pair. The default envelope itself is asserted by the integration test, which runs
     * the real error dispatch.
     */
    @Test
    void blankTitleIsRejectedWithoutTheLegacyEnvelope() throws Exception {
        mvc.perform(
                        post("/api/announcements")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"title\":\"  \",\"body\":\"body\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").doesNotExist());

        verify(service, never()).create(eq("  "), eq("body"), eq(false));
    }

    @Test
    void oversizedTitleIsRejected() throws Exception {
        String title = "x".repeat(201);

        mvc.perform(
                        post("/api/announcements")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"title\":\"" + title + "\",\"body\":\"body\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").doesNotExist());
    }

    @Test
    void oversizedBodyIsRejected() throws Exception {
        String body = "x".repeat(4001);

        mvc.perform(
                        post("/api/announcements")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"title\":\"A\",\"body\":\"" + body + "\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").doesNotExist());
    }

    @Test
    void malformedJsonIsRejectedWithoutTheLegacyEnvelope() throws Exception {
        mvc.perform(
                        post("/api/announcements")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"title\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").doesNotExist());
    }

    /** §2.4: publish returns 200 with the resource. */
    @Test
    void publishReturnsThePublishedResource() throws Exception {
        when(service.publish(1L)).thenReturn(announcement("A", true));

        mvc.perform(post("/api/announcements/1/publish"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.published").value(true));
    }

    /** §2.4: publishing an unknown id is the legacy 404 envelope. */
    @Test
    void publishUnknownIdIsLegacyNotFound() throws Exception {
        when(service.publish(anyLong()))
                .thenThrow(new NoSuchElementException("announcement 999999 not found"));

        mvc.perform(post("/api/announcements/999999/publish"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").value("Not Found"))
                .andExpect(jsonPath("$.message").value("announcement 999999 not found"));
    }

    /** §2.5 / §7: no delete route, and no unpublish route, are defined. */
    @Test
    void thereIsNoDeleteAndNoUnpublishRoute() throws Exception {
        mvc.perform(delete("/api/announcements/1")).andExpect(status().isMethodNotAllowed());
        mvc.perform(post("/api/announcements/1/unpublish")).andExpect(status().isNotFound());
    }
}
