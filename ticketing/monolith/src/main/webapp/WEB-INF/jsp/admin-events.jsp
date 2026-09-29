<%@ include file="/WEB-INF/jspf/header.jspf" %>
<h1>Performances</h1>
<table><tr><th>Id</th><th>Event</th><th>Venue</th><th>Starts</th><th>Status</th><th></th></tr>
<c:forEach var="p" items="${performances}"><tr><td>${p.id}</td><td>${p.event_title}</td><td>${p.venue_name}</td><td>${p.starts_at}</td><td>${p.status}</td>
  <td><a href="${ctx}/app/admin-performance?id=${p.id}">Edit</a></td></tr></c:forEach>
</table>
<h2>Venues</h2>
<ul><c:forEach var="v" items="${venues}"><li>${v.name}, ${v.city} (${v.capacity})</li></c:forEach></ul>
<%@ include file="/WEB-INF/jspf/footer.jspf" %>
