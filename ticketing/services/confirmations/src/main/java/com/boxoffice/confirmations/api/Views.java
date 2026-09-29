package com.boxoffice.confirmations.api;

import com.boxoffice.confirmations.domain.Confirmation;
import com.boxoffice.confirmations.domain.FulfilmentService;
import com.boxoffice.confirmations.domain.Ticket;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class Views {

    private Views() {
    }

    static List<Map<String, Object>> tickets(List<Ticket> tickets) {
        return tickets.stream().map(t -> {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("ticketCode", t.ticketCode());
            m.put("seatInventoryId", t.seatInventoryId());
            m.put("barcode", t.barcode());
            m.put("issuedAt", FulfilmentService.iso(t.issuedAt()));
            return m;
        }).toList();
    }

    static Map<String, Object> confirmation(Confirmation c) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("channel", c.channel());
        m.put("recipient", c.recipient());
        m.put("subject", c.subject());
        m.put("body", c.body());
        m.put("status", c.status());
        m.put("sentAt", FulfilmentService.iso(c.sentAt()));
        m.put("createdAt", FulfilmentService.iso(c.createdAt()));
        return m;
    }
}
