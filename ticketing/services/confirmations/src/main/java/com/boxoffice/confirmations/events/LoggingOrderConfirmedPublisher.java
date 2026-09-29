package com.boxoffice.confirmations.events;

import com.boxoffice.confirmations.config.ConfirmationsProperties;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Used when {@code confirmations.kafka-enabled=false} (tests, local runs without a broker): logs and remembers records. */
@Configuration
public class LoggingOrderConfirmedPublisher {

    private static final Logger log = LoggerFactory.getLogger(LoggingOrderConfirmedPublisher.class);

    @Bean
    @ConditionalOnMissingBean(OrderConfirmedPublisher.class)
    OrderConfirmedPublisher inMemoryPublisher(ConfirmationsProperties props) {
        return new InMemory(props.topic());
    }

    public static final class InMemory implements OrderConfirmedPublisher {

        private final String topic;
        private final List<OrderConfirmedEvent> records = new CopyOnWriteArrayList<>();

        InMemory(String topic) {
            this.topic = topic;
        }

        @Override
        public String publish(OrderConfirmedEvent event) {
            records.add(event);
            log.info("kafka disabled; order-confirmed orderRef={} would go to {}", event.orderRef(), topic);
            return topic;
        }

        public List<OrderConfirmedEvent> records() {
            return List.copyOf(records);
        }

        public void clear() {
            records.clear();
        }
    }
}
