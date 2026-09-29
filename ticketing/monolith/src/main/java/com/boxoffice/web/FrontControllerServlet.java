package com.boxoffice.web;

import com.boxoffice.catalog.EventCatalogBean;
import com.boxoffice.common.BoxOfficeException;
import com.boxoffice.customer.CustomerAccountBean;
import com.boxoffice.fulfillment.ConfirmationBean;
import com.boxoffice.inventory.SeatMapBean;
import com.boxoffice.pricing.PricingBean;
import com.boxoffice.reporting.ReportingBean;
import com.boxoffice.sales.CartBean;
import com.boxoffice.sales.OrderBean;
import com.boxoffice.sales.PurchaseFacadeBean;
import com.boxoffice.settlement.SettlementBean;
import jakarta.ejb.EJB;
import jakarta.ejb.EJBException;
import jakarta.servlet.ServletException;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import java.io.IOException;
import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.Map;
import javax.naming.InitialContext;
import javax.naming.NamingException;

/** Storefront and back office. Every page goes through here: /app/{action}. */
@WebServlet(urlPatterns = {"/app/*", ""})
public class FrontControllerServlet extends HttpServlet {

    private static final long serialVersionUID = 1L;
    private static final String CART = "boxoffice.cart";

    @EJB
    private EventCatalogBean catalog;
    @EJB
    private SeatMapBean seatMap;
    @EJB
    private CustomerAccountBean customers;
    @EJB
    private PurchaseFacadeBean purchases;
    @EJB
    private OrderBean orders;
    @EJB
    private ConfirmationBean confirmations;
    @EJB
    private SettlementBean settlement;
    @EJB
    private ReportingBean reporting;

    @Override
    protected void service(HttpServletRequest req, HttpServletResponse resp) throws ServletException, IOException {
        String action = req.getPathInfo() == null ? "home" : req.getPathInfo().substring(1);
        if (action.isEmpty()) {
            action = "home";
        }
        boolean post = "POST".equalsIgnoreCase(req.getMethod());
        try {
            String view = dispatch(action, post, req, resp);
            if (view != null) {
                req.getRequestDispatcher("/WEB-INF/jsp/" + view + ".jsp").forward(req, resp);
            }
        } catch (EJBException | BoxOfficeException e) {
            Throwable cause = e instanceof EJBException ejb && ejb.getCausedByException() != null ? ejb.getCausedByException() : e;
            if (cause instanceof BoxOfficeException be && "HOLD_EXPIRED".equals(be.getCode())) {
                resp.sendRedirect(req.getContextPath() + "/app/hold-expired");
                return;
            }
            req.setAttribute("message", cause.getMessage());
            resp.setStatus(cause instanceof BoxOfficeException ? 409 : 500);
            req.getRequestDispatcher("/WEB-INF/jsp/error.jsp").forward(req, resp);
        }
    }

