using System.Collections.Concurrent;

namespace OtterWorks.ApiGateway.Proxy;

public class CircuitBreakerManager
{
    private readonly ConcurrentDictionary<string, CircuitBreaker> _breakers = new();
    private readonly CircuitBreakerConfig _config;

    public CircuitBreakerManager(CircuitBreakerConfig config)
    {
        _config = config;
    }

    public CircuitBreaker Get(string name)
    {
        return _breakers.GetOrAdd(name, n => new CircuitBreaker(n, _config));
    }
}
