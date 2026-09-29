package com.boxoffice.confirmations.events;

import com.boxoffice.confirmations.config.ConfirmationsProperties;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(prefix = "confirmations", name = "kafka-enabled", havingValue = "true", matchIfMissing = true)
public class KafkaOrderConfirmedPublisher implements OrderConfirmedPublisher {

    private static final Logger log = LoggerFactory.getLogger(KafkaOrderConfirmedPublisher.class);

    private final KafkaTemplate<String, String> kafka;
    private final ObjectMapper json;
    private final ConfirmationsProperties props;
    private final Counter published;
    private final Counter failed;

    public KafkaOrderConfirmedPublisher(KafkaTemplate<String, String> kafka, ObjectMapper json,
                                        ConfirmationsProperties props, MeterRegistry registry) {
        this.kafka = kafka;
        this.json = json;
        this.props = props;
        this.published = registry.counter("confirmations_order_confirmed_published_total");
        this.failed = registry.counter("confirmations_order_confirmed_publish_failures_total");
    }

    @Override
    public String publish(OrderConfirmedEvent event) {
        String topic = props.topic();
        try {
            String payload = json.writeValueAsString(event);
            SendResult<String, String> result = kafka.send(topic, event.orderRef(), payload)
                    .get(props.publishTimeoutMs(), TimeUnit.MILLISECONDS);
            published.increment();
            log.info("published order-confirmed orderRef={} topic={} partition={} offset={}", event.orderRef(), topic,
                    result.getRecordMetadata().partition(), result.getRecordMetadata().offset());
            return topic;
        } catch (JsonProcessingException e) {
            failed.increment();
            throw new DeliveryException("kafka", "cannot serialise order-confirmed", e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            failed.increment();
            throw new DeliveryException("kafka", "interrupted while publishing", e);
        } catch (ExecutionException | TimeoutException e) {
            failed.increment();
            throw new DeliveryException("kafka", "broker did not ack " + topic + " within " + props.publishTimeoutMs() + "ms", e);
        }
    }
}
