package com.otterworks.legacyportal.common;

import java.io.IOException;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Marks the three bounded-context route prefixes as deprecated now that their traffic is served
 * by the extracted services (see {@code docs/migration/traffic-routing.md}).
 *
 * <p>The routes stay fully functional: this only adds the {@code Deprecation} and {@code Sunset}
 * response headers (RFC 8594 and the deprecation-header draft) and a log line. Status codes and
 * response bodies are untouched, so the parity suites still replay against this application.
 */
@Component
public class DeprecatedContextRoutesFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(DeprecatedContextRoutesFilter.class);

    /** Route prefix to the service that owns the context now. */
    private static final Map<String, String> SUCCESSORS;

    static {
        Map<String, String> successors = new LinkedHashMap<>();
        successors.put("/api/announcements", "announcements-service");
        successors.put("/api/preferences", "user-preferences-service");
        successors.put("/api/feedback", "feedback-service");
        SUCCESSORS = Collections.unmodifiableMap(successors);
    }

    /** Date after which these routes may be removed, as an HTTP-date (RFC 8594 §3). */
    static final String SUNSET = "Wed, 31 Mar 2027 00:00:00 GMT";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String path = request.getRequestURI();
        for (Map.Entry<String, String> successor : SUCCESSORS.entrySet()) {
            if (path.equals(successor.getKey()) || path.startsWith(successor.getKey() + "/")) {
                response.setHeader("Deprecation", "true");
                response.setHeader("Sunset", SUNSET);
                log.warn(
                        "Deprecated monolith route served: {} {} — this context is owned by {};"
                                + " the caller is still pointed at the monolith",
                        request.getMethod(),
                        path,
                        successor.getValue());
                break;
            }
        }
        chain.doFilter(request, response);
    }
}
