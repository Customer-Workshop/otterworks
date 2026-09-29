package com.boxoffice.payments;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * One shared context for every Spring test: H2 (PostgreSQL mode) migrated by Flyway, an embedded 6-partition
 * Kafka, and a stub HTTP inbox standing in for the confirmations / orders / seats services.
 */
@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureObservability
@ActiveProfiles("test")
@EmbeddedKafka(partitions = 6, topics = {"tkt01-order-placed", "tkt01-payment-captured", "tkt01-payment-failed"})
public abstract class SpringTestBase {

    public record InboxCall(String path, String body) {
    }

    protected static final List<InboxCall> INBOX = new CopyOnWriteArrayList<>();
    private static HttpServer inbox;

    @BeforeAll
    static void startInbox() throws IOException {
        if (inbox == null) {
            inbox = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            inbox.createContext("/", exchange -> {
                try (InputStream in = exchange.getRequestBody()) {
                    INBOX.add(new InboxCall(exchange.getRequestURI().getPath(), new String(in.readAllBytes(), StandardCharsets.UTF_8)));
                }
                exchange.sendResponseHeaders(202, -1);
                exchange.close();
            });
            inbox.start();
        }
    }

    @AfterAll
    static void keepInboxForSharedContext() {
        // the Spring context (and its inbox URLs) is cached across test classes, so the stub stays up for the JVM
    }

    @DynamicPropertySource
    static void inboxUrls(DynamicPropertyRegistry registry) throws IOException {
        startInbox();
        String base = "http://127.0.0.1:" + inbox.getAddress().getPort();
        registry.add("payments.inbox.confirmations-url", () -> base + "/confirmations");
        registry.add("payments.inbox.orders-url", () -> base + "/orders");
        registry.add("payments.inbox.seats-url", () -> base + "/seats");
    }
}
