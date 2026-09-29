package com.boxoffice.payments.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import com.boxoffice.payments.SpringTestBase;
import com.boxoffice.payments.domain.DeliveryTarget;
import com.boxoffice.payments.domain.OutcomeDelivery;
import com.boxoffice.payments.events.Fixtures;
import com.boxoffice.payments.events.OrderPlaced;
import com.boxoffice.payments.repo.DeliveryRepository;
import com.boxoffice.payments.repo.PaymentRepository;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.EmbeddedKafkaBroker;

/**
 * The verify-1 failure mode: the confirmations inbox is unreachable while payments are captured. The consumer must
 * still commit its offset (payment + Kafka record are durable) and the relay must deliver once the inbox is back.
 */
class InboxRelayTest extends SpringTestBase {

    @Autowired KafkaTemplate<String, Object> kafka;
    @Autowired EmbeddedKafkaBroker broker;
    @Autowired PaymentRepository payments;
    @Autowired DeliveryRepository deliveries;
    @Autowired InboxRelay relay;

    @BeforeEach
    void reset() {
        INBOX.clear();
        INBOX_DOWN.set(false);
    }

    @AfterEach
    void inboxBackUp() {
        INBOX_DOWN.set(false);
    }

    @Test
    void unreachableInboxDoesNotBlockTheOffsetAndIsRetriedUntilDelivered() throws Exception {
        INBOX_DOWN.set(true);
        OrderPlaced placed = Fixtures.orderPlaced("BO-RELAYDOWN1", "4242", Instant.now().plusSeconds(600));
        var meta = kafka.send("tkt01-order-placed", placed.orderRef(), placed).get().getRecordMetadata();

        // the offset is committed although every POST to confirmations fails
        awaitCommitted(new TopicPartition("tkt01-order-placed", meta.partition()), meta.offset() + 1);
        assertThat(payments.findByOrderRef(placed.orderRef())).isPresent();
        await().atMost(Duration.ofSeconds(10)).untilAsserted(() -> {
            List<OutcomeDelivery> rows = deliveries.forOrder(placed.orderRef());
            assertThat(rows).hasSize(1);
            assertThat(rows.get(0).target()).isEqualTo(DeliveryTarget.CONFIRMATIONS);
            assertThat(rows.get(0).pending()).isTrue();
            assertThat(rows.get(0).attempts()).as("retried with backoff").isGreaterThanOrEqualTo(2);
        });
        assertThat(INBOX).extracting(InboxCall::path).doesNotContain("/confirmations/events/payment-captured");
        assertThat(payments.stats().deliveriesPending()).isGreaterThanOrEqualTo(1);

        // the inbox comes back: the pending row is delivered with the original payload and cleared
        INBOX_DOWN.set(false);
        await().atMost(Duration.ofSeconds(10)).untilAsserted(() ->
                assertThat(INBOX).extracting(InboxCall::path).contains("/confirmations/events/payment-captured"));
        InboxCall call = INBOX.stream().filter(c -> c.path().endsWith("/events/payment-captured")).findFirst().orElseThrow();
        assertThat(Fixtures.JSON.readTree(call.body()).get("orderRef").asText()).isEqualTo(placed.orderRef());
        await().atMost(Duration.ofSeconds(10)).untilAsserted(() -> {
            OutcomeDelivery row = deliveries.forOrder(placed.orderRef()).get(0);
            assertThat(row.deliveredAt()).isNotNull();
            assertThat(row.givenUpAt()).isNull();
        });
    }

    @Test
    void redeliveredRecordEnqueuesNothingTwice() throws Exception {
        OrderPlaced placed = Fixtures.orderPlaced("BO-RELAYDUP01", "0000", Instant.now().plusSeconds(600));
        kafka.send("tkt01-order-placed", placed.orderRef(), placed).get();
        var meta = kafka.send("tkt01-order-placed", placed.orderRef(), placed).get().getRecordMetadata();
        awaitCommitted(new TopicPartition("tkt01-order-placed", meta.partition()), meta.offset() + 1);

        await().atMost(Duration.ofSeconds(10)).untilAsserted(() -> assertThat(INBOX).extracting(InboxCall::path)
                .contains("/orders/events/payment-failed", "/seats/events/payment-failed"));
        assertThat(deliveries.forOrder(placed.orderRef())).extracting(OutcomeDelivery::target)
                .containsExactlyInAnyOrder(DeliveryTarget.ORDERS, DeliveryTarget.SEATS);
        await().atMost(Duration.ofSeconds(10)).untilAsserted(() ->
                assertThat(deliveries.forOrder(placed.orderRef())).noneMatch(OutcomeDelivery::pending));
        assertThat(INBOX.stream().filter(c -> c.path().equals("/orders/events/payment-failed")
                && c.body().contains(placed.orderRef())).count()).isEqualTo(1);
    }

    @Test
    void backoffGrowsAndIsCapped() {
        assertThat(relay.backoff(1)).isEqualTo(Duration.ofMillis(200));
        assertThat(relay.backoff(2)).isEqualTo(Duration.ofMillis(400));
        assertThat(relay.backoff(9)).isEqualTo(Duration.ofMillis(400));
        assertThat(relay.backoff(40)).isEqualTo(Duration.ofMillis(400));
    }

    private void awaitCommitted(TopicPartition tp, long expected) {
        try (Admin admin = Admin.create(Map.of("bootstrap.servers", broker.getBrokersAsString()))) {
            await().atMost(Duration.ofSeconds(15)).untilAsserted(() -> {
                Map<TopicPartition, OffsetAndMetadata> committed =
                        admin.listConsumerGroupOffsets("tkt01-payments").partitionsToOffsetAndMetadata().get();
                assertThat(committed).containsKey(tp);
                assertThat(committed.get(tp).offset()).as("offset committed despite the inbox outage").isGreaterThanOrEqualTo(expected);
            });
        }
    }
}
