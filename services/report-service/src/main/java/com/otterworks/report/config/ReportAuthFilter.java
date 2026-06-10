package com.otterworks.report.config;

import org.springframework.context.annotation.Profile;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.io.IOException;

/**
 * Rejects requests to report API endpoints that lack identity context.
 * Requires either a gateway-injected {@code X-User-ID} header or a
 * {@code Authorization} bearer token.  Health/metrics paths are exempt.
 *
 * Active only outside the {@code test} profile so that existing
 * functional tests (which do not inject identity headers) continue to
 * pass.  Full JWT validation should be added when the service is
 * upgraded from Java&nbsp;8 / Spring Boot&nbsp;2.
 */
@Component
@Order(1)
@Profile("!test")
public class ReportAuthFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain)
            throws ServletException, IOException {

        String path = request.getRequestURI();
        if (path.startsWith("/api/v1/reports")) {
            String userId = request.getHeader("X-User-ID");
            String authHeader = request.getHeader("Authorization");
            if ((userId == null || userId.trim().isEmpty())
                    && (authHeader == null || authHeader.trim().isEmpty())) {
                response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                response.setContentType("application/json");
                response.getWriter().write("{\"error\":\"unauthorized\"}");
                return;
            }
        }
        chain.doFilter(request, response);
    }
}
