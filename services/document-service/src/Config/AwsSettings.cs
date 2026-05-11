namespace OtterWorks.DocumentService.Config;

public class AwsSettings
{
    public string Region { get; set; } = "us-east-1";

    public string EndpointUrl { get; set; } = string.Empty;

    public string SnsTopicArn { get; set; } = string.Empty;

    public bool SnsEnabled { get; set; }
}
