package com.boxoffice.confirmations.config;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * Runtime knobs. The token names the Kafka topic and the sibling services' cluster-local hosts.
 *
 * @param token           run token, e.g. {@code tkt01}
 * @param kafkaEnabled    publish order-confirmed to Kafka (tests turn this off)
 * @param topic           {@code <token>-order-confirmed}
 * @param ordersInboxUrl  orders {@code /events/order-confirmed}
 * @param seatsInboxUrl   seats {@code /events/order-confirmed}
 * @param deliveryTimeoutMs per-inbox HTTP timeout
 * @param publishTimeoutMs  wait for the Kafka ack before answering the inbox request
 */
@Validated
@ConfigurationProperties(prefix = "confirmations")
public record ConfirmationsProperties(
        @NotBlank @Pattern(regexp = "^tkt[a-z0-9]{1,12}$") String token,
        boolean kafkaEnabled,
        @NotBlank String topic,
        @NotBlank String ordersInboxUrl,
        @NotBlank String seatsInboxUrl,
        long deliveryTimeoutMs,
        long publishTimeoutMs) {
}
