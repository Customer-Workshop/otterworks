using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using OtterWorks.AuthService.DTOs;
using OtterWorks.AuthService.Services;

namespace OtterWorks.AuthService.Controllers;

[ApiController]
[Route("api/v1/auth")]
public class AuthController : ControllerBase
{
    private readonly IAuthService _authService;
    private readonly IUserService _userService;

    public AuthController(IAuthService authService, IUserService userService)
    {
        _authService = authService;
        _userService = userService;
    }

    [HttpPost("register")]
    [AllowAnonymous]
    public async Task<IActionResult> Register([FromBody] RegisterRequest request)
    {
        var response = await _authService.RegisterAsync(request);
        return StatusCode(StatusCodes.Status201Created, response);
    }

    [HttpPost("login")]
    [AllowAnonymous]
    public async Task<IActionResult> Login([FromBody] LoginRequest request)
    {
        var response = await _authService.LoginAsync(request);
        return Ok(response);
    }

    [HttpPost("refresh")]
    [AllowAnonymous]
    public async Task<IActionResult> Refresh([FromHeader(Name = "Authorization")] string bearerToken)
    {
        var token = bearerToken.Replace("Bearer ", string.Empty, StringComparison.OrdinalIgnoreCase);
        var response = await _authService.RefreshTokenAsync(token);
        return Ok(response);
    }

    [HttpGet("profile")]
    [Authorize]
    public async Task<IActionResult> GetProfile()
    {
        var userId = GetUserId();
        var profile = await _userService.GetProfileAsync(userId);
        return Ok(profile);
    }

    [HttpPut("profile")]
    [Authorize]
    public async Task<IActionResult> UpdateProfile([FromBody] UpdateProfileRequest request)
    {
        var userId = GetUserId();
        var profile = await _userService.UpdateProfileAsync(userId, request);
        return Ok(profile);
    }

    [HttpPost("change-password")]
    [Authorize]
    public async Task<IActionResult> ChangePassword([FromBody] ChangePasswordRequest request)
    {
        var userId = GetUserId();
        await _authService.ChangePasswordAsync(userId, request);
        return NoContent();
    }

    [HttpGet("users/lookup")]
    [Authorize]
    public async Task<IActionResult> LookupUser([FromQuery] string email)
    {
        var user = await _userService.FindByEmailAsync(email);
        return Ok(UserLookupResponse.FromUserDTO(user));
    }

    [HttpGet("users/by-id/{id}")]
    [Authorize]
    public async Task<IActionResult> LookupUserById(Guid id)
    {
        var user = await _userService.GetProfileAsync(id);
        return Ok(UserLookupResponse.FromUserDTO(user));
    }

    [HttpGet("users")]
    [Authorize(Roles = "ADMIN")]
    public async Task<IActionResult> ListUsers([FromQuery] int page = 0, [FromQuery] int size = 20)
    {
        var users = await _userService.ListUsersAsync(page, size);
        return Ok(users);
    }

    [HttpPost("logout")]
    [Authorize]
    public async Task<IActionResult> Logout()
    {
        var userId = GetUserId();
        await _authService.LogoutAsync(userId);
        return NoContent();
    }

    private Guid GetUserId()
    {
        var userIdClaim = User.FindFirst(ClaimTypes.NameIdentifier)?.Value
            ?? User.FindFirst(JwtRegisteredClaimNames.Sub)?.Value;

        if (string.IsNullOrEmpty(userIdClaim) || !Guid.TryParse(userIdClaim, out var userId))
        {
            throw new UnauthorizedAccessException("Invalid user identity");
        }

        return userId;
    }
}
