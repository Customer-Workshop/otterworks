package com.boxoffice.payments.kafka;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import com.boxoffice.payments.SpringTestBase;
import com.boxoffice.payments.events.Fixtures;
import com.boxoffice.payments.events.OrderPlaced;
import com.boxoffice.payments.repo.PaymentRepository;
import com.fasterxml.jackson.databind.JsonNode;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutionException;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.utils.KafkaTestUtils;

/** End to end through the real listener: Kafka in, DB row, Kafka out, inbox POSTs, then the offset is committed. */
class OrderPlacedFlowTest extends SpringTestBase {

    @Autowired KafkaTemplate<String, Object> kafka;
    @Autowired EmbeddedKafkaBroker broker;
    @Autowired PaymentRepository repo;

    private Consumer<String, String> outcomes;

    @BeforeEach
    void subscribe() {
        Map<String, Object> props = KafkaTestUtils.consumerProps(broker.getBrokersAsString(), "flow-test-" + System.nanoTime(), "true");
        outcomes = new DefaultKafkaConsumerFactory<>(props, new StringDeserializer(), new StringDeserializer()).createConsumer();
        broker.consumeFromEmbeddedTopics(outcomes, "tkt01-payment-captured", "tkt01-payment-failed");
        INBOX.clear();
    }

    @AfterEach
    void close() {
        outcomes.close();
    }

    @Test
    void approvedOrderPublishesPaymentCapturedAndPostsToConfirmationsBeforeCommitting() throws Exception {
        OrderPlaced placed = Fixtures.orderPlaced("BO-FLOWOK0001", "4242", Instant.now().plusSeconds(600));
        var meta = kafka.send("tkt01-order-placed", placed.orderRef(), placed).get().getRecordMetadata();

        ConsumerRecord<String, String> rec = awaitOutcome("tkt01-payment-captured", placed.orderRef());
        JsonNode ev = Fixtures.JSON.readTree(rec.value());
        assertThat(ev.get("orderRef").asText()).isEqualTo(placed.orderRef());
        assertThat(ev.get("amountCents").asLong()).isEqualTo(42836);
        assertThat(ev.get("latencyMs").asInt()).isEqualTo(69);
        assertThat(ev.get("gatewayRef").asText()).startsWith("GW-");
        assertThat(ev.get("order").get("items")).hasSize(2);

        await().atMost(Duration.ofSeconds(10)).untilAsserted(() ->
                assertThat(INBOX).extracting(InboxCall::path).contains("/confirmations/events/payment-captured"));
        InboxCall call = INBOX.stream().filter(c -> c.path().endsWith("/events/payment-captured")).findFirst().orElseThrow();
        assertThat(Fixtures.JSON.readTree(call.body())).isEqualTo(ev);

        assertThat(repo.findByOrderRef(placed.orderRef())).isPresent();
        awaitCommitted(new TopicPartition("tkt01-order-placed", meta.partition()), meta.offset() + 1);
    }

    @Test
    void declinedOrderPublishesPaymentFailedToOrdersAndSeats() throws Exception {
        OrderPlaced placed = Fixtures.orderPlaced("BO-FLOWKO0001", "0000", Instant.now().plusSeconds(600));
        var meta = kafka.send("tkt01-order-placed", placed.orderRef(), placed).get().getRecordMetadata();

        ConsumerRecord<String, String> rec = awaitOutcome("tkt01-payment-failed", placed.orderRef());
        JsonNode ev = Fixtures.JSON.readTree(rec.value());
        assertThat(ev.get("outcome").asText()).isEqualTo("DECLINED");
        assertThat(ev.get("orderStatus").asText()).isEqualTo("PAYMENT_FAILED");
        assertThat(ev.get("holdRef").asText()).isEqualTo(placed.holdRef());
        assertThat(ev.get("gatewayRef").asText()).startsWith("GW-");

        await().atMost(Duration.ofSeconds(10)).untilAsserted(() ->
                assertThat(INBOX).extracting(InboxCall::path)
                        .contains("/orders/events/payment-failed", "/seats/events/payment-failed"));
        awaitCommitted(new TopicPartition("tkt01-order-placed", meta.partition()), meta.offset() + 1);
    }

    @Test
    void redeliveredRecordIsANoOpButTheOutcomeIsRedriven() throws Exception {
        OrderPlaced placed = Fixtures.orderPlaced("BO-FLOWDUP001", "4242", Instant.now().plusSeconds(600));
        kafka.send("tkt01-order-placed", placed.orderRef(), placed).get();
        awaitOutcome("tkt01-payment-captured", placed.orderRef());
        long duplicatesBefore = repo.stats().duplicatesSuppressed();

        var meta = kafka.send("tkt01-order-placed", placed.orderRef(), placed).get().getRecordMetadata();
        awaitOutcome("tkt01-payment-captured", placed.orderRef());

        assertThat(repo.attemptsFor(placed.orderRef())).hasSize(1);
        assertThat(repo.stats().duplicatesSuppressed()).isEqualTo(duplicatesBefore + 1);
        awaitCommitted(new TopicPartition("tkt01-order-placed", meta.partition()), meta.offset() + 1);
    }

    private ConsumerRecord<String, String> awaitOutcome(String topic, String orderRef) {
        long deadline = System.currentTimeMillis() + 30_000;
        while (System.currentTimeMillis() < deadline) {
            ConsumerRecords<String, String> polled = outcomes.poll(Duration.ofMillis(500));
            for (ConsumerRecord<String, String> r : polled) {
                if (topic.equals(r.topic()) && orderRef.equals(r.key())) {
                    return r;
                }
            }
        }
        throw new AssertionError("no " + topic + " record for " + orderRef);
    }

    private void awaitCommitted(TopicPartition tp, long expected) throws ExecutionException, InterruptedException {
        try (Admin admin = Admin.create(Map.of("bootstrap.servers", broker.getBrokersAsString()))) {
            await().atMost(Duration.ofSeconds(15)).untilAsserted(() -> {
                Map<TopicPartition, OffsetAndMetadata> committed =
                        admin.listConsumerGroupOffsets("tkt01-payments").partitionsToOffsetAndMetadata().get();
                assertThat(committed).containsKey(tp);
                assertThat(committed.get(tp).offset()).as("offset committed after DB + delivery").isGreaterThanOrEqualTo(expected);
            });
        }
        assertThat(List.of(tp)).isNotEmpty();
    }
}
