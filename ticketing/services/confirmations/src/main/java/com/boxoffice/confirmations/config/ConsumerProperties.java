package com.boxoffice.confirmations.config;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * The payment-captured consumer. Enabled only in the KEDA-scaled consumer Deployment ({@code KAFKA_CONSUMER_ENABLED=true});
 * the request-driven Knative revision and the tests keep it off.
 *
 * @param enabled start the {@code <token>-payment-captured} listener
 * @param topic   {@code <token>-payment-captured}
 */
@Validated
@ConfigurationProperties(prefix = "confirmations.consumer")
public record ConsumerProperties(boolean enabled, @NotBlank String topic) {
}
