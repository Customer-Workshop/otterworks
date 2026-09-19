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

  it('requests the namespace finance batch through the report backend', () => {
    service.getFinanceReport('demo').subscribe(value => expect(value.ns).toBe('demo'));
    const request = httpMock.expectOne('/api/v1/billing/admin/reports/finance?ns=demo');
    expect(request.request.method).toBe('GET');
    request.flush({
      ns: 'demo',
      source: { system: 'CUSTBILL month-end batch', detail: 'ksh/Perl chain', generated_at: '', file: 'report.csv' },
      rows: [],
      totals: { record_count: 0, total_amount: '0.00' },
    });
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
