namespace OtterWorks.AnalyticsService.Config;

public class AwsSettings
{
    public string Region { get; set; } = "us-east-1";

    public string? EndpointUrl { get; set; }

    public string DataLakeBucket { get; set; } = "otterworks-data-lake";
}
