import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { ReportsComponent } from './reports.component';

const COMPLETED_REPORT = {
  id: 7,
  reportName: 'Monthly Usage Report',
  category: 'USAGE_ANALYTICS',
  reportType: 'CSV',
  status: 'COMPLETED',
  requestedBy: 'admin',
  createdAt: '2026-09-25T10:00:00.000Z',
  downloadUrl: '/api/v1/reports/7/download',
};

describe('ReportsComponent', () => {
  let component: ReportsComponent;
  let fixture: ComponentFixture<ReportsComponent>;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        ReportsComponent,
        HttpClientTestingModule,
        RouterTestingModule,
        NoopAnimationsModule,
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ReportsComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  function flushStatusRequests(reportsByStatus: Record<string, unknown[]>): void {
    for (const status of ['PENDING', 'GENERATING', 'COMPLETED', 'FAILED']) {
      const req = httpMock.expectOne(`/api/v1/reports?status=${status}`);
      req.flush({ reports: reportsByStatus[status] ?? [], total: (reportsByStatus[status] ?? []).length });
    }
  }

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should start in the loading state', () => {
    expect(component.loading).toBeTrue();
  });

  it('should list reports from every status when no filter is set', () => {
    fixture.detectChanges();
    flushStatusRequests({ COMPLETED: [COMPLETED_REPORT] });
    fixture.detectChanges();

    expect(component.loading).toBeFalse();
    expect(component.error).toBe('');
    expect(component.dataSource.data.length).toBe(1);
    expect(fixture.nativeElement.textContent).toContain('Monthly Usage Report');
  });

  it('should request a single status when the filter is set', () => {
    fixture.detectChanges();
    flushStatusRequests({});

    component.statusFilter = 'FAILED';
    component.loadReports();
    const req = httpMock.expectOne('/api/v1/reports?status=FAILED');
    expect(req.request.method).toBe('GET');
    req.flush({ reports: [], total: 0 });
    fixture.detectChanges();

    expect(component.dataSource.data.length).toBe(0);
    expect(fixture.nativeElement.textContent).toContain('No Failed reports');
  });

  it('should show an error state instead of an empty table when the request fails', () => {
    fixture.detectChanges();
    httpMock.expectOne('/api/v1/reports?status=PENDING')
      .flush('service unavailable', { status: 503, statusText: 'Service Unavailable' });
    // the remaining status requests are cancelled once the first one fails
    httpMock.match(() => true);
    fixture.detectChanges();

    expect(component.error).toContain('Could not load reports');
    expect(component.dataSource.data.length).toBe(0);
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.error-container')).toBeTruthy();
    expect(compiled.querySelector('.empty-state')).toBeFalsy();
    expect(compiled.querySelector('.reports-table')).toBeFalsy();
  });

  it('should show an empty state when there are no reports', () => {
    fixture.detectChanges();
    flushStatusRequests({});
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.empty-state')).toBeTruthy();
    expect(compiled.textContent).toContain('No reports yet');
  });

  it('should post the create-report payload and reload the list', () => {
    fixture.detectChanges();
    flushStatusRequests({});

    component.newReport = { reportName: 'Audit Trail', category: 'AUDIT_LOG', reportType: 'PDF' };
    component.createReport();

    const createReq = httpMock.expectOne('/api/v1/reports');
    expect(createReq.request.method).toBe('POST');
    expect(createReq.request.body.reportName).toBe('Audit Trail');
    expect(createReq.request.body.category).toBe('AUDIT_LOG');
    expect(createReq.request.body.reportType).toBe('PDF');
    expect(createReq.request.body.requestedBy).toBeTruthy();
    createReq.flush({ ...COMPLETED_REPORT, id: 8, reportName: 'Audit Trail', status: 'PENDING' });

    flushStatusRequests({});
    expect(component.creating).toBeFalse();
    expect(component.showCreateForm).toBeFalse();
  });

  it('should download a completed report as a blob', () => {
    fixture.detectChanges();
    flushStatusRequests({ COMPLETED: [COMPLETED_REPORT] });
    spyOn(URL, 'createObjectURL').and.returnValue('blob:report');
    spyOn(URL, 'revokeObjectURL');

    component.downloadReport(component.dataSource.data[0]);
    const req = httpMock.expectOne('/api/v1/reports/7/download');
    expect(req.request.responseType).toBe('blob');
    req.flush(new Blob(['id,name\n'], { type: 'text/csv' }), {
      headers: { 'content-disposition': 'attachment; filename="usage-7.csv"' },
    });

    expect(URL.createObjectURL).toHaveBeenCalled();
    expect(component.downloadingId).toBeNull();
  });

  it('should humanise enum labels', () => {
    expect(component.label('USAGE_ANALYTICS')).toBe('Usage Analytics');
    expect(component.label('COMPLETED')).toBe('Completed');
  });
});
