using OtterWorks.ApiGateway.Proxy;

namespace ApiGateway.Tests.Unit;

public class CircuitBreakerTests
{
    private static CircuitBreakerConfig DefaultTestConfig() => new()
    {
        MaxRequests = 2,
        Interval = TimeSpan.FromSeconds(60),
        Timeout = TimeSpan.FromSeconds(10),
        FailureRatio = 0.5,
    };

    [Fact]
    public void StartsInClosedState()
    {
        var cb = new CircuitBreaker("test-svc", DefaultTestConfig());
        Assert.Equal(CircuitState.Closed, cb.State);
    }

    [Fact]
    public void SuccessfulRequests_KeepClosed()
    {
        var cb = new CircuitBreaker("test-svc", DefaultTestConfig());

        for (var i = 0; i < 10; i++)
        {
            Assert.True(cb.AllowRequest());
            cb.RecordSuccess();
        }

        Assert.Equal(CircuitState.Closed, cb.State);
    }

    [Fact]
    public void TripsOnFailures()
    {
        var config = new CircuitBreakerConfig
        {
            MaxRequests = 2,
            Interval = TimeSpan.FromSeconds(60),
            Timeout = TimeSpan.FromSeconds(10),
            FailureRatio = 0.5,
        };
        var cb = new CircuitBreaker("test-svc", config);

        for (var i = 0; i < 6; i++)
        {
            cb.AllowRequest();
            cb.RecordFailure();
        }

        Assert.Equal(CircuitState.Open, cb.State);

        Assert.False(cb.AllowRequest(), "Should reject when open");
    }

    [Fact]
    public void TransitionsToHalfOpen()
    {
        var config = new CircuitBreakerConfig
        {
            MaxRequests = 2,
            Interval = TimeSpan.FromSeconds(60),
            Timeout = TimeSpan.FromSeconds(5),
            FailureRatio = 0.5,
        };
        var cb = new CircuitBreaker("test-svc", config);

        var now = DateTime.UtcNow;
        cb.Now = () => now;

        for (var i = 0; i < 6; i++)
        {
            cb.AllowRequest();
            cb.RecordFailure();
        }

        Assert.Equal(CircuitState.Open, cb.State);

        cb.Now = () => now.AddSeconds(6);
        Assert.Equal(CircuitState.HalfOpen, cb.State);
    }

    [Fact]
    public void RecoveryFromHalfOpen()
    {
        var config = new CircuitBreakerConfig
        {
            MaxRequests = 2,
            Interval = TimeSpan.FromSeconds(60),
            Timeout = TimeSpan.FromSeconds(5),
            FailureRatio = 0.5,
        };
        var cb = new CircuitBreaker("test-svc", config);

        var now = DateTime.UtcNow;
        cb.Now = () => now;

        for (var i = 0; i < 6; i++)
        {
            cb.AllowRequest();
            cb.RecordFailure();
        }

        Assert.Equal(CircuitState.Open, cb.State);

        cb.Now = () => now.AddSeconds(6);

        for (var i = 0; i < 2; i++)
        {
            Assert.True(cb.AllowRequest());
            cb.RecordSuccess();
        }

        Assert.Equal(CircuitState.Closed, cb.State);
    }

    [Fact]
    public void Manager_GetOrCreate()
    {
        var mgr = new CircuitBreakerManager(DefaultTestConfig());

        var cb1 = mgr.Get("service-a");
        var cb2 = mgr.Get("service-a");
        var cb3 = mgr.Get("service-b");

        Assert.Same(cb1, cb2);
        Assert.NotSame(cb1, cb3);
    }

    [Fact]
    public void CircuitState_StringValues()
    {
        Assert.Equal("Closed", CircuitState.Closed.ToString());
        Assert.Equal("Open", CircuitState.Open.ToString());
        Assert.Equal("HalfOpen", CircuitState.HalfOpen.ToString());
    }
}
