<%@ include file="/WEB-INF/jspf/header.jspf" %>
<h1>Performance ${perf.id} &middot; ${perf.event_title}</h1>
<form method="post" action="${ctx}/app/admin-performance?id=${perf.id}">
  <label>Status <select name="status"><c:forEach var="s" items="SCHEDULED,ON_HOLD,CANCELLED"><option ${perf.status == s ? 'selected' : ''}>${s}</option></c:forEach></select></label>
  <label>Max per order <input name="maxPerOrder" value="${perf.max_per_order}" size="2"></label>
  <button>Save</button>
</form>
<table><tr><th>Section</th><th>Zone</th><th>Available</th><th>Held</th><th>Sold</th></tr>
<c:forEach var="s" items="${sections}"><tr><td>${s.code}</td><td>${s.zone}</td><td>${s.available}</td><td>${s.held}</td><td>${s.sold}</td></tr></c:forEach>
</table>
<%@ include file="/WEB-INF/jspf/footer.jspf" %>
