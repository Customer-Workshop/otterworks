using System.Collections.Concurrent;
using System.Text.Json;

namespace OtterWorks.ApiGateway.Middleware;

public class TokenBucket
{
    public double Tokens { get; set; }
    public double MaxTokens { get; set; }
    public double RefillRate { get; set; }
    public DateTime LastRefill { get; set; }
}

public class RateLimiter : IDisposable
{
    private readonly ConcurrentDictionary<string, TokenBucket> _buckets = new();
    private readonly int _rps;
    private readonly Timer _cleanupTimer;
    private bool _disposed;
    internal Func<DateTime> Now { get; set; } = () => DateTime.UtcNow;

    public RateLimiter(int rps)
    {
        _rps = rps;
        _cleanupTimer = new Timer(Cleanup, null, TimeSpan.FromMinutes(5), TimeSpan.FromMinutes(5));
    }

    public void Dispose()
    {
        Dispose(true);
        GC.SuppressFinalize(this);
    }

    protected virtual void Dispose(bool disposing)
    {
        if (!_disposed)
        {
            if (disposing)
            {
                _cleanupTimer.Dispose();
            }

            _disposed = true;
        }
    }

    public bool Allow(string ip)
    {
        var now = Now();
        var bucket = _buckets.GetOrAdd(ip, _ => new TokenBucket
        {
            Tokens = _rps,
            MaxTokens = _rps,
            RefillRate = _rps,
            LastRefill = now,
        });

        lock (bucket)
        {
            var elapsed = (now - bucket.LastRefill).TotalSeconds;
            bucket.Tokens += elapsed * bucket.RefillRate;
            if (bucket.Tokens > bucket.MaxTokens)
            {
                bucket.Tokens = bucket.MaxTokens;
            }

            bucket.LastRefill = now;

            if (bucket.Tokens >= 1)
            {
                bucket.Tokens--;
                return true;
            }

            return false;
        }
    }

    private void Cleanup(object? state)
    {
        var now = Now();
        foreach (var kvp in _buckets)
        {
            if ((now - kvp.Value.LastRefill).TotalMinutes > 10)
            {
                _buckets.TryRemove(kvp.Key, out _);
            }
        }
    }
}

public class RateLimitMiddleware
{
    private readonly RequestDelegate _next;
    private readonly RateLimiter _rateLimiter;

    public RateLimitMiddleware(RequestDelegate next, RateLimiter rateLimiter)
    {
        _next = next;
        _rateLimiter = rateLimiter;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        var ip = ExtractIp(context);
        if (!_rateLimiter.Allow(ip))
        {
            context.Response.StatusCode = StatusCodes.Status429TooManyRequests;
            context.Response.ContentType = "application/json";
            context.Response.Headers["Retry-After"] = "1";
            var error = new { error = "rate limit exceeded" };
            await context.Response.WriteAsync(JsonSerializer.Serialize(error));
            return;
        }

        await _next(context);
    }

    internal static string ExtractIp(HttpContext context)
    {
        var forwarded = context.Request.Headers["X-Forwarded-For"].FirstOrDefault();
        if (!string.IsNullOrEmpty(forwarded))
        {
            return forwarded.Split(',')[0].Trim();
        }

        return context.Connection.RemoteIpAddress?.ToString() ?? "unknown";
    }
}
