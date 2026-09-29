package com.otterworks.ticketing.seats.api;

import com.otterworks.ticketing.seats.domain.Dtos.Availability;
import com.otterworks.ticketing.seats.domain.Dtos.HoldCreated;
import com.otterworks.ticketing.seats.domain.Dtos.HoldRequest;
import com.otterworks.ticketing.seats.domain.Dtos.HoldView;
import com.otterworks.ticketing.seats.domain.Dtos.SweepResult;
import com.otterworks.ticketing.seats.domain.HoldService;
import com.otterworks.ticketing.seats.domain.SeatsException;
import com.otterworks.ticketing.seats.domain.SweepService;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HoldsController {

    private final HoldService holds;
    private final SweepService sweep;

    public HoldsController(HoldService holds, SweepService sweep) {
        this.holds = holds;
        this.sweep = sweep;
    }

    @PostMapping("/api/holds")
    public ResponseEntity<HoldCreated> hold(@RequestBody HoldRequest req) {
        return ResponseEntity.status(HttpStatus.CREATED).body(holds.hold(req));
    }

    @GetMapping("/api/holds/{holdRef}")
    public HoldView get(@PathVariable String holdRef) {
        return holds.get(holdRef);
    }

    /** Optional extension for orders: attach the order reference so hold-expired can carry it. */
    @PostMapping("/api/holds/{holdRef}/order")
    public Map<String, Object> attachOrder(@PathVariable String holdRef, @RequestBody Map<String, String> body) {
        String orderRef = body == null ? null : body.get("orderRef");
        if (orderRef == null || orderRef.isBlank()) {
            throw SeatsException.badRequest("orderRef is required");
        }
        boolean attached = holds.attachOrder(holdRef, orderRef);
        return Map.of("holdRef", holdRef, "orderRef", orderRef, "attached", attached);
    }

    @GetMapping("/api/performances/{id}/availability")
    public Availability availability(@PathVariable long id) {
        return holds.availability(id);
    }

    @PostMapping({"/api/holds/sweep", "/api/admin/expire-holds"})
    public SweepResult sweep() {
        return sweep.sweep();
    }
}
