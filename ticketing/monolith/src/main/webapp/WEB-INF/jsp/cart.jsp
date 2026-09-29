<%@ include file="/WEB-INF/jspf/header.jspf" %>
<h1>Your cart</h1>
<c:choose>
<c:when test="${empty hold}"><p>Your cart is empty. <a href="${ctx}/app/events">Browse events</a>.</p></c:when>
<c:otherwise>
  <p>Hold ${hold.hold_ref} expires at ${hold.expires_at}.</p>
  <table><tr><th>Section</th><th>Row</th><th>Seat</th><th>Zone</th></tr>
  <c:forEach var="s" items="${seats}"><tr><td>${s.section}</td><td>${s.row_label}</td><td>${s.seat_number}</td><td>${s.zone}</td></tr></c:forEach>
  </table>
  <p>Subtotal <fmt:formatNumber value="${quote.subtotalCents / 100}" type="currency" currencySymbol="$"/> &middot;
     fees <fmt:formatNumber value="${quote.feesCents / 100}" type="currency" currencySymbol="$"/></p>
  <a class="button" href="${ctx}/app/checkout">Checkout</a>
</c:otherwise>
</c:choose>
<%@ include file="/WEB-INF/jspf/footer.jspf" %>
