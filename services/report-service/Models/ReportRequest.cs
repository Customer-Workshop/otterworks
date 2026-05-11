using FluentValidation;

namespace OtterWorks.ReportService.Models;

public class ReportRequest
{
    public string? ReportName { get; set; }
    public ReportCategory? Category { get; set; }
    public ReportType? ReportType { get; set; }
    public string? RequestedBy { get; set; }
    public DateTime? DateFrom { get; set; }
    public DateTime? DateTo { get; set; }
    public Dictionary<string, string>? Parameters { get; set; }
}

public class ReportRequestValidator : AbstractValidator<ReportRequest>
{
    public ReportRequestValidator()
    {
        RuleFor(x => x.ReportName)
            .NotEmpty().WithMessage("Report name is required");
        RuleFor(x => x.Category)
            .NotNull().WithMessage("Report category is required");
        RuleFor(x => x.ReportType)
            .NotNull().WithMessage("Report type is required");
        RuleFor(x => x.RequestedBy)
            .NotEmpty().WithMessage("Requester ID is required");
    }
}
