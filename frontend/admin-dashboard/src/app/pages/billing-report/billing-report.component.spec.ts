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
    httpMock.expectOne(r => r.url === '/billing-api/api/reports/month-end').flush(report);
    httpMock.expectOne(r => r.url === '/billing-api/api/reports/reconciliation').flush(recon);
    fixture.detectChanges();
  }

  it('should create', () => {
    expect(component).toBeTruthy();
    fixture.detectChanges();
    httpMock.expectOne(r => r.url === '/billing-api/api/reports/month-end').flush(REPORT);
    httpMock.expectOne(r => r.url === '/billing-api/api/reports/reconciliation').flush(RECON);
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
    httpMock.expectOne(r => r.url === '/billing-api/api/reports/month-end')
      .flush({ error: 'legacy estate unavailable' }, { status: 503, statusText: 'Service Unavailable' });
    // forkJoin cancels the sibling request on error; just acknowledge it.
    httpMock.expectOne(r => r.url === '/billing-api/api/reports/reconciliation');
    fixture.detectChanges();
    expect(component.error).toContain('Failed to load');
  });
});
