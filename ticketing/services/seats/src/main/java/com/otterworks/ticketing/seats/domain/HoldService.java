package com.otterworks.ticketing.seats.domain;

import com.otterworks.ticketing.seats.config.Refs;
import com.otterworks.ticketing.seats.config.SeatsProperties;
import com.otterworks.ticketing.seats.domain.Dtos.Availability;
import com.otterworks.ticketing.seats.domain.Dtos.HoldCreated;
import com.otterworks.ticketing.seats.domain.Dtos.HoldRequest;
import com.otterworks.ticketing.seats.domain.Dtos.HoldView;
import com.otterworks.ticketing.seats.domain.Dtos.SeatView;
import com.otterworks.ticketing.seats.domain.Dtos.Stats;
import com.otterworks.ticketing.seats.domain.Dtos.ZoneTally;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * The inventory context of the monolith (SeatHoldBean, SeatMapBean) as a service: best-available
 * holds, hold lookup, availability counts, release/convert transitions and reconciliation counts.
 */
@Service
public class HoldService {

    static final List<String> HOLD_STATUSES = List.of("ACTIVE", "CONVERTED", "EXPIRED", "RELEASED");

    private static final RowMapper<SeatView> SEAT_VIEW = (rs, i) -> new SeatView(
            rs.getLong("seat_inventory_id"), rs.getString("section"), rs.getString("row_label"),
            rs.getInt("seat_number"), rs.getLong("price_zone_id"), rs.getString("zone_code"), rs.getString("zone_name"));

    private static final String SEAT_VIEW_SQL = """
            SELECT si.id AS seat_inventory_id, vs.code AS section, s.row_label, s.seat_number,
                   s.price_zone_id, pz.code AS zone_code, pz.name AS zone_name
            FROM seat_hold_items hi
            JOIN seat_inventory si ON si.id = hi.seat_inventory_id
            JOIN seats s ON s.id = si.seat_id
            JOIN venue_sections vs ON vs.id = s.section_id
            JOIN price_zones pz ON pz.id = s.price_zone_id
            WHERE hi.hold_id = ? ORDER BY vs.code, s.row_label, s.seat_number""";

    private final JdbcTemplate jdbc;
    private final SeatsProperties props;
    private final Counter holdsCreated;
    private final Counter holdsSoldOut;
    private final Counter holdsReleased;
    private final Counter holdsConverted;

    public HoldService(JdbcTemplate jdbc, SeatsProperties props, MeterRegistry registry) {
        this.jdbc = jdbc;
        this.props = props;
        this.holdsCreated = registry.counter("seats_holds_placed_total");
        this.holdsSoldOut = registry.counter("seats_holds_sold_out_total");
        this.holdsReleased = registry.counter("seats_holds_released_total");
        this.holdsConverted = registry.counter("seats_holds_converted_total");
    }

    /** SeatHoldBean.hold: validate, lock best-available rows, mark HELD, then tally per zone in the same tx. */
    @Transactional
    public HoldCreated hold(HoldRequest req) {
        if (req == null || req.performanceId() == null) {
            throw SeatsException.badRequest("performanceId is required");
        }
        long performanceId = req.performanceId();
        Integer max;
        try {
            max = jdbc.queryForObject("SELECT max_per_order FROM performances WHERE id = ?", Integer.class, performanceId);
        } catch (EmptyResultDataAccessException e) {
            max = null;
        }
        if (max == null) {
            throw SeatsException.notFound("performance " + performanceId + " not found");
        }
        int quantity = req.quantity() == null ? 2 : req.quantity();
        if (quantity < 1 || quantity > max) {
            throw SeatsException.badQuantity("quantity must be 1.." + max);
        }
        String section = req.section() == null || req.section().isBlank() ? null : req.section().trim();
        String sql = """
                SELECT si.id FROM seat_inventory si
                JOIN seats s ON s.id = si.seat_id
                JOIN venue_sections vs ON vs.id = s.section_id
                WHERE si.performance_id = ? AND si.status = 'AVAILABLE'
                """ + (section == null ? "" : " AND vs.code = ? ") + """
                ORDER BY vs.code, s.row_label, s.seat_number
                LIMIT ? FOR UPDATE OF si SKIP LOCKED""";
        List<Long> seatIds = section == null
                ? jdbc.queryForList(sql, Long.class, performanceId, quantity)
                : jdbc.queryForList(sql, Long.class, performanceId, section, quantity);
        if (seatIds.size() < quantity) {
            holdsSoldOut.increment();
            throw SeatsException.soldOut("not enough seats available");
        }
        Instant expires = Instant.now().plusSeconds(props.holdMinutes() * 60L);
        String ref = Refs.next("H");
        String email = req.customerEmail() == null || req.customerEmail().isBlank()
                ? null : req.customerEmail().trim().toLowerCase();
        Long holdId = jdbc.queryForObject("""
                INSERT INTO seat_holds (hold_ref, performance_id, customer_email, status, expires_at)
                VALUES (?, ?, ?, 'ACTIVE', ?) RETURNING id""", Long.class, ref, performanceId, email, Timestamp.from(expires));
        for (Long siId : seatIds) {
            jdbc.update("UPDATE seat_inventory SET status = 'HELD', hold_id = ?, updated_at = now() WHERE id = ?", holdId, siId);
            jdbc.update("INSERT INTO seat_hold_items (hold_id, seat_inventory_id) VALUES (?, ?)", holdId, siId);
        }
        holdsCreated.increment();
        return new HoldCreated(ref, performanceId, expires, seats(holdId), zoneTally(performanceId));
    }

