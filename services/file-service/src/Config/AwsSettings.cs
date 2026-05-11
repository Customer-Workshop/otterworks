namespace OtterWorks.FileService.Config;

public class AwsSettings
{
    public string Region { get; set; } = "us-east-1";

    public string? EndpointUrl { get; set; }

    public string S3Bucket { get; set; } = "otterworks-files";

    public string DynamoDbTable { get; set; } = "otterworks-file-metadata";

    public string DynamoDbFoldersTable { get; set; } = "otterworks-folders";

    public string DynamoDbVersionsTable { get; set; } = "otterworks-file-versions";

    public string DynamoDbSharesTable { get; set; } = "otterworks-file-shares";

    public string? SnsTopicArn { get; set; }

    public long MaxUploadBytes { get; set; } = 104_857_600;
}
