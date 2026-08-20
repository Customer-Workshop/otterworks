package com.otterworks.legacyportal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * OtterWorks Legacy Portal — the shell left after decomposition.
 *
 * <p>The three bounded contexts it used to bundle (announcements, user-preferences, feedback) are
 * served by their extracted services. What remains boots, answers {@code /health} and the actuator
 * endpoints, and owns no data; {@code docs/migration/decommission.md} is how it is switched off.
 */
@SpringBootApplication
public class LegacyPortalApplication {

    public static void main(String[] args) {
        SpringApplication.run(LegacyPortalApplication.class, args);
    }
}
