namespace OtterWorks.ApiGateway.Health;

public static class HealthEndpoints
{
    private const string Version = "0.1.0";

    public static void MapHealthEndpoints(this WebApplication app)
    {
        app.MapGet("/health", () => Results.Ok(new HealthResponse
        {
            Status = "healthy",
            Service = "api-gateway",
            Version = Version,
        }));
    }
}

public class HealthResponse
{
    public string Status { get; set; } = "healthy";
    public string Service { get; set; } = "api-gateway";
    public string Version { get; set; } = "0.1.0";
}