    /** What PricingBean.demandFactors counted per zone (not-available vs total), after the hold. */
    List<ZoneTally> zoneTally(long performanceId) {
        return jdbc.query("""
                SELECT s.price_zone_id,
                       COUNT(*) FILTER (WHERE si.status <> 'AVAILABLE') AS not_available,
                       COUNT(*) AS total
                FROM seat_inventory si JOIN seats s ON s.id = si.seat_id
                WHERE si.performance_id = ?
                GROUP BY s.price_zone_id ORDER BY s.price_zone_id""",
                (rs, i) -> new ZoneTally(rs.getLong("price_zone_id"), rs.getLong("not_available"), rs.getLong("total")),
                performanceId);
    }

    List<SeatView> seats(long holdId) {
        return jdbc.query(SEAT_VIEW_SQL, SEAT_VIEW, holdId);
    }

    @Transactional(readOnly = true)
    public HoldView get(String holdRef) {
        return findHold(holdRef).map(h -> new HoldView(h.holdRef(), h.performanceId(), h.status(),
                        "ACTIVE".equals(h.status()) && h.expiresAt().isAfter(Instant.now()),
                        h.expiresAt(), h.orderRef(), seats(h.id())))
                .orElseThrow(() -> SeatsException.notFound("hold " + holdRef + " not found"));
    }

    public record HoldRow(long id, String holdRef, long performanceId, String status, Instant expiresAt, String orderRef) {
    }

    Optional<HoldRow> findHold(String holdRef) {
        return jdbc.query("SELECT id, hold_ref, performance_id, status, expires_at, order_ref FROM seat_holds WHERE hold_ref = ?",
                (rs, i) -> new HoldRow(rs.getLong("id"), rs.getString("hold_ref"), rs.getLong("performance_id"),
                        rs.getString("status"), rs.getTimestamp("expires_at").toInstant(), rs.getString("order_ref")),
                holdRef).stream().findFirst();
    }

    Optional<HoldRow> lockHold(String holdRef) {
        return jdbc.query("SELECT id, hold_ref, performance_id, status, expires_at, order_ref FROM seat_holds WHERE hold_ref = ? FOR UPDATE",
                (rs, i) -> new HoldRow(rs.getLong("id"), rs.getString("hold_ref"), rs.getLong("performance_id"),
                        rs.getString("status"), rs.getTimestamp("expires_at").toInstant(), rs.getString("order_ref")),
                holdRef).stream().findFirst();
    }

    /** SeatMapBean.counts: the legacy availability shape. Unknown performance → zeros, as the monolith. */
    @Transactional(readOnly = true)
    public Availability availability(long performanceId) {
        return jdbc.queryForObject("""
                SELECT COUNT(*) FILTER (WHERE status = 'AVAILABLE') AS available,
                       COUNT(*) FILTER (WHERE status = 'HELD') AS held,
                       COUNT(*) FILTER (WHERE status = 'SOLD') AS sold
                FROM seat_inventory WHERE performance_id = ?""",
                (rs, i) -> new Availability(rs.getLong("available"), rs.getLong("held"), rs.getLong("sold")), performanceId);
    }

