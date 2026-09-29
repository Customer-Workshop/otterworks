package com.boxoffice.inventory;

import com.boxoffice.common.AuditLog;
import com.boxoffice.common.Db;
import jakarta.ejb.EJB;
import jakarta.ejb.Schedule;
import jakarta.ejb.Stateless;
import java.util.List;
import java.util.Map;
import java.util.logging.Logger;

/** Sweeps expired holds every minute and returns their seats to sale. */
@Stateless
public class HoldExpiryBean {

    private static final Logger LOG = Logger.getLogger(HoldExpiryBean.class.getName());

    @EJB
    private SeatHoldBean holds;

    @Schedule(hour = "*", minute = "*", second = "0", persistent = false, info = "hold-expiry")
    public void sweep() {
        int released = releaseExpired();
        if (released > 0) {
            LOG.info("released " + released + " expired holds");
        }
    }

    public int releaseExpired() {
        List<Map<String, Object>> expired = Db.query(
                "SELECT id FROM seat_holds WHERE status = 'ACTIVE' AND expires_at < now() LIMIT 500");
        for (Map<String, Object> h : expired) {
            long holdId = ((Number) h.get("id")).longValue();
            holds.release(holdId, "EXPIRED");
            // an order that never got paid dies with its hold
            Db.update("UPDATE orders SET status = 'CANCELLED', updated_at = now() WHERE hold_id = ? AND status = 'PENDING_PAYMENT'",
                    holdId);
        }
        if (!expired.isEmpty()) {
            AuditLog.record("inventory", "HOLDS_EXPIRED", null, String.valueOf(expired.size()));
        }
        return expired.size();
    }
}
