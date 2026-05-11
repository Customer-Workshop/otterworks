using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.IdentityModel.Tokens;
using OtterWorks.ApiGateway.Middleware;

namespace ApiGateway.Tests.Unit;

public class JwtAuthMiddlewareTests
{
    private const string TestSecret = "test-secret-key-for-jwt-signing!";

    private static string GenerateTestToken(string secret, string? userId = null, string? email = null, string[]? roles = null, DateTime? expires = null, DateTime? issuedAt = null, string? subject = null)
    {
        var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(secret));
        var credentials = new SigningCredentials(key, SecurityAlgorithms.HmacSha256);

        var claims = new List<Claim>();
        if (userId != null)
        {
            claims.Add(new Claim("user_id", userId));
        }

        if (email != null)
        {
            claims.Add(new Claim("email", email));
        }

        if (roles != null)
        {
            foreach (var role in roles)
            {
                claims.Add(new Claim("roles", role));
            }
        }

        if (subject != null)
        {
            claims.Add(new Claim(JwtRegisteredClaimNames.Sub, subject));
        }

        var token = new JwtSecurityToken(
            claims: claims,
            expires: expires ?? DateTime.UtcNow.AddHours(1),
            notBefore: issuedAt ?? DateTime.UtcNow.AddSeconds(-5),
            signingCredentials: credentials);

