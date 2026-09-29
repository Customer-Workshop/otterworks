<%@ include file="/WEB-INF/jspf/header.jspf" %>
<h1>My account</h1>
<form method="get" action="${ctx}/app/account"><input name="email" type="email" placeholder="you@example.test"><button>Open</button></form>
<c:if test="${not empty customer}">
  <p>${customer.full_name} &middot; ${customer.email}</p>
  <c:forEach var="a" items="${addresses}"><p class="muted">${a.line1}, ${a.city} ${a.postal_code}</p></c:forEach>
  <table><tr><th>Order</th><th>Event</th><th>Date</th><th>Status</th><th>Tickets</th><th>Total</th></tr>
  <c:forEach var="o" items="${orders}"><tr><td>${o.order_ref}</td><td>${o.event_title}</td><td>${o.starts_at}</td><td>${o.status}</td><td>${o.ticket_count}</td>
    <td><fmt:formatNumber value="${o.total_cents / 100}" type="currency" currencySymbol="$"/></td></tr></c:forEach>
  </table>
</c:if>
<%@ include file="/WEB-INF/jspf/footer.jspf" %>
