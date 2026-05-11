namespace OtterWorks.AuthService.Config;

public sealed class JwtSettings
{
    public string Secret { get; set; } = string.Empty;
    public long AccessTokenExpirySeconds { get; set; } = 3600;
    public long RefreshTokenExpirySeconds { get; set; } = 2592000;
}
