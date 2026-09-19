import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { BillingReportComponent } from './billing-report.component';
import { MonthEndReport, ReconciliationReport } from '../../core/models/billing-report.model';

const SOURCE = {
  engine: 'oracle',
  system: 'OW_BILLING legacy estate (Oracle FREEPDB1)',
  detail: 'INVOICE_HEADER / INVOICE_LINE via CODES lookup (RPT-114)',
};

const REPORT: MonthEndReport = {
  report: 'month-end-finance',
  namespace: 'demo',
  batch_no: 1234567,
  source: SOURCE,
  generated_at: '2026-08-01T00:00:00Z',
  by_status: [
    { status: 'ISSUED', invoice_count: 100, header_total_amt: '12345.00' },
    { status: 'PAID', invoice_count: 50, header_total_amt: '655.00' },
  ],
  by_status_line_type: [
    { status: 'ISSUED', line_type: 'CHARGE', line_count: 400, line_amount: '12000.00', line_tax: '345.00', invoices_touched: 100 },
  ],
};

const RECON: ReconciliationReport = {
  namespace: 'demo',
  batch_no: 1234567,
  source: SOURCE,
  generated_at: '2026-08-01T00:00:00Z',
  balances: { customer_count: 25000, current_balance_total: '1234567.00', past_due_total: '8901.00' },
  status: 'baseline',
  checks: [],
};

const FINANCE = {
  ns: 'demo',
  source: {
    system: 'CUSTBILL month-end batch',
    detail: 'ksh/Perl chain over Oracle CUSTBILL extract',
    generated_at: '2026-08-01T00:00:00Z',
    file: 'finance_billing_20260801.csv',
  },
  rows: [{ currency: 'USD', record_type: 'INVOICE', record_count: 2, total_amount: '25.00' }],
  totals: { record_count: 2, total_amount: '25.00' },
};

