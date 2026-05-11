namespace OtterWorks.ApiGateway.Config;

public class AwsSettings
{
    public string Region { get; set; } = "us-east-1";
    public string? EndpointUrl { get; set; }
    public string S3Bucket { get; set; } = "otterworks-gateway-assets";
    public string? SnsTopicArn { get; set; }
    public string? SqsQueueUrl { get; set; }
}
