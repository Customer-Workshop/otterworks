# BoxOffice monolith → event-driven services: decomposition note

Workflow token `tkt01`, stage 1 (assess). Base commit `cb628c9fd29d7de1b5109828b5cea56baeeceace`
(`origin/review-base-ticketing`). Every source link below is pinned to that commit; `mono/…` in prose means
`ticketing/monolith/…`. Everything in this repository is synthetic: promoters, venues, performers, customers and
card numbers are generated names and digits, and this note keeps it that way.

This note is the contract for the build, integrate and verify stages. The machine-readable form of §3 and §4 is
[`ticketing/docs/decomposition.json`](decomposition.json); the `services` and `events` arrays there are the source of
truth for names, tables, endpoints and payload fields — do not rename them.

## 0. Method and what DeepWiki covered

* DeepWiki was queried for `Cognition-Partner-Workshops/otterworks`. It does not index this branch: it answered
  only about unrelated material (a billing stored-procedure migration and an insurance module) and reported that it
  had no content for `ticketing/monolith`. Nothing below comes from DeepWiki; every claim was read in the source at
  the base commit.
* Inventory read: all 13 session beans, the 20 JSPs and 2 fragments, `db/schema.sql` (30 tables), `db/seed.sql`,
  the `common` package, the two timers, the front controller and the JAX-RS kiosk API, the README, the deploy
  manifests and scripts that set the runtime knobs. The
  [README table](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/README.md#L8-L17) matches what is on disk: 13 beans (12 `@Stateless`, 1 `@Stateful` cart),
  20 JSPs, 30 tables, one shared `Db` helper, one `audit_log`.

## 1. Bounded contexts

The monolith already groups its beans by package, and the packages are the contexts. The web layer
([`FrontControllerServlet`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/FrontControllerServlet.java#L30-L51) for `/app/*`,
[`PurchaseResource`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/PurchaseResource.java#L18-L31) for `/api/*` via
[`BoxOfficeApi`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/BoxOfficeApi.java#L7-L8)) is a shell over all of them and is
not a context.

| # | Context | Beans | JSPs | Tables owned |
|---|---------|-------|------|--------------|
| 1 | **catalog** — events, performers, venues, performances | [`EventCatalogBean`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/catalog/EventCatalogBean.java#L11-L84) | `index.jsp`, `events.jsp`, `event.jsp`, `performance.jsp`, `admin-events.jsp`, `admin-performance.jsp` | `promoters`, `venues`, `venue_sections`, `price_zones`, `seats`, `performers`, `events`, `event_performers`, `performances` |
| 2 | **inventory** — seat allocation, holds, hold expiry | [`SeatHoldBean`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/inventory/SeatHoldBean.java#L14-L91), [`SeatMapBean`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/inventory/SeatMapBean.java#L9-L42), [`HoldExpiryBean`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/inventory/HoldExpiryBean.java#L13-L44) (timer) | `seatmap.jsp`, `hold-expired.jsp` | `seat_inventory`, `seat_holds`, `seat_hold_items` |
| 3 | **pricing** — face value, demand uplift, promos, fees | [`PricingBean`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/pricing/PricingBean.java#L14-L127) | (none — quotes are rendered by `cart.jsp` / `checkout.jsp`) | `performance_price_levels`, `promo_codes`, `delivery_methods` |
| 4 | **customer** — accounts, addresses | [`CustomerAccountBean`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/customer/CustomerAccountBean.java#L9-L41) | `account.jsp` | `customers`, `customer_addresses` |
| 5 | **sales** — cart, order placement, order lookup, purchase orchestration | [`CartBean`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/sales/CartBean.java#L15-L46) (stateful), [`OrderBean`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/sales/OrderBean.java#L11-L81), [`PurchaseFacadeBean`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/sales/PurchaseFacadeBean.java#L17-L72) | `cart.jsp`, `checkout.jsp`, `order-lookup.jsp` | `carts`, `cart_items`, `orders`, `order_items`, `order_fees` |
| 6 | **payment** — gateway, attempts, captures, refunds | [`PaymentBean`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/payment/PaymentBean.java#L11-L63) (+ plain class [`PaymentGatewayClient`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/payment/PaymentGatewayClient.java#L7-L41)) | `payment-failed.jsp` | `payments`, `payment_attempts`, `refunds` |
| 7 | **fulfilment** — tickets, barcodes, confirmation e-mail | [`ConfirmationBean`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/fulfillment/ConfirmationBean.java#L12-L49) | `confirmation.jsp` | `tickets`, `confirmations` |
| 8 | **settlement** — nightly promoter payout batches | [`SettlementBean`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/settlement/SettlementBean.java#L17-L88) (timer) | `admin-settlement.jsp` | `settlement_batches`, `settlement_lines` |
| 9 | **reporting** — dashboards, `/api/stats` | [`ReportingBean`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/reporting/ReportingBean.java#L9-L53) | `admin-dashboard.jsp`, `admin-reports.jsp` | (none — reads every other context) |
| 10 | **audit** (cross-cutting `common`) | no bean: [`Db`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/common/Db.java#L18-L27), [`AuditLog`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/common/AuditLog.java#L3-L13), [`Config`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/common/Config.java#L1-L45), [`Refs`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/common/Refs.java#L14-L20), [`Money`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/common/Money.java#L11-L14), [`Json`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/common/Json.java#L1-L12), [`BoxOfficeException`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/common/BoxOfficeException.java#L5-L6) | web shell: `error.jsp`, `about.jsp`, `maintenance.jsp`, `header.jspf`, `footer.jspf` | `audit_log` |

13 beans, 20 JSPs (+2 fragments), 30 tables — every one appears exactly once above.

JSP → action mapping (from the front controller): `home`/`events`/`event`/`performance`
([L79-L101](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/FrontControllerServlet.java#L79-L101)) and `admin-events`/`admin-performance`
([L209-L222](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/FrontControllerServlet.java#L209-L222)) are catalog; `seatmap`/`hold`/`hold-expired`
([L102-L118](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/FrontControllerServlet.java#L102-L118),
[L175-L178](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/FrontControllerServlet.java#L175-L178)) are inventory; `cart`/`checkout`/`pay`/`lookup`
([L119-L163](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/FrontControllerServlet.java#L119-L163),
[L179-L188](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/FrontControllerServlet.java#L179-L188)) are sales; `confirmation`
([L164-L170](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/FrontControllerServlet.java#L164-L170)) is fulfilment; `payment-failed`
([L171-L174](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/FrontControllerServlet.java#L171-L174)) is payment; `account`
([L189-L202](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/FrontControllerServlet.java#L189-L202)) is customer; `admin`/`admin-reports`
([L203-L208](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/FrontControllerServlet.java#L203-L208),
[L231-L235](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/FrontControllerServlet.java#L231-L235)) are reporting; `admin-settlement`
([L223-L230](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/FrontControllerServlet.java#L223-L230)) is settlement; `about`/`maintenance`/`error`
([L236-L241](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/FrontControllerServlet.java#L236-L241),
[L61-L75](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/FrontControllerServlet.java#L61-L75)) are the shell. Note `performance.jsp`
also shows inventory counts ([performance.jsp L4](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/webapp/WEB-INF/jsp/performance.jsp#L4-L10)) and
`confirmation.jsp` is rendered entirely from `OrderBean` rows ([confirmation.jsp L6-L12](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/webapp/WEB-INF/jsp/confirmation.jsp#L6-L12)).

Two things are dead in the monolith and are documented so nobody ports them: `carts`/`cart_items` are never referenced
from Java (the "cart" is the in-memory `@Stateful` `CartBean`,
[L15-L38](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/sales/CartBean.java#L15-L38)), and `PaymentBean.refund`
([L56-L62](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/payment/PaymentBean.java#L56-L62)) has no caller in web or API.

## 2. Table ownership and why the schema is hard to split

The schema header says it: *"single shared schema, all modules read and write it … Owned by: nobody in
particular. Every module joins across it."* ([schema.sql L1-L2](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L1-L2)).

### 2.1 All 30 tables, one owner each

| Table | Owner | Schema | Written by (context) | Read by other contexts |
|-------|-------|--------|----------------------|------------------------|
| `promoters` | catalog | [L4-L11](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L4-L11) | seed only | settlement (`commission_bp`, [SettlementBean L33](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/settlement/SettlementBean.java#L33-L36)) |
| `venues` | catalog | [L13-L20](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L13-L20) | seed only | sales, fulfilment, customer, reporting joins |
| `venue_sections` | catalog | [L22-L30](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L22-L30) | seed only | inventory, sales |
| `price_zones` | catalog | [L32-L38](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L32-L38) | seed only | pricing, inventory, sales |
| `seats` | catalog | [L40-L48](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L40-L48) | seed only | inventory, pricing, sales |
| `performers` | catalog | [L50-L54](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L50-L54) | seed only | — |
| `events` | catalog | [L56-L65](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L56-L65) | seed only | sales, fulfilment, customer, settlement, reporting |
| `event_performers` | catalog | [L67-L72](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L67-L72) | seed only | — |
| `performances` | catalog | [L74-L82](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L74-L82) | catalog ([EventCatalogBean L79-L83](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/catalog/EventCatalogBean.java#L79-L83)) | inventory (`max_per_order`), pricing, sales, fulfilment, customer, settlement, reporting |
| `performance_price_levels` | pricing | [L84-L91](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L84-L91) | seed only | inventory (`SeatMapBean.sections`, [L21-L27](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/inventory/SeatMapBean.java#L21-L27)) |
| `seat_inventory` | inventory | [L93-L104](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L93-L104) | inventory, **sales** (`order_id`, [OrderBean L26](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/sales/OrderBean.java#L23-L27)), **fulfilment** (`SOLD`, [ConfirmationBean L33](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/fulfillment/ConfirmationBean.java#L33-L34)) | pricing, catalog, sales, reporting |
| `customers` | customer | [L106-L113](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L106-L113) | customer | sales, fulfilment, inventory (`customer_id` on holds) |
| `customer_addresses` | customer | [L115-L122](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L115-L122) | seed only | — |
| `seat_holds` | inventory | [L124-L133](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L124-L133) | inventory, **fulfilment** (`CONVERTED`, [ConfirmationBean L35](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/fulfillment/ConfirmationBean.java#L35)) | pricing, sales, payment |
| `seat_hold_items` | inventory | [L135-L139](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L135-L139) | inventory | pricing, sales |
| `carts` | sales | [L141-L147](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L141-L147) | nobody (dead) | — |
| `cart_items` | sales | [L149-L154](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L149-L154) | nobody (dead) | — |
| `promo_codes` | pricing | [L156-L164](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L156-L164) | **sales** (`used_count`, [OrderBean L33-L35](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/sales/OrderBean.java#L33-L35)) | — |
| `delivery_methods` | pricing | [L166-L171](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L166-L171) | seed only | — |
| `orders` | sales | [L173-L191](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L173-L191) | sales, **payment** (`PAYMENT_FAILED`/`PAYMENT_TIMEOUT`/`REFUNDED`, [PaymentBean L39,L46,L59](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/payment/PaymentBean.java#L35-L48)), **fulfilment** (`CONFIRMED`, [ConfirmationBean L36](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/fulfillment/ConfirmationBean.java#L36)), **inventory** (`CANCELLED`, [HoldExpiryBean L35-L37](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/inventory/HoldExpiryBean.java#L35-L37)) | payment, fulfilment, customer, settlement, reporting |
| `order_items` | sales | [L193-L199](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L193-L199) | sales | fulfilment, settlement |
| `order_fees` | sales | [L201-L206](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L201-L206) | sales | — |
| `payments` | payment | [L208-L219](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L208-L219) | payment | settlement, reporting |
| `payment_attempts` | payment | [L221-L228](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L221-L228) | payment | — |
| `refunds` | payment | [L230-L236](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L230-L236) | payment (dead path) | settlement |
| `tickets` | fulfilment | [L238-L246](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L238-L246) | fulfilment | sales (`ticket_code` on items), customer, settlement, reporting |
| `confirmations` | fulfilment | [L248-L258](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L248-L258) | fulfilment | reporting |
| `settlement_batches` | settlement | [L260-L272](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L260-L272) | settlement | — |
| `settlement_lines` | settlement | [L274-L281](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L274-L281) | settlement | — |
| `audit_log` | audit | [L283-L290](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L283-L290) | **every context** via `AuditLog.record` | reporting (`audit-log` panel via `recent`) |

### 2.2 The single JTA transaction in `PurchaseFacadeBean`

`purchase(...)` and `checkout(...)` are `@TransactionAttribute(REQUIRED)`
([L37-L52](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/sales/PurchaseFacadeBean.java#L37-L52)) and `completeHold` chains six
contexts inside that one transaction
([L54-L71](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/sales/PurchaseFacadeBean.java#L54-L71)):

```
customers.findOrCreate → holds.hold → pricing.quote → orders.place → payments.charge → confirmations.confirm
```

The class comment says why it was built this way: one container transaction "so the whole purchase either commits
or rolls back" ([L17-L20](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/sales/PurchaseFacadeBean.java#L17-L20)). Consequences:

* The seat rows selected `FOR UPDATE SKIP LOCKED` in `SeatHoldBean.hold`
  ([L29-L39](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/inventory/SeatHoldBean.java#L29-L39)) stay locked while the pricing
  passes run and while the gateway sleeps up to `PAYMENT_TIMEOUT_MS`
  ([PaymentGatewayClient L20-L27](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/payment/PaymentGatewayClient.java#L19-L32)).
  Lock hold time = pricing CPU + gateway latency.
* Declines and timeouts are *not* rollbacks: `BoxOfficeException` is `rollback = true`
  ([L5-L6](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/common/BoxOfficeException.java#L5-L6)) but `PaymentBean.charge` returns
  the outcome instead of throwing, so the failed order, its attempt row and the released hold all commit
  ([L35-L48](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/payment/PaymentBean.java#L35-L48)). Only `SOLD_OUT`, `NOT_FOUND`,
  `BAD_QUANTITY`, `HOLD_EXPIRED` and SQL errors roll everything back.
* `PricingBean.quote` is called *after* the hold, so the demand tally counts the seats just held
  ([PurchaseFacadeBean L41 then L56](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/sales/PurchaseFacadeBean.java#L37-L57);
  tally at [PricingBean L78-L84](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/pricing/PricingBean.java#L78-L84)).

### 2.3 `Db` and `AuditLog` in `common`

`Db` is "the one JDBC helper every module in the application goes through"; connections come from the container
datasource and enlist in the caller's JTA transaction ([Db L18-L27](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/common/Db.java#L18-L27),
JNDI name [L25](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/common/Db.java#L25)). `AuditLog.record` is a static insert into
`audit_log` through the same helper ([AuditLog L9-L12](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/common/AuditLog.java#L9-L12)),
called from inventory ([SeatHoldBean L54](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/inventory/SeatHoldBean.java#L54),
[HoldExpiryBean L41](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/inventory/HoldExpiryBean.java#L39-L42)), sales
([OrderBean L36](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/sales/OrderBean.java#L36)), payment
([PaymentBean L51-L52](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/payment/PaymentBean.java#L50-L53)), fulfilment
([ConfirmationBean L42](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/fulfillment/ConfirmationBean.java#L42)), customer
([CustomerAccountBean L18](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/customer/CustomerAccountBean.java#L12-L20)), catalog
([EventCatalogBean L82](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/catalog/EventCatalogBean.java#L79-L83)) and settlement
([SettlementBean L78](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/settlement/SettlementBean.java#L76-L79)). Because it runs in the
caller's transaction, an audit row is part of every business write — splitting the database means every service
loses the shared audit table. `Refs.next` ([L14-L20](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/common/Refs.java#L14-L20))
generates the `BO-`, `HD-`, `PAY-`, `TK-`, `GW-`, `STL-` references (random, not sequence-based, so services can
generate them independently) and `Money.percentOf` is basis-point HALF_UP rounding
([L11-L14](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/common/Money.java#L11-L14)) that must be copied verbatim to keep totals equal.

### 2.4 Cross-context writes on the purchase path

| Writer | Table it does not own | Where |
|--------|-----------------------|-------|
| sales `OrderBean.place` | `seat_inventory.order_id` | [L23-L27](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/sales/OrderBean.java#L23-L27) |
| sales `OrderBean.place` | `promo_codes.used_count` (incremented at placement, even if payment later fails) | [L33-L35](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/sales/OrderBean.java#L33-L35) |
| payment `PaymentBean.charge` | `orders.status`, and `seat_holds`/`seat_inventory` through `holds.release` | [L35-L48](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/payment/PaymentBean.java#L35-L48), release at [SeatHoldBean L80-L86](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/inventory/SeatHoldBean.java#L80-L86) |
| fulfilment `ConfirmationBean.confirm` | `seat_inventory.status=SOLD`, `seat_holds.status=CONVERTED`, `orders.status=CONFIRMED` | [L33-L36](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/fulfillment/ConfirmationBean.java#L33-L36) |
| inventory `HoldExpiryBean` | `orders.status=CANCELLED` for `PENDING_PAYMENT` orders on the hold | [L35-L37](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/inventory/HoldExpiryBean.java#L35-L37) |
| every context | `audit_log` | §2.3 |

### 2.5 Cross-context joins (reads)

* **Order lookup** `OrderBean.byRef` joins `customers`, `performances`, `events`, `venues`
  ([L48-L57](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/sales/OrderBean.java#L48-L57)); `OrderBean.items` joins `seat_inventory`,
  `seats`, `venue_sections`, `price_zones` and left-joins `tickets` for the ticket code
  ([L59-L69](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/sales/OrderBean.java#L59-L69)). This is what `GET /api/orders/{ref}` and
  `confirmation.jsp` render.
* **Hold** `SeatHoldBean.hold` reads `performances.max_per_order` and joins `seats`/`venue_sections`
  ([L21-L39](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/inventory/SeatHoldBean.java#L21-L39)); `SeatMapBean.sections` joins
  `performance_price_levels` for the face value ([L21-L27](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/inventory/SeatMapBean.java#L21-L27)).
* **Pricing** `PricingBean.quote` reads `seat_holds`, `seat_hold_items`, `seat_inventory`, `seats`,
  `performance_price_levels` ([L25-L39](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/pricing/PricingBean.java#L25-L39)) and the
  demand tally scans the whole performance's `seat_inventory` joined to `seats`
  ([L78-L84](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/pricing/PricingBean.java#L78-L84)) — `PRICING_PASSES` times
  ([L86-L105](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/pricing/PricingBean.java#L86-L105)).
* **Confirmation** `ConfirmationBean.confirm` joins `orders`, `customers`, `performances`, `events`, `venues`
  ([L19-L26](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/fulfillment/ConfirmationBean.java#L19-L26)).
* **Customer** `CustomerAccountBean.orders` joins `orders`, `performances`, `events`, `venues`, `tickets`
  ([L26-L36](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/customer/CustomerAccountBean.java#L26-L36)).
* **Catalog** `EventCatalogBean.performances` counts `seat_inventory` per performance
  ([L49-L56](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/catalog/EventCatalogBean.java#L49-L56)).
* **Reporting** `salesByPerformance` joins `performances`, `events`, `venues`, `orders`, `payments`, `tickets`
  ([L13-L26](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/reporting/ReportingBean.java#L13-L26)); `dailyTotals` reads `orders`
  ([L28-L34](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/reporting/ReportingBean.java#L28-L34)); `stats` reads `orders`,
  `payments`, `tickets`, `confirmations`, `seat_inventory`
  ([L37-L52](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/reporting/ReportingBean.java#L37-L52)).
* **Settlement** (nightly `@Schedule(hour="2", minute="15")`,
  [L24-L28](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/settlement/SettlementBean.java#L24-L28)) per promoter joins
  `orders`+`payments`+`performances`+`events` for gross/fees
  ([L37-L45](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/settlement/SettlementBean.java#L37-L45)),
  `refunds`+`payments`+`orders`+`performances`+`events` for refunds
  ([L46-L52](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/settlement/SettlementBean.java#L46-L52)), applies
  `promoters.commission_bp` ([L55-L56](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/settlement/SettlementBean.java#L55-L56)), then
  `orders`+`order_items`+`tickets`+`performances`+`events` for the lines
  ([L66-L75](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/settlement/SettlementBean.java#L66-L75)). It deletes and rewrites
  yesterday's batch on every run ([L59-L65](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/settlement/SettlementBean.java#L59-L65)).

Settlement and reporting are pure readers of five other contexts; they stay in the monolith for the first slice and
later consume the events in §3 instead of joining.

## 3. Events between contexts

Topic naming, partitions and keys follow
[`CONVENTIONS.md`](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/CONVENTIONS.md):
`<token>-<event-name>`, 6 partitions, key = order reference so one order's records replay in order. All payloads are
JSON with the exact field names in `decomposition.json`; money is integer cents, timestamps ISO-8601 UTC.

**Delivery rule.** `seats`, `orders` and `confirmations` are request-driven Knative Services that scale to zero, so
they cannot hold a Kafka consumer. Only `payments` consumes from Kafka (that is what KEDA scales). For every other
edge the producer (a) writes the record to the topic — the durable fact, what dashboards and future monolith
adapters read — and (b) delivers the same JSON to the consumer's HTTP inbox `POST /events/<event-name>` as part of
the same unit of work (payments: before committing the offset; seats/confirmations: within the request that produced
it). Every inbox is idempotent on the key, so at-least-once delivery on either path is safe.

| Event | Producer | Consumers | Key | Payload fields | Replaces (monolith) |
|-------|----------|-----------|-----|----------------|---------------------|
| `order-placed` | orders (outbox relay) | payments | `orderRef` | `orderRef, clientRef, customerEmail, performanceId, eventTitle, venueName, startsAt, holdRef, holdExpiresAt, channel, items[]{seatInventoryId, priceZoneId, zoneCode, zoneName, section, rowLabel, seatNumber, priceCents}, fees[]{feeType, amountCents}, subtotalCents, feesCents, totalCents, currency, cardLast4, placedAt` | `orders.place` → `payments.charge` call ([PurchaseFacadeBean L57-L58](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/sales/PurchaseFacadeBean.java#L57-L58)) |
| `payment-captured` | payments | confirmations; settlement (monolith, future) | `orderRef` | `orderRef, gatewayRef, amountCents, currency, cardLast4, attemptNo, latencyMs, capturedAt, order{customerEmail, performanceId, eventTitle, venueName, startsAt, holdRef, totalCents, items[]{seatInventoryId, section, rowLabel, seatNumber, zoneCode}}` | `APPROVED` branch → `confirmations.confirm` ([L60-L62](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/sales/PurchaseFacadeBean.java#L60-L62)) |
| `payment-failed` | payments | orders, seats; reporting (future) | `orderRef` | `orderRef, holdRef, outcome (DECLINED\|TIMEOUT\|HOLD_EXPIRED), orderStatus (PAYMENT_FAILED\|PAYMENT_TIMEOUT\|CANCELLED), amountCents, cardLast4, attemptNo, latencyMs, gatewayRef (null on TIMEOUT/HOLD_EXPIRED), failedAt` | `PaymentBean` writing `orders.status` + `holds.release` ([L35-L48](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/payment/PaymentBean.java#L35-L48)); `checkout` `HOLD_EXPIRED` guard ([L48-L50](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/sales/PurchaseFacadeBean.java#L45-L52)) |
| `order-confirmed` | confirmations | orders, seats; settlement/customer (future) | `orderRef` | `orderRef, holdRef, performanceId, ticketCount, tickets[]{ticketCode, seatInventoryId, barcode}, recipient, confirmedAt` | `ConfirmationBean` writing `seat_inventory`, `seat_holds`, `orders` ([L33-L36](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/fulfillment/ConfirmationBean.java#L33-L36)) |
| `hold-expired` | seats (sweep) | orders; reporting (future) | `orderRef` if a `PENDING_PAYMENT` order is attached, else `holdRef` | `holdRef, performanceId, orderRef (nullable), seatInventoryIds[], expiredAt` | `HoldExpiryBean` cancelling orders ([L29-L43](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/inventory/HoldExpiryBean.java#L29-L43)) |

Events that exist between contexts but are **not** part of the first slice (settlement, reporting, customer and
refunds stay in the monolith): `order-refunded` (payment → settlement, sales), `settlement-batch-closed`
(settlement → reporting), `performance-updated` (catalog → inventory/pricing). They are named here so later slices do
not collide, but no service in this slice produces or consumes them.

## 4. First slice: orders, seats, payments, confirmations

Runtimes are fixed by `CONVENTIONS.md`: `orders`, `seats`, `confirmations` = request-driven Knative Services;
`payments` = Kafka consumer Deployment with a KEDA `ScaledObject` (min 0, max 6, manual commit after the DB
transaction, order reference as the idempotency key). Each service has its own PostgreSQL; the monolith database is
not shared with any of them.

### 4.1 Target flow (after)

```
client ──POST /api/purchase──▶ orders ──POST /api/holds──▶ seats        (sync, 201 hold + zone tally)
                                orders: price, INSERT orders+items+fees+outbox  (one local tx) ──▶ 202 PENDING_PAYMENT
                                relay: outbox ──▶ topic <token>-order-placed
payments (KEDA) ◀── order-placed ── charge (sim gateway) ── INSERT payment_attempts+payments (tx) ── publish
   APPROVED  ──▶ payment-captured ──▶ confirmations POST /events/payment-captured
                                        confirmations: tickets+confirmation (tx) ──▶ order-confirmed ──▶ orders, seats inboxes
   DECLINED / TIMEOUT / HOLD_EXPIRED ──▶ payment-failed ──▶ orders, seats inboxes
   commit offset
seats CronJob (1/min) ──▶ POST /api/holds/sweep ──▶ hold-expired ──▶ orders inbox
```

Identifier rule: reference data is copied from the *same deterministic seed*, whose ids are stable across resets
([seed.sql L1-L2](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/seed.sql#L1-L2)), so `performanceId`, `seatInventoryId` and `priceZoneId` are valid opaque
identifiers across services. Everything created at runtime crosses service boundaries only by business reference
(`orderRef`, `holdRef`, `ticketCode`), never by database id: `orders.hold_id` becomes `orders.hold_ref`,
`seat_inventory.order_id` becomes `seat_inventory.order_ref`, `payments.order_id`/`tickets.order_id`/
`confirmations.order_id` become `order_ref`.

Observable-behaviour mapping (all four services must hit these):

| Monolith behaviour | Source | After-state observation |
|--------------------|--------|-------------------------|
| `POST /api/purchase` → **201** when the order ends `CONFIRMED`, **402** otherwise, body `{orderRef,status,totalCents,tickets,paymentOutcome}` | [PurchaseResource L52-L84](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/PurchaseResource.java#L52-L84) | `orders` answers **202** `{orderRef,status:PENDING_PAYMENT,totalCents,tickets:0,paymentOutcome:PENDING}` immediately; `GET /api/orders/{ref}` converges to `status=CONFIRMED, tickets=quantity, paymentOutcome=APPROVED` (≡201) or `status=PAYMENT_FAILED\|PAYMENT_TIMEOUT, tickets=0, paymentOutcome=DECLINED\|TIMEOUT` (≡402). `totalCents` in the 202 is final and equals the monolith total. |
| Defaults: `quantity=2`, `channel=KIOSK`, `delivery=MOBILE`, `cardLast4=4242`, `email` = synthetic `kiosk+<n>@example.test` | [L64-L72](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/PurchaseResource.java#L64-L72) | identical defaults in `orders` |
| Error mapping: bad JSON → **400** `BAD_REQUEST`; `SOLD_OUT` → **409**; `NOT_FOUND` → **404**; `BAD_QUANTITY`/`BAD_REQUEST` → **400**; `HOLD_EXPIRED` → **410**; other → **500**; body `{error, message}` | [L57-L62](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/PurchaseResource.java#L57-L62), [L131-L140](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/PurchaseResource.java#L131-L140) | `seats` raises the same codes on `POST /api/holds`; `orders` passes them through unchanged; `410` only from `POST /api/orders` on an inactive hold |
| Quantity must be 1..`performances.max_per_order`; unknown performance → `NOT_FOUND`; fewer free seats than asked → `SOLD_OUT` (optionally within one section) | [SeatHoldBean L21-L42](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/inventory/SeatHoldBean.java#L21-L42) | same checks in `seats`, same order of checks |
| Totals: line price = `face_value_cents × (demand_factor_bp + uplift) / 10000` HALF_UP; `uplift = min(4000, (soldPct/10)×500)` with `soldPct = notAvailable×100/total` (integer division, per price zone, `HELD` counts as not available, tally taken after the hold); promo `-discount_bp` of subtotal if code exists, `valid_until > now` and `used_count < max_uses` (**event_id is not checked**); service fee 12 % of the discounted subtotal; facility fee 250 ¢ per seat; delivery fee from `delivery_methods` (`MOBILE` 0, `PRINT` 150, `WILLCALL` 0); `total = subtotal + service + facility + delivery`. The `PRICING_PASSES` loop recomputes the identical tally each pass, so the result is independent of the pass count | [PricingBean L21-L22](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/pricing/PricingBean.java#L21-L22), [L43-L72](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/pricing/PricingBean.java#L43-L72), [L86-L105](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/pricing/PricingBean.java#L86-L105), [Money L11-L14](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/common/Money.java#L11-L14), seed [L67-L84](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/seed.sql#L67-L84) | `orders` computes once from the `zoneTally` returned by `seats`. Worked example at 0 % sell-through, 2 × P1 arena seats (18 900 ¢): subtotal 37 800, service 4 536, facility 500, `MOBILE` 0 → **42 836**; with `PRINT` → **42 986**; with `FANCLUB10` → subtotal 34 020, service 4 082, facility 500 → **38 602** |
| `promo_codes.used_count` is incremented at placement, regardless of payment outcome | [OrderBean L33-L35](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/sales/OrderBean.java#L33-L35) | `orders` increments its local copy at placement |
| Order fees rows `SERVICE`, `FACILITY`, `DELIVERY` (delivery only when > 0) | [OrderBean L28-L32](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/sales/OrderBean.java#L28-L32) | same rows in `orders.order_fees`, same `fees[]` shape |
| Hold expiry: `expires_at = now + HOLD_MINUTES` (default 10; 10 in the k8s manifests); sweeper every minute at second 0, ≤500 holds per run; seats back to `AVAILABLE`, hold `EXPIRED`, attached `PENDING_PAYMENT` orders `CANCELLED`; `POST /api/admin/expire-holds` → `{released:n}` | [SeatHoldBean L43](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/inventory/SeatHoldBean.java#L43-L47), [Config L18-L20](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/common/Config.java#L18-L20), [HoldExpiryBean L21-L43](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/inventory/HoldExpiryBean.java#L21-L43), [PurchaseResource L118-L122](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/PurchaseResource.java#L118-L122) | `seats` CronJob + `POST /api/holds/sweep` (alias `/api/admin/expire-holds`, same `{released:n}`); `hold-expired` → `orders` cancels; in addition `payments` never charges a record whose `holdExpiresAt` has passed (emits `payment-failed` with `outcome=HOLD_EXPIRED`, `orderStatus=CANCELLED`) — the async equivalent of the `HOLD_EXPIRED` guard |
| Card `0000` always declines; otherwise decline with probability `GATEWAY_DECLINE_PCT` (default 0) | [PaymentGatewayClient L28-L30](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/payment/PaymentGatewayClient.java#L28-L30), [README L33](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/README.md#L33) | `payments` simulator identical; visible as `paymentOutcome=DECLINED`, `status=PAYMENT_FAILED`, seats `AVAILABLE` again, `payments.status=DECLINED` with a `GW-` gateway ref |
| Timeout: latency uniform in `[GATEWAY_MIN_MS, GATEWAY_MAX_MS]` (40–120), caller sleeps `min(latency, PAYMENT_TIMEOUT_MS)` (4000) and reports `TIMEOUT` with `gateway_ref = NULL` when `latency > timeout` | [L19-L32](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/payment/PaymentGatewayClient.java#L19-L32), [Config L23-L34](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/common/Config.java#L23-L34) | identical knobs and semantics in `payments`; `status=PAYMENT_TIMEOUT`, `paymentOutcome=TIMEOUT`, `payments.status=TIMEOUT`, `gatewayRef=null`, seats released |
| Payment rows: one `payment_attempts` row per call (`attempt_no`, `outcome`, `latency_ms`), one `payments` row per outcome (`CAPTURED`/`DECLINED`/`TIMEOUT`, `PAY-` ref, `provider=SYNTH`) | [PaymentBean L27-L48](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/payment/PaymentBean.java#L27-L48), schema [L208-L228](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L208-L228) | same rows in the `payments` DB, plus `EXPIRED` for the hold-lapsed case and `UNIQUE(order_ref)` on `payments` |
| Confirmation: one `TK-` ticket + 24-char barcode per item, `issued_at`; `confirmations` row `recipient=email`, `subject="Your tickets for <title>"`, `body="Order <ref>: <n> ticket(s) for <title> at <venue> on <starts_at>. Total $x.xx"`, `status=QUEUED`; tickets returned = item count | [ConfirmationBean L27-L44](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/fulfillment/ConfirmationBean.java#L27-L44) | identical rows in the `confirmations` DB; `tickets` in `GET /api/orders/{ref}` = `ticketCount` from `order-confirmed`; `ticket_code` visible per item |
| `GET /api/orders/{ref}` shape (`order`, `items[]`, `fees[]`) and 404 | [PurchaseResource L86-L96](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/PurchaseResource.java#L86-L96), [OrderBean L48-L73](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/sales/OrderBean.java#L48-L73) | `orders` keeps the shape; item columns are denormalised at placement from the seats response instead of joined |
| `GET /api/performances/{id}/availability` → `{available, held, sold}` | [L98-L102](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/PurchaseResource.java#L98-L102), [SeatMapBean L35-L41](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/inventory/SeatMapBean.java#L35-L41) | served by `seats`, same shape |
| `GET /api/stats` keys `ordersTotal, ordersByStatus, paymentsCaptured, capturedCents, ticketsIssued, confirmationsQueued, seatsSold, seatsHeld` | [L104-L108](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/PurchaseResource.java#L104-L108), [ReportingBean L37-L52](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/reporting/ReportingBean.java#L37-L52) | partitioned: `orders /stats` → `ordersTotal, ordersByStatus`; `payments /stats` → `paymentsCaptured, capturedCents`; `confirmations /stats` → `ticketsIssued, confirmationsQueued`; `seats /stats` → `seatsSold, seatsHeld`. Reconciliation invariant: `ordersByStatus.CONFIRMED == paymentsCaptured == confirmationsQueued` and `ticketsIssued == seatsSold` |
| `GET /api/health` → `{"status":"UP"}` | [L124-L129](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/PurchaseResource.java#L124-L129) | each service's `/actuator/health`; the after ingress maps `/api/health` to `orders` |
| Web checkout: hold → quote → `pay` form (`cardLast4` default 4242) → `confirmation` or `payment-failed`; `HOLD_EXPIRED` redirects to `hold-expired` | [FrontControllerServlet L108-L178](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/web/FrontControllerServlet.java#L108-L178), [checkout.jsp L19-L23](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/webapp/WEB-INF/jsp/checkout.jsp#L19-L23) | stays in the monolith (see 4.6) |

Runtime knobs must be honoured with the monolith's names and defaults
([Config L17-L44](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/common/Config.java#L17-L44)): `HOLD_MINUTES=10`,
`PAYMENT_TIMEOUT_MS=4000`, `GATEWAY_MIN_MS=40`, `GATEWAY_MAX_MS=120`, `GATEWAY_DECLINE_PCT=0`. `PRICING_PASSES`
(3 in code, 200 in the before-state deploy
[scripts/lib.sh](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/scripts/lib.sh#L17-L19))
is the monolith's CPU sink; it does not exist in the services because the passes are a no-op on the result.

### 4.2 `orders` — Knative Service + outbox relay

* **Takes** `orders`, `order_items`, `order_fees` (monolith schema
  [L173-L206](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L173-L206)) and adds `outbox`. Column changes: `customer_id` → `customer_email`
  (lower-cased as [CustomerAccountBean L12-L17](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/customer/CustomerAccountBean.java#L12-L17)),
  `hold_id` → `hold_ref` + `hold_expires_at`, new `client_ref UNIQUE NULL`, new `payment_outcome`,
  `order_items` gains denormalised `section, row_label, seat_number, zone_code, zone_name, ticket_code`.
* **Reference data (read-only copies, seeded from `db/seed.sql`)**: `performances`, `events`, `venues` (for
  `event_title`, `starts_at`, `venue_name` in the order view and the `order-placed` payload — seed
  [L36-L65](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/seed.sql#L36-L65)), `performance_price_levels` (face value + base `demand_factor_bp`,
  [L67-L71](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/seed.sql#L67-L71)), `promo_codes` ([L82-L84](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/seed.sql#L82-L84); the only reference table
  `orders` writes — `used_count`), `delivery_methods` ([L79-L80](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/seed.sql#L79-L80)).
* **API**: see `decomposition.json` (`POST /api/purchase`, `POST /api/orders`, `GET /api/orders/{ref}`, three
  `/events/*` inboxes, `/stats`, actuator).
* **Order-placement outbox**: table `outbox(id BIGSERIAL PK, aggregate_ref TEXT, event_name TEXT, key TEXT,
  payload JSONB, created_at, published_at NULL)`. `POST /api/purchase` inserts the order rows and the
  `order-placed` outbox row in **one local transaction** — the only way to keep "a placed order always reaches
  payments" without the monolith's JTA span. The relay is a separate Deployment in the same dir, scaled by a KEDA
  `postgresql` trigger on `SELECT count(*) FROM outbox WHERE published_at IS NULL` (min 0), publishing in `id`
  order per key with `acks=all`, then setting `published_at`; it is at-least-once, `payments` de-duplicates.
  Metric `orders_outbox_unpublished` (gauge) and `orders_outbox_published_total` (counter) on
  `/actuator/prometheus`; `/stats.outboxUnpublished` mirrors the gauge for the demo table.
* **Publishes** `order-placed`. **Consumes** `payment-failed`, `order-confirmed`, `hold-expired` via inbox.
* **Status machine** (same names as the monolith `orders.status` check
  [schema L181](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L173-L191)): `PENDING_PAYMENT → CONFIRMED | PAYMENT_FAILED | PAYMENT_TIMEOUT |
  CANCELLED`. Inbox transitions from a terminal state are ignored (idempotent replay).
* **Placement idempotency**: optional `clientRef` (the k6 "unique order key"); a replay with the same `clientRef`
  returns the existing order and does not hold seats again.

### 4.3 `seats` — Knative Service

* **Takes** `seat_inventory`, `seat_holds`, `seat_hold_items` ([schema L93-L104](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L93-L104),
  [L124-L139](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L124-L139)); `seat_inventory.order_id` → `order_ref`, `seat_holds.customer_id` →
  `customer_email NULL`. Seed the inventory exactly as the monolith does (every seat of the venue, `AVAILABLE`, per
  performance — [seed.sql L73-L77](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/seed.sql#L73-L77); 152 400 rows for the 24 performances).
* **Reference data**: `performances` (`max_per_order`, `venue_id` — [seed L58-L65](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/seed.sql#L58-L65)),
  `seats`, `venue_sections`, `price_zones` ([seed L14-L34](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/seed.sql#L14-L34)) for best-available selection,
  section filter, and the per-seat labels/zone returned to `orders`.
* **Hold algorithm** = [SeatHoldBean L20-L56](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/inventory/SeatHoldBean.java#L20-L56):
  `SELECT … FOR UPDATE SKIP LOCKED` ordered by section, row, seat, limited to `quantity`; `SOLD_OUT` if fewer
  rows; `HD-` ref; `expires_at = now + HOLD_MINUTES`; rows → `HELD`. In addition the response carries the per-zone
  `zoneTally` computed **after** the update in the same transaction, which is what
  [PricingBean L78-L84](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/pricing/PricingBean.java#L78-L84) would have counted.
* **Release / convert** = [SeatHoldBean L80-L90](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/inventory/SeatHoldBean.java#L80-L90),
  driven by the `payment-failed` and `order-confirmed` inboxes; `order-confirmed` also marks the seats `SOLD`
  ([ConfirmationBean L33-L35](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/fulfillment/ConfirmationBean.java#L33-L35)).
* **Sweep** = [HoldExpiryBean](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/inventory/HoldExpiryBean.java#L21-L43) as an endpoint
  called by a CronJob every minute (a scale-to-zero service has no timer); publishes `hold-expired`.
* **Publishes** `hold-expired`. **Consumes** `payment-failed`, `order-confirmed`.

### 4.4 `payments` — Kafka consumer Deployment + KEDA

* **Takes** `payments`, `payment_attempts` ([schema L208-L228](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L208-L228)) with `order_id` →
  `order_ref`; adds `UNIQUE(order_ref)` on `payments` and `UNIQUE(order_ref, attempt_no)` on `payment_attempts`.
  `refunds` stays in the monolith (no live caller).
* **Reference data**: none — the amount, card and hold deadline travel in `order-placed`.
* **Consumes** `order-placed` (group `<token>-payments`, one record at a time per partition, `enable.auto.commit=false`,
  commit after the DB transaction and after the inbox deliveries). **Publishes** `payment-captured`, `payment-failed`.
* **Idempotency key = `orderRef`** (`payments.order_ref UNIQUE`). Per record:
  1. If a `payments` row for `orderRef` exists → do **not** call the gateway or write; re-run step 4 with the stored
     outcome (covers a pod killed between commit and delivery), increment `duplicates_suppressed`, commit offset.
  2. If `holdExpiresAt < now` → outcome `HOLD_EXPIRED`: insert `payments(status=EXPIRED, gateway_ref NULL)` and an
     attempt row, no gateway call.
  3. Else run the simulator exactly as
     [PaymentGatewayClient L19-L32](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/payment/PaymentGatewayClient.java#L19-L32) and
     write `payment_attempts` + `payments` (`CAPTURED` / `DECLINED` / `TIMEOUT`, `PAY-` ref, `provider=SYNTH`) in one
     transaction, as [PaymentBean L27-L48](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/payment/PaymentBean.java#L27-L48).
  4. Publish `payment-captured` (→ inbox `confirmations`) or `payment-failed` (→ inboxes `orders`, `seats`).
  5. Commit the offset.
  A killed pod therefore never loses or double-charges an order: the partition replays and steps 1/4 make redelivery a
  no-op with the side effects re-driven.
* **Scaling**: KEDA `kafka` trigger on the consumer group lag of `<token>-order-placed`, `minReplicaCount: 0`,
  `maxReplicaCount: 6` (= partitions), `cooldownPeriod` ≤ 60 s. Each record costs 40–120 ms of gateway latency (or
  4 s on a timeout), so six partitions sustain the 600 orders/min on-sale peak with lag draining.

### 4.5 `confirmations` — Knative Service

* **Takes** `tickets`, `confirmations` ([schema L238-L258](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/db/schema.sql#L238-L258)) with `order_id` →
  `order_ref` and `UNIQUE(order_ref)` on `confirmations`; `tickets.seat_inventory_id` stays (deterministic seed id),
  `tickets.order_item_id` → `seat_inventory_id` + `order_ref`.
* **Reference data**: none — title, venue, start time, e-mail and total travel in `payment-captured.order`.
* **Consumes** `payment-captured` via inbox; issues one ticket per item and the confirmation row exactly as
  [ConfirmationBean L27-L41](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/fulfillment/ConfirmationBean.java#L27-L41) in one local
  transaction, then **publishes** `order-confirmed` and delivers it to the `orders` and `seats` inboxes. A replay for
  an existing `order_ref` re-publishes/re-delivers without issuing new tickets.
* The e-mail is never sent (monolith leaves it `QUEUED`,
  [L37-L41](https://github.com/Cognition-Partner-Workshops/otterworks/blob/cb628c9fd29d7de1b5109828b5cea56baeeceace/ticketing/monolith/src/main/java/com/boxoffice/fulfillment/ConfirmationBean.java#L37-L41)); keep `status=QUEUED`.

### 4.6 What stays in the monolith

* Contexts: catalog, pricing configuration (the services carry read-only copies; the monolith stays the writer via
  `admin-performance`), customer (`customers`, `customer_addresses` — the services store the e-mail only),
  settlement (timer and tables, unchanged; it will later consume `payment-captured`/`order-confirmed` instead of
  joining the sales/payment tables), reporting (`admin-dashboard`, `admin-reports`; `/api/stats` is partitioned as
  above), audit (`audit_log` — services emit structured logs and Kafka records instead), refunds (dead path), the
  in-memory `CartBean`, and the JSP storefront with its in-process checkout.
* Tables staying: `promoters`, `venues`, `venue_sections`, `price_zones`, `seats`, `performers`, `events`,
  `event_performers`, `performances`, `performance_price_levels`, `customers`, `customer_addresses`, `carts`,
  `cart_items`, `promo_codes`, `delivery_methods`, `refunds`, `settlement_batches`, `settlement_lines`, `audit_log`
  (20). Tables leaving: the 10 in §4.2–4.5.
* In the demo the before (`tkt01-before`) and after (`tkt01-after`) namespaces are independent installations seeded
  from the same deterministic seed; there is no dual-write or live migration. The after ingress routes
  `/api/purchase`, `/api/orders/*`, `/api/health` → `orders`; `/api/performances/*`, `/api/admin/expire-holds` →
  `seats`; `/api/stats` → each service's `/stats` (the integrate stage decides the exact composition).

## 5. Link check

Sample of the permalinks above resolved at the base commit and checked against the lines cited:
`PurchaseFacadeBean.java#L54-L71` (completeHold), `PaymentGatewayClient.java#L19-L32` (simulator),
`OrderBean.java#L33-L35` (promo `used_count`), `HoldExpiryBean.java#L35-L37` (`CANCELLED`),
`schema.sql#L173-L191` (`orders`), `SettlementBean.java#L24-L28` (02:15 timer), `ReportingBean.java#L37-L52`
(`stats`), `Db.java#L18-L27` (shared helper comment), `PurchaseResource.java#L131-L140` (status mapping).