    /**
     * SeatHoldBean.release: HELD seats of the hold back to AVAILABLE with hold/order cleared, hold to
     * {@code newStatus} (RELEASED or EXPIRED). Only an ACTIVE hold transitions; anything else is a no-op
     * so that inbox replays and sweep/inbox races are idempotent. Empty when nothing transitioned.
     */
    @Transactional
    public Optional<List<Long>> release(String holdRef, String newStatus) {
        HoldRow h = lockHold(holdRef).orElse(null);
        if (h == null || !"ACTIVE".equals(h.status())) {
            return Optional.empty();
        }
        return Optional.of(releaseLocked(h.id(), newStatus));
    }

    List<Long> releaseLocked(long holdId, String newStatus) {
        List<Long> ids = jdbc.queryForList(
                "SELECT id FROM seat_inventory WHERE hold_id = ? AND status = 'HELD' ORDER BY id", Long.class, holdId);
        jdbc.update("""
                UPDATE seat_inventory SET status = 'AVAILABLE', hold_id = NULL, order_ref = NULL, updated_at = now()
                WHERE hold_id = ? AND status = 'HELD'""", holdId);
        jdbc.update("UPDATE seat_holds SET status = ? WHERE id = ?", newStatus, holdId);
        holdsReleased.increment();
        return ids;
    }

    /** ConfirmationBean.confirm's inventory half: seats SOLD with order_ref stamped, hold CONVERTED. */
    @Transactional
    public boolean convert(String holdRef, String orderRef) {
        HoldRow h = lockHold(holdRef).orElse(null);
        if (h == null || !"ACTIVE".equals(h.status())) {
            return false;
        }
        jdbc.update("""
                UPDATE seat_inventory SET status = 'SOLD', order_ref = ?, updated_at = now()
                WHERE hold_id = ? AND status = 'HELD'""", orderRef, h.id());
        jdbc.update("UPDATE seat_holds SET status = 'CONVERTED', order_ref = ? WHERE id = ?", orderRef, h.id());
        holdsConverted.increment();
        return true;
    }

    /** Optional: orders may attach its reference to an ACTIVE hold so hold-expired carries orderRef. */
    @Transactional
    public boolean attachOrder(String holdRef, String orderRef) {
        HoldRow h = lockHold(holdRef).orElseThrow(() -> SeatsException.notFound("hold " + holdRef + " not found"));
        if (!"ACTIVE".equals(h.status())) {
            return false;
        }
        jdbc.update("UPDATE seat_holds SET order_ref = ? WHERE id = ?", orderRef, h.id());
        jdbc.update("UPDATE seat_inventory SET order_ref = ?, updated_at = now() WHERE hold_id = ? AND status = 'HELD'", orderRef, h.id());
        return true;
    }

    @Transactional(readOnly = true)
    public Stats stats() {
        Map<String, Long> byStatus = new LinkedHashMap<>();
        HOLD_STATUSES.forEach(s -> byStatus.put(s, 0L));
        jdbc.query("SELECT status, COUNT(*) AS n FROM seat_holds GROUP BY status",
                rs -> { byStatus.put(rs.getString("status"), rs.getLong("n")); });
        Availability a = jdbc.queryForObject("""
                SELECT COUNT(*) FILTER (WHERE status = 'AVAILABLE') AS available,
                       COUNT(*) FILTER (WHERE status = 'HELD') AS held,
                       COUNT(*) FILTER (WHERE status = 'SOLD') AS sold
                FROM seat_inventory""",
                (rs, i) -> new Availability(rs.getLong("available"), rs.getLong("held"), rs.getLong("sold")));
        Long inbox = jdbc.queryForObject("SELECT COUNT(*) FROM inbox", Long.class);
        Long pending = jdbc.queryForObject("""
                SELECT COUNT(*) FROM hold_expired_events
                WHERE kafka_published_at IS NULL OR orders_delivered_at IS NULL""", Long.class);
        return new Stats(a.available(), a.held(), a.sold(), byStatus,
                inbox == null ? 0 : inbox, pending == null ? 0 : pending);
    }

    List<Map<String, Object>> expiredActiveHolds(int limit) {
        List<Map<String, Object>> rows = new ArrayList<>(jdbc.queryForList("""
                SELECT id, hold_ref, performance_id, order_ref FROM seat_holds
                WHERE status = 'ACTIVE' AND expires_at < now()
                ORDER BY expires_at LIMIT ? FOR UPDATE SKIP LOCKED""", limit));
        return rows;
    }
}
