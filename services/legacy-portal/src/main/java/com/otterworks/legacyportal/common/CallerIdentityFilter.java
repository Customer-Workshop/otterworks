package com.otterworks.legacyportal.common;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Requires an authenticated caller on every {@code /api/**} route.
 *
 * <p>{@code /health} and {@code /actuator/health} are liveness endpoints for the VM's process
 * supervisor and the load balancer, and stay anonymous.
 */
@Component
public class CallerIdentityFilter extends OncePerRequestFilter {

    private static final String PROTECTED_PREFIX = "/api/";

    private final ObjectMapper objectMapper;

    public CallerIdentityFilter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        if (request.getRequestURI().startsWith(PROTECTED_PREFIX) && callerId(request) == null) {
            unauthorized(response);
            return;
        }
        chain.doFilter(request, response);
    }

    private String callerId(HttpServletRequest request) {
        String header = request.getHeader(CallerIdentity.HEADER);
        if (header == null || header.trim().isEmpty()) {
            return null;
        }
        return header.trim();
    }

    private void unauthorized(HttpServletResponse response) throws IOException {
        Map<String, String> body = new LinkedHashMap<>();
        body.put("error", HttpStatus.UNAUTHORIZED.getReasonPhrase());
        body.put("message", "missing " + CallerIdentity.HEADER + " header");
        response.setStatus(HttpStatus.UNAUTHORIZED.value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        objectMapper.writeValue(response.getOutputStream(), body);
    }
}
