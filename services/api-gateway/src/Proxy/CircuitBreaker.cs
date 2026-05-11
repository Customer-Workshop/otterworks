namespace OtterWorks.ApiGateway.Proxy;

public enum CircuitState
{
    Closed,
    Open,
    HalfOpen,
}

public class CircuitBreakerConfig
{
    public uint MaxRequests { get; set; } = 5;
    public TimeSpan Interval { get; set; } = TimeSpan.FromSeconds(60);
    public TimeSpan Timeout { get; set; } = TimeSpan.FromSeconds(30);
    public double FailureRatio { get; set; } = 0.6;
}

public class CircuitBreaker
{
    private readonly object _lock = new();
    private readonly string _name;
    private readonly CircuitBreakerConfig _config;
    private CircuitState _state = CircuitState.Closed;
    private Counts _counts = new();
    private DateTime _expiry = DateTime.MinValue;

    internal Func<DateTime> Now { get; set; } = () => DateTime.UtcNow;

    public CircuitBreaker(string name, CircuitBreakerConfig config)
    {
        _name = name;
        _config = config;
    }

    public CircuitState State
    {
        get
        {
            lock (_lock)
            {
                return CurrentState();
            }
        }
    }

    public bool AllowRequest()
    {
        lock (_lock)
        {
            var state = CurrentState();
            if (state == CircuitState.Open)
            {
                return false;
            }

            if (state == CircuitState.HalfOpen && _counts.Requests >= _config.MaxRequests)
            {
                return false;
            }

            _counts.Requests++;
            return true;
        }
    }

    public void RecordSuccess()
    {
        lock (_lock)
        {
            _counts.OnSuccess();
            if (_state == CircuitState.HalfOpen && _counts.ConsecutiveSuccesses >= _config.MaxRequests)
            {
                SetState(CircuitState.Closed, Now());
            }
        }
    }

    public void RecordFailure()
    {
        lock (_lock)
        {
            _counts.OnFailure();
            var now = Now();
            switch (_state)
            {
                case CircuitState.Closed:
                    if (ShouldTrip())
                    {
                        SetState(CircuitState.Open, now);
                    }

                    break;
                case CircuitState.HalfOpen:
                    SetState(CircuitState.Open, now);
                    break;
            }
        }
    }

    private CircuitState CurrentState()
    {
        var now = Now();
        switch (_state)
        {
            case CircuitState.Closed:
                if (_expiry != DateTime.MinValue && _expiry < now)
                {
                    ToNewGeneration(now);
                }

                break;
            case CircuitState.Open:
                if (_expiry < now)
                {
                    SetState(CircuitState.HalfOpen, now);
                }

                break;
        }

        return _state;
    }

    private void SetState(CircuitState state, DateTime now)
    {
        _state = state;
        _counts = new Counts();

        switch (state)
        {
            case CircuitState.Closed:
                _expiry = _config.Interval > TimeSpan.Zero ? now.Add(_config.Interval) : DateTime.MinValue;
                break;
            case CircuitState.Open:
                _expiry = now.Add(_config.Timeout);
                break;
            case CircuitState.HalfOpen:
                _expiry = DateTime.MinValue;
                break;
        }
    }

    private void ToNewGeneration(DateTime now)
    {
        _counts = new Counts();
        _expiry = _config.Interval > TimeSpan.Zero ? now.Add(_config.Interval) : DateTime.MinValue;
    }

    private bool ShouldTrip()
    {
        var total = _counts.TotalSuccesses + _counts.TotalFailures;
        if (total < 5)
        {
            return false;
        }

        var ratio = (double)_counts.TotalFailures / total;
        return ratio >= _config.FailureRatio;
    }

    private class Counts
    {
        public uint Requests { get; set; }
        public uint TotalSuccesses { get; set; }
        public uint TotalFailures { get; set; }
        public uint ConsecutiveSuccesses { get; set; }
        public uint ConsecutiveFailures { get; set; }

        public void OnSuccess()
        {
            TotalSuccesses++;
            ConsecutiveSuccesses++;
            ConsecutiveFailures = 0;
        }

        public void OnFailure()
        {
            TotalFailures++;
            ConsecutiveFailures++;
            ConsecutiveSuccesses = 0;
        }
    }
}
