using System.Text.Json;
using OtterWorks.ApiGateway.Middleware;

namespace OtterWorks.ApiGateway.Proxy;

public class ProxyRoute
{
    public string Prefix { get; set; } = string.Empty;
    public string TargetUrl { get; set; } = string.Empty;
}

public class ReverseProxyMiddleware
{
    private readonly RequestDelegate _next;
    private readonly List<ProxyRoute> _routes;
    private readonly CircuitBreakerManager _cbManager;
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly ILogger<ReverseProxyMiddleware> _logger;

    public ReverseProxyMiddleware(
        RequestDelegate next,
        IEnumerable<ProxyRoute> routes,
        CircuitBreakerManager cbManager,
        IHttpClientFactory httpClientFactory,
        ILogger<ReverseProxyMiddleware> logger)
    {
        _next = next;
        _routes = routes.OrderByDescending(r => r.Prefix.Length).ToList();
        _cbManager = cbManager;
        _httpClientFactory = httpClientFactory;
        _logger = logger;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        var path = context.Request.Path.Value ?? string.Empty;

        var route = FindRoute(path);
        if (route == null)
        {
            context.Response.StatusCode = StatusCodes.Status404NotFound;
            context.Response.ContentType = "application/json";
            await context.Response.WriteAsync(JsonSerializer.Serialize(new { error = "route not found" }));
            return;
        }

        var cb = _cbManager.Get(route.Prefix);

        if (!cb.AllowRequest())
        {
            _logger.LogWarning("Circuit breaker {CircuitBreaker} rejected request (state={State})",
                route.Prefix, cb.State);

            context.Response.StatusCode = StatusCodes.Status503ServiceUnavailable;
            context.Response.ContentType = "application/json";
            await context.Response.WriteAsync(JsonSerializer.Serialize(new
            {
                error = "service temporarily unavailable",
                service = route.Prefix,
                reason = "circuit breaker open",
            }));
            return;
        }

        try
        {
            await ForwardRequest(context, route);

            if (context.Response.StatusCode >= 500)
            {
                cb.RecordFailure();
            }
            else
            {
                cb.RecordSuccess();
            }
        }
        catch (Exception ex)
        {
            cb.RecordFailure();
            _logger.LogError(ex, "Proxy error for {Target} {Path}", route.TargetUrl, path);

            if (!context.Response.HasStarted)
            {
                context.Response.StatusCode = StatusCodes.Status502BadGateway;
                context.Response.ContentType = "application/json";
                await context.Response.WriteAsync(JsonSerializer.Serialize(new
                {
                    error = "service unavailable",
                    target = route.Prefix,
                }));
            }
        }
    }

    internal ProxyRoute? FindRoute(string path)
    {
        foreach (var route in _routes)
        {
            if (path.Equals(route.Prefix, StringComparison.Ordinal) ||
                path.StartsWith(route.Prefix + "/", StringComparison.Ordinal))
            {
                return route;
            }
        }

        return null;
    }

    private async Task ForwardRequest(HttpContext context, ProxyRoute route)
    {
        var client = _httpClientFactory.CreateClient("proxy");
        var targetUri = new Uri(new Uri(route.TargetUrl), context.Request.Path + context.Request.QueryString);

        using var requestMessage = new HttpRequestMessage
        {
            Method = new HttpMethod(context.Request.Method),
            RequestUri = targetUri,
        };

        foreach (var header in context.Request.Headers)
        {
            if (!ShouldSkipHeader(header.Key))
            {
                requestMessage.Headers.TryAddWithoutValidation(header.Key, header.Value.ToArray());
            }
        }

        var claims = JwtAuthMiddleware.GetClaims(context);
        if (claims != null)
        {
            var userId = !string.IsNullOrEmpty(claims.Subject) ? claims.Subject : claims.UserId;
            if (!string.IsNullOrEmpty(userId))
            {
                requestMessage.Headers.TryAddWithoutValidation("X-User-ID", userId);
            }
        }

        if (context.Request.ContentLength > 0 || context.Request.Headers.ContainsKey("Transfer-Encoding"))
        {
            requestMessage.Content = new StreamContent(context.Request.Body);
            if (context.Request.ContentType != null)
            {
                requestMessage.Content.Headers.ContentType =
                    System.Net.Http.Headers.MediaTypeHeaderValue.Parse(context.Request.ContentType);
            }
        }

        using var response = await client.SendAsync(requestMessage, HttpCompletionOption.ResponseHeadersRead, context.RequestAborted);

        context.Response.StatusCode = (int)response.StatusCode;

        foreach (var header in response.Headers)
        {
            context.Response.Headers[header.Key] = header.Value.ToArray();
        }

        foreach (var header in response.Content.Headers)
        {
            context.Response.Headers[header.Key] = header.Value.ToArray();
        }

        context.Response.Headers.Remove("transfer-encoding");

        await response.Content.CopyToAsync(context.Response.Body, context.RequestAborted);
    }

    private static bool ShouldSkipHeader(string headerName)
    {
        return headerName.Equals("Host", StringComparison.OrdinalIgnoreCase) ||
               headerName.Equals("Connection", StringComparison.OrdinalIgnoreCase) ||
               headerName.Equals("Transfer-Encoding", StringComparison.OrdinalIgnoreCase);
    }
}
