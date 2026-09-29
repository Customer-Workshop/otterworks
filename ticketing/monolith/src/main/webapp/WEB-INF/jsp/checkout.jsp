<%@ include file="/WEB-INF/jspf/header.jspf" %>
<h1>Checkout</h1>
<p>Hold ${hold.hold_ref} &middot; ${quote.seatCount} seat(s) &middot; expires ${hold.expires_at}</p>
<form method="post" action="${ctx}/app/checkout">
  <label>Promo code <input name="promoCode" value="${promoCode}"></label>
  <label>Delivery <select name="delivery">
    <option value="MOBILE" ${delivery == 'MOBILE' ? 'selected' : ''}>Mobile ticket</option>
    <option value="PRINT" ${delivery == 'PRINT' ? 'selected' : ''}>Print at home</option>
    <option value="WILLCALL" ${delivery == 'WILLCALL' ? 'selected' : ''}>Will call</option></select></label>
  <button>Update total</button>
</form>
<table>
  <tr><td>Tickets</td><td><fmt:formatNumber value="${quote.subtotalCents / 100}" type="currency" currencySymbol="$"/></td></tr>
  <tr><td>Service fee</td><td><fmt:formatNumber value="${quote.serviceFeeCents / 100}" type="currency" currencySymbol="$"/></td></tr>
  <tr><td>Facility fee</td><td><fmt:formatNumber value="${quote.facilityFeeCents / 100}" type="currency" currencySymbol="$"/></td></tr>
  <tr><td>Delivery</td><td><fmt:formatNumber value="${quote.deliveryFeeCents / 100}" type="currency" currencySymbol="$"/></td></tr>
  <tr><th>Total</th><th><fmt:formatNumber value="${quote.totalCents / 100}" type="currency" currencySymbol="$"/></th></tr>
</table>
<form method="post" action="${ctx}/app/pay">
  <label>Email <input name="email" type="email" required></label>
  <label>Name <input name="fullName"></label>
  <label>Card (last 4, synthetic) <input name="cardLast4" value="4242" size="4"></label>
  <button>Pay now</button>
</form>
<%@ include file="/WEB-INF/jspf/footer.jspf" %>
