namespace OtterWorks.AnalyticsService.Config;

public class PostgresSettings
{
    public string Host { get; set; } = "localhost";

    public int Port { get; set; } = 5432;

    public string User { get; set; } = "otterworks";

    public string Password { get; set; } = "otterworks_dev";

    public string Database { get; set; } = "otterworks";

    public string ConnectionString =>
        $"Host={Host};Port={Port};Database={Database};Username={User};Password={Password}";
}
