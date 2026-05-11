namespace OtterWorks.CollabService.Config;

public class RedisSettings
{
    public string Host { get; set; } = "localhost";

    public int Port { get; set; } = 6379;

    public string? Password { get; set; }

    public int Db { get; set; }

    public string KeyPrefix { get; set; } = "collab:";

    public string ConnectionString =>
        string.IsNullOrEmpty(Password)
            ? $"{Host}:{Port},defaultDatabase={Db},abortConnect=false"
            : $"{Host}:{Port},password={Password},defaultDatabase={Db},abortConnect=false";
}
