namespace OtterWorks.AnalyticsService.Config;

public class RedisSettings
{
    public string Host { get; set; } = "localhost";

    public int Port { get; set; } = 6379;

    public string ConnectionString => $"{Host}:{Port}";
}
