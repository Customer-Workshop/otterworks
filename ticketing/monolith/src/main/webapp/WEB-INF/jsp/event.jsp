<%@ include file="/WEB-INF/jspf/header.jspf" %>
<h1>${event.title}</h1>
<p>${event.description} Presented by ${event.promoter_name}.</p>
<p>Featuring: <c:forEach var="p" items="${performers}" varStatus="s">${p.name}<c:if test="${!s.last}">, </c:if></c:forEach></p>
<table><tr><th>Date</th><th>Venue</th><th>Available</th><th></th></tr>
<c:forEach var="p" items="${performances}">
  <tr><td>${p.starts_at}</td><td>${p.venue_name}, ${p.city}</td><td>${p.available}</td>
      <td><a href="${ctx}/app/performance?id=${p.id}">Choose seats</a></td></tr>
</c:forEach>
</table>
<%@ include file="/WEB-INF/jspf/footer.jspf" %>
