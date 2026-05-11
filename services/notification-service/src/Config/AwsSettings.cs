namespace OtterWorks.NotificationService.Config;

public class AwsSettings
{
    public string Region { get; set; } = "us-east-1";
    public string? EndpointUrl { get; set; }
    public string DynamoDbTableNotifications { get; set; } = "otterworks-notifications";
    public string DynamoDbTablePreferences { get; set; } = "otterworks-notification-preferences";
    public string SqsQueueUrl { get; set; } = "http://localhost:4566/000000000000/otterworks-notifications";
    public string SnsTopicArn { get; set; } = "arn:aws:sns:us-east-1:000000000000:otterworks-events";
    public string SesFromEmail { get; set; } = "notifications@otterworks.io";
    public int SqsMaxMessages { get; set; } = 10;
    public int SqsWaitTimeSeconds { get; set; } = 20;
    public int SqsPollIntervalMs { get; set; } = 5000;
}
