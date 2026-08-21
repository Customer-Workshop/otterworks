package com.otterworks.feedback;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * OtterWorks Feedback Service — the feedback bounded context extracted out of the legacy-portal
 * modular monolith. It owns the {@code feedback} schema exclusively.
 */
@SpringBootApplication
public class FeedbackServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(FeedbackServiceApplication.class, args);
    }
}
