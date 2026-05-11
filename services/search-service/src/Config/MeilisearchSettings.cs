namespace OtterWorks.SearchService.Config;

public class MeilisearchSettings
{
    public string Url { get; set; } = "http://localhost:7700";
    public string ApiKey { get; set; } = string.Empty;
    public string DocumentsIndex { get; set; } = "documents";
    public string FilesIndex { get; set; } = "files";
}
