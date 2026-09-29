<%@ include file="/WEB-INF/jspf/header.jspf" %>
<h1>Payment did not go through</h1>
<p>Order ${order.order_ref} ended as <strong>${order.status}</strong>. Your seats have been released back to sale.</p>
<c:if test="${order.status == 'PAYMENT_TIMEOUT'}"><p>The card processor did not answer in time. You have not been charged.</p></c:if>
<p><a href="${ctx}/app/performance?id=${order.performance_id}">Try again</a></p>
<%@ include file="/WEB-INF/jspf/footer.jspf" %>
