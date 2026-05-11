namespace OtterWorks.SearchService.Configuration;

public class MeiliSearchSettings
{
    public string Url { get; set; } = "http://localhost:7700";
    public string ApiKey { get; set; } = string.Empty;
    public string DocumentsIndex { get; set; } = "documents";
    public string FilesIndex { get; set; } = "files";
}

public class SqsSettings
{
    public bool Enabled { get; set; }
    public string QueueUrl { get; set; } = string.Empty;
    public string Region { get; set; } = "us-east-1";
    public string EndpointUrl { get; set; } = string.Empty;
    public int MaxMessages { get; set; } = 10;
    public int WaitTimeSeconds { get; set; } = 20;
    public int VisibilityTimeout { get; set; } = 60;
}

public class AuthSettings
{
    public string ServiceToken { get; set; } = string.Empty;
    public bool RequireAuth { get; set; } = true;
}

public class SearchServiceSettings
{
    public string ServiceName { get; set; } = "search-service";
    public int Port { get; set; } = 8087;
    public MeiliSearchSettings MeiliSearch { get; set; } = new();
    public SqsSettings Sqs { get; set; } = new();
    public AuthSettings Auth { get; set; } = new();
}
