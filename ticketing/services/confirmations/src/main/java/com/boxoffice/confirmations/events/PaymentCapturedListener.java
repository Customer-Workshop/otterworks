package com.boxoffice.confirmations.events;

import com.boxoffice.confirmations.domain.FulfilmentService;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.util.Set;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

/**
 * {@code <token>-payment-captured} consumer, group {@code <token>-confirmations}: the durable path that survives
 * this service being unschedulable while payments keeps capturing. Runs only where
 * {@code confirmations.consumer.enabled=true} (the KEDA-scaled consumer Deployment). The offset is committed
 * manually after tickets and the confirmation are committed and order-confirmed has been delivered; a record that
 * cannot be delivered is retried on its partition (see {@link com.boxoffice.confirmations.config.KafkaConsumerConfig})
 * and the {@code order_ref} unique key makes every retry, and every redelivery after a rebalance, a no-op.
 */
@Component
@ConditionalOnProperty(prefix = "confirmations.consumer", name = "enabled", havingValue = "true")
public class PaymentCapturedListener {

    private static final Logger log = LoggerFactory.getLogger(PaymentCapturedListener.class);

    private final FulfilmentService fulfilment;
    private final Validator validator;
    private final Counter skipped;

    public PaymentCapturedListener(FulfilmentService fulfilment, Validator validator, MeterRegistry registry) {
        this.fulfilment = fulfilment;
        this.validator = validator;
        this.skipped = registry.counter("confirmations_consumer_records_total", "outcome", "skipped");
    }

    @KafkaListener(topics = "${confirmations.consumer.topic}", groupId = "${spring.kafka.consumer.group-id}")
    public void onPaymentCaptured(ConsumerRecord<String, PaymentCapturedEvent> record, Acknowledgment ack) {
        PaymentCapturedEvent event = record.value();
        if (event == null) {
            log.warn("skipping undecodable payment-captured at {}-{}@{}", record.topic(), record.partition(), record.offset());
            skipped.increment();
            ack.acknowledge();
            return;
        }
        Set<ConstraintViolation<PaymentCapturedEvent>> violations = validator.validate(event);
        if (!violations.isEmpty()) {
            log.warn("skipping invalid payment-captured orderRef={} at {}-{}@{}: {}", event.orderRef(), record.topic(),
                    record.partition(), record.offset(), violations.iterator().next().getPropertyPath() + " " + violations.iterator().next().getMessage());
            skipped.increment();
            ack.acknowledge();
            return;
        }
        FulfilmentService.Outcome out = fulfilment.onPaymentCapturedRecord(event);
        log.debug("consumed payment-captured orderRef={} replay={} topic={} at {}-{}@{}", event.orderRef(), out.replay(),
                out.topic(), record.topic(), record.partition(), record.offset());
        ack.acknowledge();
    }
}
