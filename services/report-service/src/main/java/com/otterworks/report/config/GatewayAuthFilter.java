package com.otterworks.report.config;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

import javax.servlet.Filter;
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

/**
 * Verifies that requests to protected endpoints carry the X-User-ID header
 * injected by the API gateway after JWT validation. Requests without this
 * header are rejected with 401 Unauthorized.
 */
@Component
@Order(1)
public class GatewayAuthFilter implements Filter {

    private static final Set<String> PUBLIC_PREFIXES = new HashSet<>(Arrays.asList(
        "/health", "/metrics", "/actuator", "/swagger-ui", "/swagger-resources", "/v2/api-docs"
    ));

    @Override
    public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain)
            throws IOException, ServletException {
        HttpServletRequest httpReq = (HttpServletRequest) request;
        HttpServletResponse httpRes = (HttpServletResponse) response;

        String path = httpReq.getRequestURI();
        if (isPublicPath(path)) {
            chain.doFilter(request, response);
            return;
        }

        String userId = httpReq.getHeader("X-User-ID");
        if (userId == null || userId.trim().isEmpty()) {
            httpRes.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            httpRes.setContentType("application/json");
            httpRes.getWriter().write("{\"error\":\"Authentication required\"}");
            return;
        }

        chain.doFilter(request, response);
    }

    private boolean isPublicPath(String path) {
        return PUBLIC_PREFIXES.stream().anyMatch(path::startsWith);
    }
}
