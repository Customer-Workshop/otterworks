package com.otterworks.portal.common;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.NoSuchElementException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

/**
 * Pins the two error envelopes and the health body for every service that inherits
 * portal-common. If a change here goes red, extraction parity is broken for all three
 * contexts at once.
 */
@SpringBootTest(properties = "spring.application.name=portal-common-test")
@AutoConfigureMockMvc
class PortalCommonWireTest {

    @Autowired private MockMvc mvc;

    @Test
    void healthReportsServiceName() throws Exception {
        mvc.perform(get("/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.service").value("portal-common-test"))
                .andExpect(jsonPath("$.banner").doesNotExist());
    }

    @Test
    void notFoundUsesLegacyEnvelope() throws Exception {
        mvc.perform(get("/probe/missing"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").value("Not Found"))
                .andExpect(jsonPath("$.message").value("thing 7 not found"))
                .andExpect(jsonPath("$.timestamp").doesNotExist());
    }

    /** Conversion failures reach the IllegalArgumentException handler by cause unwrapping. */
    @Test
    void typeMismatchUsesLegacyEnvelopeWithConverterMessage() throws Exception {
        mvc.perform(get("/probe/number/abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("Bad Request"))
                .andExpect(jsonPath("$.message").value("For input string: \"abc\""));
    }

    /**
     * The advice must not swallow framework exceptions — 405 has to stay Spring's own, so the
     * default envelope survives. MockMvc does not run the error dispatch, so only the status is
     * asserted here; the envelope body itself is asserted by the per-service parity suites,
     * which replay against a running server.
     */
    @Test
    void unmappedMethodIsNotCapturedByTheAdvice() throws Exception {
        mvc.perform(delete("/probe/missing")).andExpect(status().isMethodNotAllowed());
    }

    @SpringBootApplication
    static class TestApp {

        @RestController
        static class ProbeController {

            @GetMapping("/probe/missing")
            String missing() {
                throw new NoSuchElementException("thing 7 not found");
            }

            @GetMapping("/probe/number/{id}")
            String number(@PathVariable long id) {
                return Long.toString(id);
            }
        }
    }
}
