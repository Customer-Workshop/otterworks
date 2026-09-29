package com.otterworks.ticketing.orders;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.otterworks.ticketing.orders.outbox.OutboxRelay;
import com.otterworks.ticketing.orders.outbox.OutboxRepository;
import com.otterworks.ticketing.orders.support.IntegrationTestBase;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

/** The relay role: publishes unpublished rows in id order to {@code <token>-<event-name>} and stamps published_at. */
@TestPropertySource(properties = {"orders.relay.enabled=true", "orders.relay.poll-interval=1h"})
class OutboxRelayIT extends IntegrationTestBase {

    @MockitoBean
    KafkaTemplate<String, String> kafka;
    @Autowired
    OutboxRelay relay;
    @Autowired
    OutboxRepository outbox;

    @Test
    void publishesInIdOrderWithOrderRefKeyAndMarksPublished() {
        long a = outbox.append("BO-RELAY000001", "order-placed", "BO-RELAY000001", "{\"orderRef\":\"BO-RELAY000001\"}");
        long b = outbox.append("BO-RELAY000002", "order-placed", "BO-RELAY000002", "{\"orderRef\":\"BO-RELAY000002\"}");
        when(kafka.send(anyString(), anyString(), anyString()))
                .thenAnswer(inv -> CompletableFuture.completedFuture(new SendResult<>(
                        new ProducerRecord<>(inv.getArgument(0), inv.getArgument(1), inv.getArgument(2)), null)));

        int published = relay.drainBatch(100);

        assertThat(published).isGreaterThanOrEqualTo(2);
        InOrder inOrder = Mockito.inOrder(kafka);
        inOrder.verify(kafka).send(eq("test-order-placed"), eq("BO-RELAY000001"), eq("{\"orderRef\": \"BO-RELAY000001\"}"));
        inOrder.verify(kafka).send(eq("test-order-placed"), eq("BO-RELAY000002"), eq("{\"orderRef\": \"BO-RELAY000002\"}"));
        assertThat(jdbc.sql("SELECT count(*) FROM outbox WHERE id IN (:a, :b) AND published_at IS NOT NULL")
                .param("a", a).param("b", b).query(Long.class).single()).isEqualTo(2);
        assertThat(outbox.countUnpublished()).isZero();
        assertThat(relay.drainBatch(100)).isZero();
    }

    @Test
    void failedPublishLeavesRowsUnpublishedForRetry() {
        long id = outbox.append("BO-RELAYFAIL01", "order-placed", "BO-RELAYFAIL01", "{}");
        when(kafka.send(anyString(), anyString(), anyString()))
                .thenReturn(CompletableFuture.failedFuture(new RuntimeException("broker down")));

        assertThat(relay.drainBatch(100)).isZero();

        ArgumentCaptor<String> topic = ArgumentCaptor.forClass(String.class);
        verify(kafka, Mockito.atLeastOnce()).send(topic.capture(), anyString(), anyString());
        assertThat(topic.getAllValues()).containsOnly("test-order-placed");
        assertThat(jdbc.sql("SELECT published_at IS NULL FROM outbox WHERE id = :id").param("id", id)
                .query(Boolean.class).single()).isTrue();
        List<OutboxRepository.OutboxRow> rows = outbox.lockUnpublished(10);
        assertThat(rows).extracting(OutboxRepository.OutboxRow::id).contains(id);
    }
}
