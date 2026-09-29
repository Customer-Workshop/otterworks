<%@ include file="/WEB-INF/jspf/header.jspf" %>
<h1>On sale now</h1>
<ul class="cards">
<c:forEach var="e" items="${events}">
  <li class="card"><a href="${ctx}/app/event?id=${e.id}"><strong>${e.title}</strong></a>
    <span>${e.category} &middot; ${e.promoter_name} &middot; ${e.performance_count} shows from ${e.first_show}</span></li>
</c:forEach>
</ul>
<%@ include file="/WEB-INF/jspf/footer.jspf" %>
