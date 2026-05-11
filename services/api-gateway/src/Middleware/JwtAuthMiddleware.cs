using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text;
using System.Text.Json;
using Microsoft.IdentityModel.Tokens;

namespace OtterWorks.ApiGateway.Middleware;

public class JwtClaims
{
    public string UserId { get; set; } = string.Empty;
    public string Email { get; set; } = string.Empty;
    public List<string> Roles { get; set; } = [];
    public string Subject { get; set; } = string.Empty;
}

public class JwtAuthMiddleware
{
    private static readonly string[] DefaultPublicPaths =
    [
        "/api/v1/auth/login",
        "/api/v1/auth/register",
    ];

    private static readonly string[] DefaultPrefixPaths =
    [
        "/health",
        "/metrics",
        "/socket.io",
    ];

    private readonly RequestDelegate _next;
    private readonly string _secret;
    private readonly HashSet<string> _publicPaths;
    private readonly string[] _prefixPaths;

    public JwtAuthMiddleware(RequestDelegate next, IConfiguration configuration)
    {
        _next = next;
        _secret = configuration["JWT_SECRET"]
            ?? Environment.GetEnvironmentVariable("JWT_SECRET")
            ?? string.Empty;
        _publicPaths = new HashSet<string>(DefaultPublicPaths, StringComparer.Ordinal);
        _prefixPaths = DefaultPrefixPaths;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        var path = context.Request.Path.Value ?? string.Empty;

        if (IsPublicPath(path))
        {
            await _next(context);
            return;
        }

        var token = ExtractBearerToken(context);
        if (string.IsNullOrEmpty(token))
        {
            await WriteJsonError(context, StatusCodes.Status401Unauthorized, "missing or invalid authorization header");
            return;
        }

        var claims = ValidateToken(token);
        if (claims == null)
        {
            await WriteJsonError(context, StatusCodes.Status401Unauthorized, "invalid token");
            return;
        }

        context.Items["JwtClaims"] = claims;

        await _next(context);
    }

    public static JwtClaims? GetClaims(HttpContext context)
    {
        return context.Items["JwtClaims"] as JwtClaims;
    }

    internal static bool IsPublicPathStatic(string path, HashSet<string> publicPaths, string[] prefixPaths)
    {
        if (publicPaths.Contains(path))
        {
            return true;
        }

        foreach (var prefix in prefixPaths)
        {
            if (path.Equals(prefix, StringComparison.Ordinal) ||
                path.StartsWith(prefix + "/", StringComparison.Ordinal))
            {
                return true;
            }
        }

        return false;
    }

    internal static string ExtractBearerTokenFromHeader(string? authHeader)
    {
        if (string.IsNullOrEmpty(authHeader))
        {
            return string.Empty;
        }

        var parts = authHeader.Split(' ', 2);
        if (parts.Length != 2 || !parts[0].Equals("Bearer", StringComparison.OrdinalIgnoreCase))
        {
            return string.Empty;
        }

        return parts[1];
    }

    internal JwtClaims? ValidateToken(string tokenStr)
    {
        if (string.IsNullOrEmpty(_secret))
        {
            return null;
        }

        try
        {
            var tokenHandler = new JwtSecurityTokenHandler();
            var key = Encoding.UTF8.GetBytes(_secret);
            var validationParameters = new TokenValidationParameters
            {
                ValidateIssuerSigningKey = true,
                IssuerSigningKey = new SymmetricSecurityKey(key),
                ValidateIssuer = false,
                ValidateAudience = false,
                ValidateLifetime = true,
                ClockSkew = TimeSpan.Zero,
                RequireSignedTokens = true,
            };

            validationParameters.ValidAlgorithms = new[] { SecurityAlgorithms.HmacSha256 };

            var principal = tokenHandler.ValidateToken(tokenStr, validationParameters, out var validatedToken);
            if (validatedToken is not JwtSecurityToken jwtToken)
            {
                return null;
            }

            var userId = jwtToken.Claims.FirstOrDefault(c => c.Type == "user_id")?.Value ?? string.Empty;
            var email = jwtToken.Claims.FirstOrDefault(c => c.Type == "email")?.Value ?? string.Empty;
            var subject = jwtToken.Subject ?? string.Empty;
            var roles = jwtToken.Claims.Where(c => c.Type == "roles").Select(c => c.Value).ToList();

            return new JwtClaims
            {
                UserId = userId,
                Email = email,
                Subject = subject,
                Roles = roles,
            };
        }
        catch
        {
            return null;
        }
    }

    private bool IsPublicPath(string path)
    {
        return IsPublicPathStatic(path, _publicPaths, _prefixPaths);
    }

    private static string ExtractBearerToken(HttpContext context)
    {
        var authHeader = context.Request.Headers.Authorization.FirstOrDefault();
        return ExtractBearerTokenFromHeader(authHeader);
    }

    private static async Task WriteJsonError(HttpContext context, int statusCode, string message)
    {
        context.Response.StatusCode = statusCode;
        context.Response.ContentType = "application/json";
        var error = new { error = message };
        await context.Response.WriteAsync(JsonSerializer.Serialize(error));
    }
}
