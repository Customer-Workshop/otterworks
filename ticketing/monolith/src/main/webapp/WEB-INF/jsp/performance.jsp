<%@ include file="/WEB-INF/jspf/header.jspf" %>
<h1>${perf.event_title}</h1>
<p>${perf.venue_name}, ${perf.city} &middot; doors ${perf.doors_at} &middot; show ${perf.starts_at}</p>
<p>Available ${counts.available} &middot; held ${counts.held} &middot; sold ${counts.sold}</p>
<form method="post" action="${ctx}/app/hold">
  <input type="hidden" name="performanceId" value="${perf.id}">
  <label>Tickets <select name="quantity"><c:forEach begin="1" end="${perf.max_per_order}" var="n"><option>${n}</option></c:forEach></select></label>
  <label>Section (optional) <input name="section" size="4"></label>
  <button>Find best available</button>
</form>
<p><a href="${ctx}/app/seatmap?id=${perf.id}">View seat map</a></p>
<%@ include file="/WEB-INF/jspf/footer.jspf" %>
