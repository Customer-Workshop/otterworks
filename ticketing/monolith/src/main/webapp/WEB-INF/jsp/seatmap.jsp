<%@ include file="/WEB-INF/jspf/header.jspf" %>
<h1>Seat map &middot; ${perf.event_title}</h1>
<p>${perf.venue_name} (capacity ${perf.capacity})</p>
<table><tr><th>Section</th><th>Zone</th><th>Face value</th><th>Available</th><th>Held</th><th>Sold</th></tr>
<c:forEach var="s" items="${sections}">
  <tr><td>${s.code} ${s.name}</td><td>${s.zone}</td><td><fmt:formatNumber value="${s.face_value_cents / 100}" type="currency" currencySymbol="$"/></td>
      <td>${s.available}</td><td>${s.held}</td><td>${s.sold}</td></tr>
</c:forEach>
</table>
<p><a href="${ctx}/app/performance?id=${perf.id}">Back to ticket selection</a></p>
<%@ include file="/WEB-INF/jspf/footer.jspf" %>
