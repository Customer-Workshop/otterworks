package com.boxoffice.payments.web;

import com.boxoffice.payments.domain.Payment;
import com.boxoffice.payments.domain.PaymentStats;
import com.boxoffice.payments.repo.PaymentRepository;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PaymentsController {

    public record AttemptView(int attemptNo, String outcome, int latencyMs) {
    }

    public record PaymentView(String orderRef, String status, long amountCents, String gatewayRef, String cardLast4,
                              List<AttemptView> attempts) {
    }

    private final PaymentRepository repo;

    public PaymentsController(PaymentRepository repo) {
        this.repo = repo;
    }

    @GetMapping("/api/payments/{orderRef}")
    public ResponseEntity<PaymentView> payment(@PathVariable String orderRef) {
        return repo.findByOrderRef(orderRef)
                .map(this::view)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.status(HttpStatus.NOT_FOUND).build());
    }

    @GetMapping("/stats")
    public PaymentStats stats() {
        return repo.stats();
    }

    private PaymentView view(Payment p) {
        List<AttemptView> attempts = repo.attemptsFor(p.orderRef()).stream()
                .map(a -> new AttemptView(a.attemptNo(), a.outcome(), a.latencyMs()))
                .toList();
        return new PaymentView(p.orderRef(), p.status().name(), p.amountCents(), p.gatewayRef(), p.cardLast4(), attempts);
    }
}
