package com.otterworks.ticketing.seats.api;

import com.otterworks.ticketing.seats.domain.Dtos.Stats;
import com.otterworks.ticketing.seats.domain.HoldService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatsController {

    private final HoldService holds;

    public StatsController(HoldService holds) {
        this.holds = holds;
    }

    @GetMapping({"/stats", "/api/stats"})
    public Stats stats() {
        return holds.stats();
    }
}
