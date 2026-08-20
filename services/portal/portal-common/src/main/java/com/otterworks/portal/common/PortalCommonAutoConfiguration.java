package com.otterworks.portal.common;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

/**
 * Registers the shared error envelope and health endpoint automatically, so a service only
 * depends on {@code portal-common} and scans its own package. Children must not re-declare
 * these beans and must not add a second {@code @ControllerAdvice}.
 */
@AutoConfiguration
public class PortalCommonAutoConfiguration {

    @Bean
    public PortalExceptionHandler portalExceptionHandler() {
        return new PortalExceptionHandler();
    }

    @Bean
    public PortalHealthController portalHealthController(
            @Value("${spring.application.name}") String serviceName) {
        return new PortalHealthController(serviceName);
    }
}
