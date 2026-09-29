package com.boxoffice.confirmations;

import com.boxoffice.confirmations.config.ConfirmationsProperties;
import com.boxoffice.confirmations.config.ConsumerProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

/** Tickets and confirmation e-mails: the fulfilment context of the BoxOffice monolith as a Knative Service. */
@SpringBootApplication
@EnableConfigurationProperties({ConfirmationsProperties.class, ConsumerProperties.class})
public class ConfirmationsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfirmationsApplication.class, args);
    }
}
