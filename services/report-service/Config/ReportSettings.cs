namespace OtterWorks.ReportService.Config;

public class ReportSettings
{
    public string OutputDir { get; set; } = "/tmp/reports";
    public int MaxRows { get; set; } = 50000;
    public int ConnectionTimeoutMs { get; set; } = 5000;
    public int ReadTimeoutMs { get; set; } = 30000;
}
