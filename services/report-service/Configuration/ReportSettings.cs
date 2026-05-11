namespace OtterWorks.ReportService.Configuration;

public class ReportSettings
{
    public string AnalyticsServiceUrl { get; set; } = "http://analytics-service:8088";

    public string AuditServiceUrl { get; set; } = "http://audit-service:8090";

    public string AuthServiceUrl { get; set; } = "http://auth-service:8081";

    public string OutputDir { get; set; } = "/tmp/reports";

    public int MaxRows { get; set; } = 50000;

    public int ConnectionTimeoutMs { get; set; } = 5000;

    public int ReadTimeoutMs { get; set; } = 30000;
}
