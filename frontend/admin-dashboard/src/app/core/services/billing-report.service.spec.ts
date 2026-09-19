import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { BillingReportService } from './billing-report.service';

describe('BillingReportService collections endpoints', () => {
  let service: BillingReportService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [BillingReportService],
    });
    service = TestBed.inject(BillingReportService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('requests overdue accounts through the gateway', () => {
    service.getOverdueAccounts('2026-02-28').subscribe(value => expect(value).toEqual([]));
    const request = httpMock.expectOne('/api/v1/billing/admin/overdue?as_of=2026-02-28');
    expect(request.request.method).toBe('GET');
    request.flush([]);
  });

  it('requests dunning attempts through the gateway', () => {
    service.getDunningAttempts('2026-02-28').subscribe(value => expect(value).toEqual([]));
    const request = httpMock.expectOne('/api/v1/billing/admin/dunning?as_of=2026-02-28');
    expect(request.request.method).toBe('GET');
    request.flush([]);
  });

  it('surfaces forbidden and unavailable responses', () => {
    let forbiddenStatus = 0;
    service.getOverdueAccounts('2026-02-28').subscribe({
      error: error => { forbiddenStatus = error.status; },
    });
    httpMock.expectOne(r => r.url === '/api/v1/billing/admin/overdue').flush({}, {
      status: 403,
      statusText: 'Forbidden',
    });
    expect(forbiddenStatus).toBe(403);

    let unavailableStatus = 0;
    service.getDunningAttempts('2026-02-28').subscribe({
      error: error => { unavailableStatus = error.status; },
    });
    httpMock.expectOne(r => r.url === '/api/v1/billing/admin/dunning').flush({}, {
      status: 503,
      statusText: 'Service Unavailable',
    });
    expect(unavailableStatus).toBe(503);
  });
});
