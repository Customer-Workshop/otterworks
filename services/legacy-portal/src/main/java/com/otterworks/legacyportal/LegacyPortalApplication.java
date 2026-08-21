package com.otterworks.legacyportal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * OtterWorks Legacy Portal — a modular monolith.
 *
 * <p>Two bounded contexts (announcements, user-preferences) are bundled into a single deployable,
 * each living in its own package with its own routes and its own database schema. This is a
 * deliberate decomposition candidate: the module seams map cleanly onto future microservices — the
 * feedback context has already been extracted into services/feedback-service.
 */
@SpringBootApplication
public class LegacyPortalApplication {

    public static void main(String[] args) {
        SpringApplication.run(LegacyPortalApplication.class, args);
    }
}
