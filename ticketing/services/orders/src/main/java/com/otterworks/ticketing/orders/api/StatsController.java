package com.otterworks.ticketing.orders.api;

import com.otterworks.ticketing.orders.stats.StatsService;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatsController {

    private final StatsService stats;

    public StatsController(StatsService stats) {
        this.stats = stats;
    }

    @GetMapping({"/stats", "/api/stats"})
    public Map<String, Object> stats() {
        return stats.stats();
    }
}
