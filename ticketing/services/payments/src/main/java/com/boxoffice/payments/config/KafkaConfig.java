package com.boxoffice.payments.config;

import java.util.Collection;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.config.ContainerCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.listener.ConcurrentMessageListenerContainer;
import org.springframework.kafka.listener.ConsumerAwareRebalanceListener;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

/**
 * Manual offset commit is configured in application.yml (enable.auto.commit=false, ack-mode manual_immediate).
 * A record whose side effects could not be delivered is retried on the same partition without limit, so it is
 * never skipped or lost; the idempotency key makes every retry a no-op on the database.
 */
@Configuration
public class KafkaConfig {

    private static final Logger log = LoggerFactory.getLogger(KafkaConfig.class);

    @Bean
    DefaultErrorHandler kafkaErrorHandler() {
        DefaultErrorHandler handler = new DefaultErrorHandler(
                (record, ex) -> log.error("giving up on {}-{}@{}", record.topic(), record.partition(), record.offset(), ex),
                new FixedBackOff(2000L, FixedBackOff.UNLIMITED_ATTEMPTS));
        handler.setCommitRecovered(false);
        return handler;
    }

    /**
     * Commit the initial position of every newly assigned partition so the consumer group has a committed offset
     * from the first poll on. KEDA's kafka scaler treats a partition without a committed offset as lag, which
     * would pin the deployment at one replica forever; with a committed offset it can scale to zero.
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
