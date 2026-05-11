namespace OtterWorks.ApiGateway.Config;

public class GatewaySettings
{
    public int RateLimitRequestsPerSecond { get; set; } = 100;

    public string CorsAllowedOrigins { get; set; } = "http://localhost:3000,http://localhost:4200";
    public string CorsAllowedMethods { get; set; } = "GET,POST,PUT,PATCH,DELETE,OPTIONS";
    public string CorsAllowedHeaders { get; set; } = "Accept,Authorization,Content-Type,X-Request-ID";
    public int CorsMaxAgeSeconds { get; set; } = 300;

    public int ShutdownTimeoutSeconds { get; set; } = 30;

    public uint CircuitBreakerMaxRequests { get; set; } = 5;
    public int CircuitBreakerIntervalSeconds { get; set; } = 60;
    public int CircuitBreakerTimeoutSeconds { get; set; } = 30;
    public double CircuitBreakerFailureRatio { get; set; } = 0.6;

    public string[] GetAllowedOrigins() => CorsAllowedOrigins.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

    public string[] GetAllowedMethods() => CorsAllowedMethods.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

    public string[] GetAllowedHeaders() => CorsAllowedHeaders.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
}
