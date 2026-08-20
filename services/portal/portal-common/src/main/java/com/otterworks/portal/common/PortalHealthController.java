package com.otterworks.portal.common;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * {@code GET /health}, the plain health surface the on-prem load balancer and the compose
 * healthchecks poll. Actuator stays available at {@code /actuator/health} alongside it.
 *
 * <p>The monolith also returns a {@code banner} field sourced from a
 * {@code portal-settings.properties} file resolved against the process working directory. That
 * field is intentionally dropped: the host-file override is the finding the assessment rates
 * highest, and no extracted service reads configuration off the host filesystem.
 */
@RestController
public class PortalHealthController {

    private final String serviceName;

    public PortalHealthController(@Value("${spring.application.name}") String serviceName) {
        this.serviceName = serviceName;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        Map<String, String> body = new LinkedHashMap<>();
        body.put("status", "UP");
        body.put("service", serviceName);
        return body;
    }
}
