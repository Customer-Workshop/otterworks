namespace OtterWorks.ReportService.Config;

public class ServiceUrlsSettings
{
    public string Analytics { get; set; } = "http://analytics-service:8088";
    public string Audit { get; set; } = "http://audit-service:8090";
    public string Auth { get; set; } = "http://auth-service:8081";
}
