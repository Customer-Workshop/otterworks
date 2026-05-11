using FluentValidation;
using OtterWorks.AnalyticsService.Models;

namespace OtterWorks.AnalyticsService.Validators;

public class TrackEventRequestValidator : AbstractValidator<TrackEventRequest>
{
    public TrackEventRequestValidator()
    {
        RuleFor(x => x.EventType).NotEmpty().WithMessage("eventType is required");
        RuleFor(x => x.UserId).NotEmpty().WithMessage("userId is required");
        RuleFor(x => x.ResourceId).NotEmpty().WithMessage("resourceId is required");
        RuleFor(x => x.ResourceType).NotEmpty().WithMessage("resourceType is required");
    }
}
