<%@ include file="/WEB-INF/jspf/header.jspf" %>
<h1>Events</h1>
<form method="get" action="${ctx}/app/events"><input name="q" value="${q}" placeholder="Search events or performers"><button>Search</button></form>
<table><tr><th>Event</th><th>Category</th></tr>
<c:forEach var="e" items="${events}">
  <tr><td><a href="${ctx}/app/event?id=${e.id}">${e.title}</a></td><td>${e.category}</td></tr>
</c:forEach>
</table>
<c:if test="${empty events}"><p>No events match.</p></c:if>
<%@ include file="/WEB-INF/jspf/footer.jspf" %>
