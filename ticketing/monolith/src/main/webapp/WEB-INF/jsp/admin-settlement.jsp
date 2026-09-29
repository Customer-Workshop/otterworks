<%@ include file="/WEB-INF/jspf/header.jspf" %>
<h1>Promoter settlement</h1>
<form method="post" action="${ctx}/app/admin-settlement"><label>Business date <input name="date" placeholder="YYYY-MM-DD"></label><button>Run settlement</button></form>
<c:if test="${not empty runSummary}"><ul><c:forEach var="l" items="${runSummary}"><li>${l}</li></c:forEach></ul></c:if>
<table><tr><th>Date</th><th>Promoter</th><th>Orders</th><th>Gross</th><th>Refunds</th><th>Net payout</th><th>Status</th></tr>
<c:forEach var="b" items="${batches}"><tr><td>${b.business_date}</td><td>${b.promoter_name}</td><td>${b.order_count}</td>
  <td><fmt:formatNumber value="${b.gross_cents / 100}" type="currency" currencySymbol="$"/></td>
  <td><fmt:formatNumber value="${b.refunds_cents / 100}" type="currency" currencySymbol="$"/></td>
  <td><fmt:formatNumber value="${b.net_payout_cents / 100}" type="currency" currencySymbol="$"/></td><td>${b.status}</td></tr></c:forEach>
</table>
<%@ include file="/WEB-INF/jspf/footer.jspf" %>
