using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text;
using Microsoft.Extensions.Options;
using Microsoft.IdentityModel.Tokens;
using OtterWorks.AuthService.Config;
using OtterWorks.AuthService.Data.Entities;

namespace OtterWorks.AuthService.Services;

public sealed class JwtTokenProvider : IJwtTokenProvider
{
    private readonly SymmetricSecurityKey _key;
    private readonly JwtSettings _settings;

    public JwtTokenProvider(IOptions<JwtSettings> settings)
    {
        _settings = settings.Value;
        _key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(_settings.Secret));
    }

    public long AccessTokenExpiry => _settings.AccessTokenExpirySeconds;

    public long RefreshTokenExpiry => _settings.RefreshTokenExpirySeconds;

    public string GenerateAccessToken(User user)
    {
        var now = DateTime.UtcNow;
        var claims = new List<Claim>
        {
            new(JwtRegisteredClaimNames.Sub, user.Id.ToString()),
            new("email", user.Email),
            new("name", user.DisplayName),
            new("type", "access"),
        };

        foreach (var role in user.UserRoles)
        {
            claims.Add(new Claim("roles", role.Role));
        }

        var tokenDescriptor = new SecurityTokenDescriptor
        {
            Subject = new ClaimsIdentity(claims),
            Expires = now.AddSeconds(_settings.AccessTokenExpirySeconds),
            IssuedAt = now,
            SigningCredentials = new SigningCredentials(_key, SecurityAlgorithms.HmacSha256),
        };

        var handler = new JwtSecurityTokenHandler();
        var token = handler.CreateToken(tokenDescriptor);
        return handler.WriteToken(token);
    }

    public string GenerateRefreshToken(User user)
    {
        var now = DateTime.UtcNow;
        var jti = Guid.NewGuid().ToString();
        var claims = new List<Claim>
        {
            new(JwtRegisteredClaimNames.Sub, user.Id.ToString()),
            new(JwtRegisteredClaimNames.Jti, jti),
            new("type", "refresh"),
        };

        var tokenDescriptor = new SecurityTokenDescriptor
        {
            Subject = new ClaimsIdentity(claims),
            Expires = now.AddSeconds(_settings.RefreshTokenExpirySeconds),
            IssuedAt = now,
            SigningCredentials = new SigningCredentials(_key, SecurityAlgorithms.HmacSha256),
        };

        var handler = new JwtSecurityTokenHandler();
        var token = handler.CreateToken(tokenDescriptor);
        return handler.WriteToken(token);
    }

    public ClaimsPrincipal ValidateAndGetClaims(string token)
    {
        var handler = new JwtSecurityTokenHandler
        {
            MapInboundClaims = false,
        };
        var validationParams = new TokenValidationParameters
        {
            ValidateIssuerSigningKey = true,
            IssuerSigningKey = _key,
            ValidateIssuer = false,
            ValidateAudience = false,
            ValidateLifetime = true,
            ClockSkew = TimeSpan.Zero,
        };

        return handler.ValidateToken(token, validationParams, out _);
    }

    public string ValidateTokenAndGetUserId(string token)
    {
        var principal = ValidateAndGetClaims(token);
        var typeClaim = principal.FindFirst("type")?.Value;
        if (typeClaim == "refresh")
        {
            throw new ArgumentException("Refresh token cannot be used as access token");
        }

        return principal.FindFirst(JwtRegisteredClaimNames.Sub)?.Value
            ?? principal.FindFirst(ClaimTypes.NameIdentifier)?.Value
            ?? throw new ArgumentException("Token does not contain a subject");
    }

    public string ValidateRefreshTokenAndGetUserId(string token)
    {
        var principal = ValidateAndGetClaims(token);
        var typeClaim = principal.FindFirst("type")?.Value;
        if (typeClaim != "refresh")
        {
            throw new ArgumentException("Token is not a refresh token");
        }

        return principal.FindFirst(JwtRegisteredClaimNames.Sub)?.Value
            ?? principal.FindFirst(ClaimTypes.NameIdentifier)?.Value
            ?? throw new ArgumentException("Token does not contain a subject");
    }

    public string ExtractJti(string token)
    {
        var principal = ValidateAndGetClaims(token);
        return principal.FindFirst(JwtRegisteredClaimNames.Jti)?.Value
            ?? throw new ArgumentException("Token does not contain a JTI");
    }

    public bool IsTokenValid(string token)
    {
        try
        {
            ValidateAndGetClaims(token);
            return true;
        }
        catch
        {
            return false;
        }
    }
}
