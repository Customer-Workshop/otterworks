package com.otterworks.report;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * OtterWorks Report Service — generates PDF, CSV, and Excel reports
 * from analytics and audit data.
 *
 * Runs on Java 17 / Spring Boot 3.5.
 *
 * REMAINING TECH DEBT (not part of the Java 17 / Boot 3 upgrade):
 * - java.util.Date usage (target: java.time.*)
 * - RestTemplate (target: WebClient or RestClient)
 * - iText 5 (AGPL licence; iText 7 is a different licence and API)
 */
@SpringBootApplication
@EnableScheduling
@EnableAsync
public class ReportApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReportApplication.class, args);
    }
}
