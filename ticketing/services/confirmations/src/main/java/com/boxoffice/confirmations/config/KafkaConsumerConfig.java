package com.boxoffice.confirmations.config;

import java.util.Collection;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ContainerCustomizer;
import org.springframework.kafka.listener.ConcurrentMessageListenerContainer;
import org.springframework.kafka.listener.ConsumerAwareRebalanceListener;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

/**
 * Consumer-side wiring for the payment-captured listener (manual commit is configured in application.yml:
 * enable.auto.commit=false, ack-mode manual_immediate). Mirrors the payments consumer so both KEDA-scaled
 * consumers behave the same way.
 */
@Configuration
@ConditionalOnProperty(prefix = "confirmations.consumer", name = "enabled", havingValue = "true")
public class KafkaConsumerConfig {

    private static final Logger log = LoggerFactory.getLogger(KafkaConsumerConfig.class);

    /** A record whose side effects could not be delivered is retried on its partition without limit: never skipped, never lost. */
    @Bean
    DefaultErrorHandler kafkaErrorHandler() {
        DefaultErrorHandler handler = new DefaultErrorHandler(
                (record, ex) -> log.error("giving up on {}-{}@{}", record.topic(), record.partition(), record.offset(), ex),
                new FixedBackOff(2000L, FixedBackOff.UNLIMITED_ATTEMPTS));
        handler.setCommitRecovered(false);
        return handler;
    }

    /**
     * Commit the initial position of every newly assigned partition that has no committed offset yet. KEDA's kafka
     * scaler counts a partition without a committed offset as lag, which would pin the consumer at one replica;
     * with a committed offset it scales back to zero.
     */
    @Bean
    ContainerCustomizer<Object, Object, ConcurrentMessageListenerContainer<Object, Object>> commitOnAssign() {
        return container -> container.getContainerProperties().setConsumerRebalanceListener(new ConsumerAwareRebalanceListener() {
            @Override
            public void onPartitionsAssigned(Consumer<?, ?> consumer, Collection<TopicPartition> partitions) {
                Map<TopicPartition, OffsetAndMetadata> initial = new HashMap<>();
                for (TopicPartition tp : partitions) {
                    if (consumer.committed(Set.of(tp)).get(tp) == null) {
                        initial.put(tp, new OffsetAndMetadata(consumer.position(tp)));
                    }
                }
                if (!initial.isEmpty()) {
                    consumer.commitSync(initial);
                    log.info("committed initial offsets for {}", initial.keySet());
                }
            }
        });
    }
}