        return new JwtSecurityTokenHandler().WriteToken(token);
    }

    private static JwtAuthMiddleware CreateMiddleware(RequestDelegate? next = null, string secret = TestSecret)
    {
        next ??= context =>
        {
            context.Response.StatusCode = 200;
            return Task.CompletedTask;
        };

        var config = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["JWT_SECRET"] = secret,
            })
            .Build();

        return new JwtAuthMiddleware(next, config);
    }

    [Theory]
    [InlineData("/health")]
    [InlineData("/metrics")]
    [InlineData("/api/v1/auth/login")]
    [InlineData("/api/v1/auth/register")]
    public async Task PublicPaths_SkipValidation(string path)
    {
        var invoked = false;
        var middleware = CreateMiddleware(context =>
        {
            invoked = true;
            context.Response.StatusCode = 200;
            return Task.CompletedTask;
        });

        var context = new DefaultHttpContext();
        context.Request.Path = path;

        await middleware.InvokeAsync(context);

        Assert.True(invoked);
        Assert.Equal(200, context.Response.StatusCode);
    }

    [Theory]
    [InlineData("/api/v1/auth/login/callback")]
    [InlineData("/api/v1/auth/register/verify")]
    public async Task SubPathsOfExactMatch_RequireAuth(string path)
    {
        var middleware = CreateMiddleware();

        var context = new DefaultHttpContext();
        context.Request.Path = path;

        await middleware.InvokeAsync(context);

        Assert.Equal(401, context.Response.StatusCode);
    }

    [Theory]
    [InlineData("/health/ready")]
    [InlineData("/metrics/prometheus")]
    public async Task SubPathsOfPrefixMatch_SkipAuth(string path)
    {
        var invoked = false;
        var middleware = CreateMiddleware(context =>
        {
            invoked = true;
            context.Response.StatusCode = 200;
            return Task.CompletedTask;
        });

        var context = new DefaultHttpContext();
        context.Request.Path = path;

        await middleware.InvokeAsync(context);

        Assert.True(invoked);
        Assert.Equal(200, context.Response.StatusCode);
    }

    [Fact]
    public async Task MissingToken_Returns401()
    {
        var middleware = CreateMiddleware();

        var context = new DefaultHttpContext();
        context.Request.Path = "/api/v1/files/list";

        await middleware.InvokeAsync(context);

        Assert.Equal(401, context.Response.StatusCode);
    }

    [Fact]
    public async Task InvalidToken_Returns401()
    {
        var middleware = CreateMiddleware();

        var context = new DefaultHttpContext();
        context.Request.Path = "/api/v1/files/list";
        context.Request.Headers.Authorization = "Bearer invalid-token-string";

        await middleware.InvokeAsync(context);

        Assert.Equal(401, context.Response.StatusCode);
    }

    [Fact]
    public async Task ValidToken_PassesThrough()
    {
        JwtClaims? capturedClaims = null;
        var middleware = CreateMiddleware(context =>
        {
            capturedClaims = JwtAuthMiddleware.GetClaims(context);
            context.Response.StatusCode = 200;
            return Task.CompletedTask;
        });

        var token = GenerateTestToken(TestSecret, userId: "user-123", email: "test@otterworks.dev", roles: new[] { "user" }, subject: "user-123");

        var context = new DefaultHttpContext();
        context.Request.Path = "/api/v1/files/list";
        context.Request.Headers.Authorization = $"Bearer {token}";

        await middleware.InvokeAsync(context);

        Assert.Equal(200, context.Response.StatusCode);
        Assert.NotNull(capturedClaims);
        Assert.Equal("user-123", capturedClaims.UserId);
        Assert.Equal("test@otterworks.dev", capturedClaims.Email);
    }

    [Fact]
    public async Task ExpiredToken_Returns401()
    {
        var middleware = CreateMiddleware();

        var token = GenerateTestToken(
            TestSecret,
            userId: "user-123",
            expires: DateTime.UtcNow.AddHours(-1),
            issuedAt: DateTime.UtcNow.AddHours(-2));

        var context = new DefaultHttpContext();
        context.Request.Path = "/api/v1/files/list";
        context.Request.Headers.Authorization = $"Bearer {token}";

        await middleware.InvokeAsync(context);

        Assert.Equal(401, context.Response.StatusCode);
    }

    [Fact]
    public async Task WrongSecret_Returns401()
    {
        var middleware = CreateMiddleware();

        var token = GenerateTestToken("wrong-secret-key-for-jwt-testing!", userId: "user-123");

        var context = new DefaultHttpContext();
        context.Request.Path = "/api/v1/files/list";
        context.Request.Headers.Authorization = $"Bearer {token}";

        await middleware.InvokeAsync(context);

        Assert.Equal(401, context.Response.StatusCode);
    }

    [Theory]
    [InlineData("token-without-bearer")]
    [InlineData("Basic dXNlcjpwYXNz")]
    [InlineData("Bearer ")]
    public async Task MalformedAuthHeader_Returns401(string header)
    {
        var middleware = CreateMiddleware();

        var context = new DefaultHttpContext();
        context.Request.Path = "/api/v1/files/list";
        context.Request.Headers.Authorization = header;

        await middleware.InvokeAsync(context);

        Assert.Equal(401, context.Response.StatusCode);
    }

    [Theory]
    [InlineData("Bearer abc123", "abc123")]
    [InlineData("bearer abc123", "abc123")]
    [InlineData("", "")]
    [InlineData("abc123", "")]
    [InlineData("Basic dXNlcjpwYXNz", "")]
    public void ExtractBearerToken_ExtractsCorrectly(string header, string expected)
    {
        var result = JwtAuthMiddleware.ExtractBearerTokenFromHeader(header == string.Empty ? null : header);
        Assert.Equal(expected, result);
    }

    [Fact]
    public void GetClaims_NilContext_ReturnsNull()
    {
        var context = new DefaultHttpContext();
        var claims = JwtAuthMiddleware.GetClaims(context);
        Assert.Null(claims);
    }

    [Fact]
    public void IsPublicPath_ExactMatch()
    {
        var publicPaths = new HashSet<string> { "/api/v1/auth/login", "/api/v1/auth/register" };
        var prefixPaths = new[] { "/health", "/metrics", "/socket.io" };

        Assert.True(JwtAuthMiddleware.IsPublicPathStatic("/api/v1/auth/login", publicPaths, prefixPaths));
        Assert.True(JwtAuthMiddleware.IsPublicPathStatic("/health", publicPaths, prefixPaths));
        Assert.True(JwtAuthMiddleware.IsPublicPathStatic("/health/ready", publicPaths, prefixPaths));
        Assert.False(JwtAuthMiddleware.IsPublicPathStatic("/api/v1/files", publicPaths, prefixPaths));
    }
}
