<%@ include file="/WEB-INF/jspf/header.jspf" %>
<h1>Reports</h1>
<h2>Sales by performance</h2>
<table><tr><th>Event</th><th>Venue</th><th>Starts</th><th>Confirmed orders</th><th>Tickets</th><th>Captured</th></tr>
<c:forEach var="r" items="${byPerformance}"><tr><td>${r.title}</td><td>${r.venue_name}</td><td>${r.starts_at}</td><td>${r.confirmed_orders}</td><td>${r.tickets}</td>
  <td><fmt:formatNumber value="${r.captured_cents / 100}" type="currency" currencySymbol="$"/></td></tr></c:forEach>
</table>
<h2>Daily totals</h2>
<table><tr><th>Day</th><th>Orders</th><th>Confirmed</th><th>Revenue</th></tr>
<c:forEach var="d" items="${daily}"><tr><td>${d.day}</td><td>${d.orders}</td><td>${d.confirmed}</td>
  <td><fmt:formatNumber value="${d.revenue_cents / 100}" type="currency" currencySymbol="$"/></td></tr></c:forEach>
</table>
<%@ include file="/WEB-INF/jspf/footer.jspf" %>