    private String dispatch(String action, boolean post, HttpServletRequest req, HttpServletResponse resp) throws IOException {
        switch (action) {
            case "home" -> {
                req.setAttribute("events", catalog.onSaleEvents());
                return "index";
            }
            case "events" -> {
                String q = req.getParameter("q");
                req.setAttribute("q", q);
                req.setAttribute("events", q == null || q.isBlank() ? catalog.onSaleEvents() : catalog.search(q));
                return "events";
            }
            case "event" -> {
                long id = Long.parseLong(req.getParameter("id"));
                req.setAttribute("event", catalog.event(id));
                req.setAttribute("performers", catalog.performers(id));
                req.setAttribute("performances", catalog.performances(id));
                return "event";
            }
            case "performance" -> {
                long id = Long.parseLong(req.getParameter("id"));
                req.setAttribute("perf", catalog.performance(id));
                req.setAttribute("counts", seatMap.counts(id));
                return "performance";
            }
            case "seatmap" -> {
                long id = Long.parseLong(req.getParameter("id"));
                req.setAttribute("perf", catalog.performance(id));
                req.setAttribute("sections", seatMap.sections(id));
                return "seatmap";
            }
            case "hold" -> {
                if (!post) {
                    resp.sendError(405);
                    return null;
                }
                CartBean cart = cart(req.getSession());
                cart.holdSeats(Long.parseLong(req.getParameter("performanceId")), cart.getCustomerId(),
                        Integer.parseInt(req.getParameter("quantity")), blankToNull(req.getParameter("section")));
                resp.sendRedirect(req.getContextPath() + "/app/cart");
                return null;
            }
            case "cart" -> {
                CartBean cart = cart(req.getSession());
                if (cart.getHoldId() != null && !cart.holdActive()) {
                    resp.sendRedirect(req.getContextPath() + "/app/hold-expired");
                    return null;
                }
                req.setAttribute("hold", cart.holdRow());
                req.setAttribute("seats", cart.seats());
                req.setAttribute("quote", toMap(cart.quote()));
                return "cart";
            }
            case "checkout" -> {
                CartBean cart = cart(req.getSession());
                if (cart.getHoldId() == null || !cart.holdActive()) {
                    resp.sendRedirect(req.getContextPath() + "/app/hold-expired");
                    return null;
                }
                if (post) {
                    cart.setPromoCode(blankToNull(req.getParameter("promoCode")));
                    cart.setDeliveryCode(req.getParameter("delivery"));
                }
                req.setAttribute("hold", cart.holdRow());
                req.setAttribute("quote", toMap(cart.quote()));
                req.setAttribute("promoCode", cart.getPromoCode());
                req.setAttribute("delivery", cart.getDeliveryCode());
                return "checkout";
            }
            case "pay" -> {
                if (!post) {
                    resp.sendError(405);
                    return null;
                }
                CartBean cart = cart(req.getSession());
                long customerId = customers.findOrCreate(req.getParameter("email"), req.getParameter("fullName"));
                Map<String, Object> result = purchases.checkout(customerId, cart.getHoldId(), cart.getPromoCode(),
                        cart.getDeliveryCode(), req.getParameter("cardLast4"));
                req.getSession().removeAttribute(CART);
                String ref = (String) result.get("orderRef");
                if ("CONFIRMED".equals(result.get("status"))) {
                    resp.sendRedirect(req.getContextPath() + "/app/confirmation?ref=" + ref);
                } else {
                    resp.sendRedirect(req.getContextPath() + "/app/payment-failed?ref=" + ref);
                }
                return null;
            }
            case "confirmation" -> {
                Map<String, Object> o = orders.byRef(req.getParameter("ref"));
                req.setAttribute("order", o);
                req.setAttribute("items", o == null ? null : orders.items(((Number) o.get("id")).longValue()));
                req.setAttribute("fees", o == null ? null : orders.fees(((Number) o.get("id")).longValue()));
                return "confirmation";
            }
            case "payment-failed" -> {
                req.setAttribute("order", orders.byRef(req.getParameter("ref")));
                return "payment-failed";
            }
            case "hold-expired" -> {
                req.getSession().removeAttribute(CART);
                return "hold-expired";
            }
            case "lookup" -> {
                String ref = req.getParameter("ref");
                if (ref != null && !ref.isBlank()) {
                    Map<String, Object> o = orders.byRef(ref.trim());
                    req.setAttribute("order", o);
                    req.setAttribute("items", o == null ? null : orders.items(((Number) o.get("id")).longValue()));
                }
                req.setAttribute("ref", ref);
                return "order-lookup";
            }
            case "account" -> {
                String email = req.getParameter("email");
                if (email != null && !email.isBlank()) {
                    Map<String, Object> c = customers.byEmail(email.trim());
                    req.setAttribute("customer", c);
                    if (c != null) {
                        long cid = ((Number) c.get("id")).longValue();
                        req.setAttribute("orders", customers.orders(cid));
                        req.setAttribute("addresses", customers.addresses(cid));
                        cart(req.getSession()).setCustomerId(cid);
                    }
                }
                return "account";
            }
            case "admin" -> {
                req.setAttribute("stats", reporting.stats());
                req.setAttribute("recent", orders.recent(20));
                req.setAttribute("pendingEmails", confirmations.pendingEmails(10));
                return "admin-dashboard";
            }
            case "admin-events" -> {
                req.setAttribute("performances", catalog.allPerformances());
                req.setAttribute("venues", catalog.venues());
                return "admin-events";
            }
            case "admin-performance" -> {
                long id = Long.parseLong(req.getParameter("id"));
                if (post) {
                    catalog.updatePerformance(id, req.getParameter("status"), Integer.parseInt(req.getParameter("maxPerOrder")));
                }
                req.setAttribute("perf", catalog.performance(id));
                req.setAttribute("sections", seatMap.sections(id));
                return "admin-performance";
            }
            case "admin-settlement" -> {
                if (post) {
                    String d = req.getParameter("date");
                    req.setAttribute("runSummary", settlement.run(d == null || d.isBlank() ? LocalDate.now() : LocalDate.parse(d)));
                }
                req.setAttribute("batches", settlement.batches(30));
                return "admin-settlement";
            }
            case "admin-reports" -> {
                req.setAttribute("byPerformance", reporting.salesByPerformance());
                req.setAttribute("daily", reporting.dailyTotals());
                return "admin-reports";
            }
            case "about" -> {
                return "about";
            }
            case "maintenance" -> {
                return "maintenance";
            }
            default -> {
                resp.sendError(404);
                return null;
            }
        }
    }

    private static CartBean cart(HttpSession session) {
        CartBean cart = (CartBean) session.getAttribute(CART);
        if (cart == null) {
            try {
                cart = (CartBean) new InitialContext().lookup("java:module/CartBean");
            } catch (NamingException e) {
                throw new BoxOfficeException("cart bean unavailable", e);
            }
            session.setAttribute(CART, cart);
        }
        return cart;
    }

    private static Map<String, Object> toMap(PricingBean.Quote q) {
        if (q == null) {
            return null;
        }
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("subtotalCents", q.subtotalCents);
        m.put("serviceFeeCents", q.serviceFeeCents);
        m.put("facilityFeeCents", q.facilityFeeCents);
        m.put("deliveryFeeCents", q.deliveryFeeCents);
        m.put("feesCents", q.feesCents);
        m.put("totalCents", q.totalCents);
        m.put("seatCount", q.lines.size());
        return m;
    }

    private static String blankToNull(String s) {
        return s == null || s.isBlank() ? null : s;
    }
}