describe('BillingReportComponent', () => {
  let component: BillingReportComponent;
  let fixture: ComponentFixture<BillingReportComponent>;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [BillingReportComponent, HttpClientTestingModule, NoopAnimationsModule],
    }).compileComponents();

    fixture = TestBed.createComponent(BillingReportComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  function flush(report: MonthEndReport = REPORT, recon: ReconciliationReport = RECON): void {
    fixture.detectChanges();
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/month-end')).flush(report);
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/reconciliation')).flush(recon);
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/overdue')).flush([]);
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/dunning')).flush([]);
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/finance')).flush(FINANCE);
    fixture.detectChanges();
  }

  it('should create', () => {
    expect(component).toBeTruthy();
    fixture.detectChanges();
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/month-end')).flush(REPORT);
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/reconciliation')).flush(RECON);
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/overdue')).flush([]);
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/dunning')).flush([]);
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/finance')).flush(FINANCE);
  });

  it('ignores slower responses from an earlier refresh', () => {
    fixture.detectChanges();
    component.refresh();

    const monthEnd = httpMock.match(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/month-end'));
    const reconciliation = httpMock.match(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/reconciliation'));
    const overdue = httpMock.match(r => r.urlWithParams.startsWith('/api/v1/billing/admin/overdue'));
    const dunning = httpMock.match(r => r.urlWithParams.startsWith('/api/v1/billing/admin/dunning'));
    const finance = httpMock.match(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/finance'));
    expect(monthEnd.length).toBe(2);
    const newerReport = { ...REPORT, namespace: 'newer' };
    monthEnd[1].flush(newerReport);
    reconciliation[1].flush(RECON);
    overdue[1].flush([]);
    dunning[1].flush([]);
    finance[1].flush(FINANCE);
    fixture.detectChanges();
    expect(component.report?.namespace).toBe('newer');

    monthEnd[0].flush({ ...REPORT, namespace: 'older' });
    reconciliation[0].flush(RECON);
    overdue[0].flush([]);
    dunning[0].flush([]);
    finance[0].flush(FINANCE);
    fixture.detectChanges();
    expect(component.report?.namespace).toBe('newer');
  });

  it('should render the legacy source badge', () => {
    flush();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.source-badge')?.textContent).toContain('Legacy Oracle Estate');
    expect(compiled.querySelector('.source-badge')?.classList).toContain('engine-oracle');
  });

  it('should total invoices and billed amounts across statuses', () => {
    flush();
    expect(component.totalInvoices).toBe(150);
    expect(component.totalBilled).toBe(13000);
  });

  it('should total string invoice counts numerically', () => {
    flush({
      ...REPORT,
      by_status: [
        { status: 'ISSUED', invoice_count: '10000', header_total_amt: '12345.00' },
        { status: 'PAID', invoice_count: '8750', header_total_amt: '655.00' },
      ],
    });
    expect(component.totalInvoices).toBe(18750);
  });

  it('should show the baseline reconciliation banner for the legacy estate', () => {
    flush();
    const banner = (fixture.nativeElement as HTMLElement).querySelector('.recon-banner');
    expect(banner?.classList).toContain('recon-baseline');
    expect(banner?.textContent).toContain('Legacy source of truth');
  });

  it('should flip the banner red and list failing checks on drift', () => {
    flush(REPORT, {
      ...RECON,
      status: 'fail',
      checks: [{ name: 'customers-checksum', status: 'fail' }],
    });
    const banner = (fixture.nativeElement as HTMLElement).querySelector('.recon-banner');
    expect(banner?.classList).toContain('recon-fail');
    expect(banner?.textContent).toContain('customers-checksum');
  });

  it('should show an error state when the estate is unavailable', () => {
    fixture.detectChanges();
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/month-end'))
      .flush({ error: 'legacy estate unavailable' }, { status: 503, statusText: 'Service Unavailable' });
    // forkJoin cancels the sibling request on error; just acknowledge it.
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/reconciliation'));
    httpMock.match(r => r.urlWithParams.includes('/api/v1/billing/admin/overdue') || r.urlWithParams.includes('/api/v1/billing/admin/dunning')).forEach(request => {
      if (!request.cancelled) {
        request.flush({ error: 'legacy estate unavailable' }, { status: 503, statusText: 'Service Unavailable' });
      }
    });
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/finance'))
      .flush({ error: 'legacy estate unavailable' }, { status: 503, statusText: 'Service Unavailable' });
    fixture.detectChanges();
    expect(component.error).toContain('Failed to load');
  });

  it('should render overdue accounts and dunning attempts', () => {
    fixture.detectChanges();
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/month-end')).flush(REPORT);
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/reconciliation')).flush(RECON);
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/overdue')).flush([
      { tenant_id: 'tenant-1', invoice_id: 'invoice-1', total: '25.00', amount: '25.00', overdue_days: 12 },
    ]);
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/dunning')).flush([
      { tenant_id: 'tenant-1', invoice_id: 'invoice-1', scheduled_for: '2026-02-28', status: 'SCHEDULED' },
    ]);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('tenant-1');
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('SCHEDULED');
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/finance')).flush(FINANCE);
  });

  it('should show the admin sign-in message for forbidden collections data', () => {
    fixture.detectChanges();
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/month-end')).flush(REPORT);
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/reconciliation')).flush(RECON);
    const requests = httpMock.match(r => r.urlWithParams.includes('/api/v1/billing/admin/overdue') || r.urlWithParams.includes('/api/v1/billing/admin/dunning'));
    requests.forEach(request => {
      if (!request.cancelled) {
        request.flush({ error: 'forbidden' }, { status: 403, statusText: 'Forbidden' });
      }
    });
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/finance'))
      .flush(FINANCE);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Sign in as an admin to view collections data');
  });

  it('should show the unavailable message for unavailable collections data', () => {
    fixture.detectChanges();
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/month-end')).flush(REPORT);
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/reconciliation')).flush(RECON);
    const requests = httpMock.match(r => r.urlWithParams.includes('/api/v1/billing/admin/overdue') || r.urlWithParams.includes('/api/v1/billing/admin/dunning'));
    requests.forEach(request => {
      if (!request.cancelled) {
        request.flush({ error: 'unavailable' }, { status: 503, statusText: 'Service Unavailable' });
      }
    });
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/finance'))
      .flush(FINANCE);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain("Billing is temporarily unavailable");
  });

  it('renders the month-end finance batch source and rows', () => {
    flush();
    const text = (fixture.nativeElement as HTMLElement).textContent;
    expect(text).toContain('Month-end finance batch');
    expect(text).toContain('CUSTBILL month-end batch');
    expect(text).toContain('INVOICE');
  });

  it('shows the rerun instruction when the finance batch is missing', () => {
    fixture.detectChanges();
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/month-end')).flush(REPORT);
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/reconciliation')).flush(RECON);
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/finance'))
      .flush({ error: 'no finance report for namespace' }, { status: 404, statusText: 'Not Found' });
    httpMock.match(r => r.urlWithParams.includes('/api/v1/billing/admin/overdue') || r.urlWithParams.includes('/api/v1/billing/admin/dunning')).forEach(request => {
      if (!request.cancelled) request.flush([]);
    });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('run make tp-month-end NS=demo');
  });

  it('shows the unavailable treatment when the finance batch is unavailable', () => {
    fixture.detectChanges();
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/month-end')).flush(REPORT);
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/reconciliation')).flush(RECON);
    httpMock.expectOne(r => r.urlWithParams.startsWith('/api/v1/billing/admin/reports/finance'))
      .flush({ error: 'unavailable' }, { status: 503, statusText: 'Service Unavailable' });
    httpMock.match(r => r.url.startsWith('/api/v1/billing/admin/')).forEach(request => {
      if (!request.cancelled) request.flush([]);
    });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Billing is temporarily unavailable');
  });
});
