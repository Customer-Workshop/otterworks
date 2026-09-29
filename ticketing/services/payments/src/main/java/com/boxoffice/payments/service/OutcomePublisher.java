package com.boxoffice.payments.service;

import com.boxoffice.payments.config.PaymentsProperties;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

/**
 * Delivery contract for payment-captured / payment-failed: a Kafka record keyed by orderRef, acknowledged by the
 * broker before the consumer commits its offset; a failure propagates and the order-placed record is redelivered
 * (idempotent). The HTTP inbox fan-out is not on this path: it sits in outcome_deliveries (written with the
 * payment) and InboxRelay drives it, so an unreachable sibling never stalls a partition.
 */
@Component
public class OutcomePublisher {

    private final KafkaTemplate<String, Object> kafka;
    private final PaymentsProperties props;

    public OutcomePublisher(KafkaTemplate<String, Object> kafka, PaymentsProperties props) {
        this.kafka = kafka;
        this.props = props;
    }

    public void publish(OutcomeEvent event) {
        if (event.captured() != null) {
            send(props.topics().paymentCaptured(), event.orderRef(), event.captured());
        } else {
            send(props.topics().paymentFailed(), event.orderRef(), event.failed());
        }
    }

    private void send(String topic, String key, Object payload) {
        try {
            kafka.send(topic, key, payload).get(30, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new DeliveryException(topic, e);
        } catch (ExecutionException | TimeoutException e) {
            throw new DeliveryException(topic, e);
        }
    }

    public static class DeliveryException extends RuntimeException {
        public DeliveryException(String target, Throwable cause) {
            super("could not deliver outcome to " + target, cause);
        }
    }
}
