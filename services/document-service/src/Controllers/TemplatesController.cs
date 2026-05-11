using Microsoft.AspNetCore.Mvc;
using OtterWorks.DocumentService.DTOs;
using OtterWorks.DocumentService.Services;

namespace OtterWorks.DocumentService.Controllers;

[ApiController]
[Route("api/v1/templates")]
public class TemplatesController : ControllerBase
{
    private readonly IDocumentService _service;
    private readonly ILogger<TemplatesController> _logger;

    public TemplatesController(IDocumentService service, ILogger<TemplatesController> logger)
    {
        _service = service;
        _logger = logger;
    }

    [HttpGet("")]
    public async Task<IActionResult> ListTemplates()
    {
        var templates = await _service.ListTemplatesAsync();
        return Ok(templates);
    }

    [HttpPost("")]
    public async Task<IActionResult> CreateTemplate([FromBody] TemplateCreateRequest body)
    {
        var template = await _service.CreateTemplateAsync(body);
        _logger.LogInformation("template_created: {TemplateId}", template.Id);
        return StatusCode(201, template);
    }
}
