namespace OtterWorks.CollabService.Config;

public class JwtSettings
{
    public string Secret { get; set; } = "otterworks-dev-secret";

    public string Issuer { get; set; } = "otterworks-auth-service";
}
