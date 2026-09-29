<%@ include file="/WEB-INF/jspf/header.jspf" %>
<c:choose>
<c:when test="${empty order}"><h1>Order not found</h1></c:when>
<c:otherwise>
<h1>You're going!</h1>
<p>Order <strong>${order.order_ref}</strong> for ${order.event_title} at ${order.venue_name} on ${order.starts_at}.</p>
<table><tr><th>Section</th><th>Row</th><th>Seat</th><th>Zone</th><th>Price</th><th>Ticket</th></tr>
<c:forEach var="i" items="${items}"><tr><td>${i.section}</td><td>${i.row_label}</td><td>${i.seat_number}</td><td>${i.zone}</td>
  <td><fmt:formatNumber value="${i.price_cents / 100}" type="currency" currencySymbol="$"/></td><td>${i.ticket_code}</td></tr></c:forEach>
</table>
<ul><c:forEach var="f" items="${fees}"><li>${f.fee_type}: <fmt:formatNumber value="${f.amount_cents / 100}" type="currency" currencySymbol="$"/></li></c:forEach></ul>
<p>Total paid <fmt:formatNumber value="${order.total_cents / 100}" type="currency" currencySymbol="$"/>. A confirmation email is on its way to ${order.email}.</p>
</c:otherwise>
</c:choose>
<%@ include file="/WEB-INF/jspf/footer.jspf" %>
