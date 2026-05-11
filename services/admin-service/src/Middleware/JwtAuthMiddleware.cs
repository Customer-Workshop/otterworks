using System.IdentityModel.Tokens.Jwt;
using System.Text;
using Microsoft.IdentityModel.Tokens;

namespace OtterWorks.AdminService.Middleware;

public class JwtAuthMiddleware
{
    private static readonly string[] ExcludedPaths = ["/health", "/metrics"];

    private readonly RequestDelegate _next;
    private readonly IConfiguration _configuration;
    private readonly ILogger<JwtAuthMiddleware> _logger;

    public JwtAuthMiddleware(RequestDelegate next, IConfiguration configuration, ILogger<JwtAuthMiddleware> logger)
    {
        _next = next;
        _configuration = configuration;
        _logger = logger;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        var path = context.Request.Path.Value ?? string.Empty;
        if (ExcludedPaths.Any(p => path.Equals(p, StringComparison.OrdinalIgnoreCase)))
        {
            await _next(context);
            return;
        }

        var authHeader = context.Request.Headers.Authorization.FirstOrDefault();
        if (string.IsNullOrEmpty(authHeader) || !authHeader.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase))
        {
            context.Response.StatusCode = 401;
            context.Response.ContentType = "application/json";
            await context.Response.WriteAsync("{\"error\":\"Missing authorization token\"}");
            return;
        }

        var token = authHeader["Bearer ".Length..].Trim();
        var secret = _configuration["Jwt:Secret"]
            ?? Environment.GetEnvironmentVariable("JWT_SECRET")
            ?? string.Empty;

        try
        {
            var handler = new JwtSecurityTokenHandler();
            var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(secret));
            var validationParams = new TokenValidationParameters
            {
                ValidateIssuerSigningKey = true,
                IssuerSigningKey = key,
                ValidateIssuer = false,
                ValidateAudience = false,
                ValidateLifetime = true,
                ClockSkew = TimeSpan.Zero,
            };

            var principal = handler.ValidateToken(token, validationParams, out var validatedToken);
            var jwtToken = (JwtSecurityToken)validatedToken;

            context.Items["jwt.user_id"] = jwtToken.Claims.FirstOrDefault(c => c.Type == "sub")?.Value;
            context.Items["jwt.user_email"] = jwtToken.Claims.FirstOrDefault(c => c.Type == "email")?.Value;
            context.Items["jwt.user_role"] = jwtToken.Claims.FirstOrDefault(c => c.Type == "role")?.Value;

            await _next(context);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "JWT authentication failed");
            context.Response.StatusCode = 401;
            context.Response.ContentType = "application/json";
            await context.Response.WriteAsync("{\"error\":\"Invalid or expired token\"}");
        }
    }
}
