<%@ include file="/WEB-INF/jspf/header.jspf" %>
<h1>Find my order</h1>
<form method="get" action="${ctx}/app/lookup"><input name="ref" value="${ref}" placeholder="BO-XXXXXXXXXX"><button>Look up</button></form>
<c:if test="${not empty ref && empty order}"><p>No order ${ref}.</p></c:if>
<c:if test="${not empty order}">
  <p>${order.order_ref} &middot; ${order.status} &middot; ${order.event_title} &middot; ${order.starts_at}</p>
  <ul><c:forEach var="i" items="${items}"><li>${i.section} row ${i.row_label} seat ${i.seat_number} ${i.ticket_code}</li></c:forEach></ul>
</c:if>
<%@ include file="/WEB-INF/jspf/footer.jspf" %>
