<%@ include file="/WEB-INF/jspf/header.jspf" %>
<h1>Back office</h1>
<p>Orders ${stats.ordersTotal} &middot; captured payments ${stats.paymentsCaptured} &middot; tickets ${stats.ticketsIssued} &middot; seats held ${stats.seatsHeld}</p>
<p><c:forEach var="s" items="${stats.ordersByStatus}">${s.key}: ${s.value} &nbsp; </c:forEach></p>
<nav class="sub"><a href="${ctx}/app/admin-events">Performances</a> <a href="${ctx}/app/admin-settlement">Settlement</a> <a href="${ctx}/app/admin-reports">Reports</a></nav>
<h2>Recent orders</h2>
<table><tr><th>Ref</th><th>Event</th><th>Status</th><th>Channel</th><th>Total</th></tr>
<c:forEach var="o" items="${recent}"><tr><td>${o.order_ref}</td><td>${o.event_title}</td><td>${o.status}</td><td>${o.channel}</td>
  <td><fmt:formatNumber value="${o.total_cents / 100}" type="currency" currencySymbol="$"/></td></tr></c:forEach>
</table>
<h2>Confirmation emails waiting</h2>
<ul><c:forEach var="m" items="${pendingEmails}"><li>${m.recipient}: ${m.subject}</li></c:forEach></ul>
<%@ include file="/WEB-INF/jspf/footer.jspf" %>
