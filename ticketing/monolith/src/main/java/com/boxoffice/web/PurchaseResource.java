package com.boxoffice.web;

import com.boxoffice.common.BoxOfficeException;
import com.boxoffice.common.Db;
import com.boxoffice.common.Json;
import com.boxoffice.inventory.HoldExpiryBean;
import com.boxoffice.inventory.SeatMapBean;
import com.boxoffice.reporting.ReportingBean;
import com.boxoffice.sales.OrderBean;
import com.boxoffice.sales.PurchaseFacadeBean;
import com.boxoffice.settlement.SettlementBean;
import jakarta.ejb.EJB;
import jakarta.ejb.EJBException;
import jakarta.json.JsonObject;
import jakarta.json.JsonReader;
import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.PathParam;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.QueryParam;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import java.io.StringReader;
import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Path("/")
@Produces(MediaType.APPLICATION_JSON)
public class PurchaseResource {

    @EJB
    private PurchaseFacadeBean purchases;
    @EJB
    private OrderBean orders;
    @EJB
    private SeatMapBean seatMap;
    @EJB
    private ReportingBean reporting;
    @EJB
    private SettlementBean settlement;
    @EJB
    private HoldExpiryBean holdExpiry;

    /**
     * Body: {"performanceId":1,"email":"fan00001@example.test","quantity":2,
     *        "section":"A01"?, "promoCode":?, "delivery":"MOBILE"?, "cardLast4":"4242"?}
     */
    @POST
    @Path("purchase")
    @Consumes(MediaType.APPLICATION_JSON)
    public Response purchase(String body) {
        JsonObject req;
        try (JsonReader r = jakarta.json.Json.createReader(new StringReader(body))) {
            req = r.readObject();
        } catch (RuntimeException e) {
            return error(400, "BAD_REQUEST", "invalid JSON");
        }
        try {
            Map<String, Object> result = purchases.purchase(
                    req.getJsonNumber("performanceId").longValue(),
                    req.getString("email"),
                    req.getInt("quantity", 2),
                    req.getString("section", null),
                    req.getString("promoCode", null),
                    req.getString("delivery", "MOBILE"),
                    req.getString("cardLast4", "4242"),
                    "API");
            String status = (String) result.get("status");
            int code = "CONFIRMED".equals(status) ? 201 : 402;
            return Response.status(code).entity(Json.write(result)).build();
        } catch (EJBException e) {
            Throwable cause = e.getCausedByException() != null ? e.getCausedByException() : e.getCause();
            if (cause instanceof BoxOfficeException be) {
                return fromBusiness(be);
            }
            return error(500, "ERROR", String.valueOf(cause));
        } catch (BoxOfficeException be) {
            return fromBusiness(be);
        }
    }

    @GET
    @Path("orders/{ref}")
    public Response order(@PathParam("ref") String ref) {
        Map<String, Object> o = orders.byRef(ref);
        if (o == null) {
            return error(404, "NOT_FOUND", ref);
        }
        Map<String, Object> out = new LinkedHashMap<>(o);
        out.put("items", orders.items(((Number) o.get("id")).longValue()));
        return Response.ok(Json.write(out)).build();
    }

    @GET
    @Path("performances/{id}/availability")
    public Response availability(@PathParam("id") long id) {
        return Response.ok(Json.write(seatMap.counts(id))).build();
    }

    @GET
    @Path("stats")
    public Response stats() {
        return Response.ok(Json.write(reporting.stats())).build();
    }

    @POST
    @Path("admin/settlement")
    public Response runSettlement(@QueryParam("date") String date) {
        LocalDate d = date == null ? LocalDate.now() : LocalDate.parse(date);
        List<String> summary = settlement.run(d);
        return Response.ok(Json.write(Map.of("businessDate", d.toString(), "promoters", summary))).build();
    }

    @POST
    @Path("admin/expire-holds")
    public Response expireHolds() {
        return Response.ok(Json.write(Map.of("released", holdExpiry.releaseExpired()))).build();
    }

    @GET
    @Path("health")
    public Response health() {
        long one = Db.scalarLong("SELECT 1");
        return Response.ok(Json.write(Map.of("status", one == 1 ? "UP" : "DOWN"))).build();
    }

    private static Response fromBusiness(BoxOfficeException be) {
        int status = switch (be.getCode()) {
            case "SOLD_OUT" -> 409;
            case "NOT_FOUND" -> 404;
            case "BAD_QUANTITY", "BAD_REQUEST" -> 400;
            case "HOLD_EXPIRED" -> 410;
            default -> 500;
        };
        return error(status, be.getCode(), be.getMessage());
    }

    private static Response error(int status, String code, String message) {
        return Response.status(status).entity(Json.write(Map.of("error", code, "message", message))).build();
    }
}
