namespace OtterWorks.SearchService.Config;

public class SqsSettings
{
    public bool Enabled { get; set; }
    public string QueueUrl { get; set; } = string.Empty;
    public string Region { get; set; } = "us-east-1";
    public string? EndpointUrl { get; set; }
    public int MaxMessages { get; set; } = 10;
    public int WaitTimeSeconds { get; set; } = 20;
    public int VisibilityTimeout { get; set; } = 60;
}
