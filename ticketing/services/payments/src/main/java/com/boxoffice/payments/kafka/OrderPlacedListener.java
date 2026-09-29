package com.boxoffice.payments.kafka;

import com.boxoffice.payments.events.OrderPlaced;
import com.boxoffice.payments.service.OutcomeEvent;
import com.boxoffice.payments.service.OutcomePublisher;
import com.boxoffice.payments.service.PaymentProcessor;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

/**
 * order-placed consumer, group {@code <token>-payments}. Offsets are committed manually, only after the payment
 * transaction (payment + outbox rows) has committed and the outcome record has been acknowledged by Kafka. The HTTP
 * inbox fan-out is relayed from the outbox and never holds the partition.
 */
@Component
public class OrderPlacedListener {

    private static final Logger log = LoggerFactory.getLogger(OrderPlacedListener.class);

    private final PaymentProcessor processor;
    private final OutcomePublisher publisher;

    public OrderPlacedListener(PaymentProcessor processor, OutcomePublisher publisher) {
        this.processor = processor;
        this.publisher = publisher;
    }

    @KafkaListener(topics = "${payments.topics.order-placed}", groupId = "${spring.kafka.consumer.group-id}")
    public void onOrderPlaced(ConsumerRecord<String, OrderPlaced> record, Acknowledgment ack) {
        OrderPlaced placed = record.value();
        if (placed == null || placed.orderRef() == null || placed.orderRef().isBlank()) {
            log.warn("skipping order-placed without orderRef at {}-{}@{}", record.topic(), record.partition(), record.offset());
            ack.acknowledge();
            return;
        }
        OutcomeEvent outcome = processor.process(placed);
        publisher.publish(outcome);
        ack.acknowledge();
    }
}
