namespace OtterWorks.CollabService.Config;

public class CorsSettings
{
    public string Origins { get; set; } = "http://localhost:3000,http://localhost:4200";

    public string[] GetOrigins() => Origins.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
}
