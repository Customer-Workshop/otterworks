import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { RouterTestingModule } from '@angular/router/testing';
import { BehaviorSubject } from 'rxjs';
import { ParamMap } from '@angular/router';
import { MigrationComponent } from './migration.component';
import { ReconciliationReport } from '../../core/models/migration.model';

const REPORT: ReconciliationReport = {
  run_id: 'r20260924150000',
  namespace: 'd24-after',
  generated_at: '2026-09-24T15:00:00Z',
  status: 'SUCCEEDED',
  started_at: null,
  finished_at: null,
  closes: false,
  tables: [
    { table: 'RETNPLCY', extracted: 40, loaded: 40, validated: 40, purged: 0, failed: 0, rejected: 0, validate_failed: 0, purge_intended: 0, purge_dry_run: true, closes: true },
    { table: 'DOCARCH', extracted: 180000, loaded: 179980, validated: 179963, purged: 179963, failed: 37, rejected: 20, validate_failed: 17, purge_intended: 179963, purge_dry_run: false, closes: true },
  ],
  failures: [
    { table: 'DOCARCH', source_key: 'MIG01-0000000001', rule: 'CCSID_UNMAPPABLE', stage: 'LOAD', field: 'OWNER_NAME', sqlstate: null, native_error: null, error: 'byte X\'3F\'', issue: 'MIG-01' },
    { table: 'DOCARCH', source_key: 'MIG07-0000000001', rule: 'CLASS_TOTAL_MISMATCH', stage: 'VALIDATE', field: 'STORAGE_CHARGE', sqlstate: null, native_error: null, error: 'class FIN7 differs', issue: 'MIG-07' },
    { table: 'FILEAUD', source_key: 'MIG05-0000000001', rule: 'ORPHAN_PARENT', stage: 'VALIDATE', field: null, sqlstate: null, native_error: null, error: 'no parent', issue: 'MIG-05' },
  ],
  class_totals: [
    { table: 'DOCARCH', class: 'FIN7', source_count: 10, target_count: 10, source_sum: '10.00000000', target_sum: '9.00000000', matches: false },
  ],
  sessions: [{ label: 'app', url: 'https://example.invalid/sessions/abc' }],
};

describe('MigrationComponent', () => {
  let fixture: ComponentFixture<MigrationComponent>;
  let component: MigrationComponent;
  let http: HttpTestingController;
  let params$: BehaviorSubject<ParamMap>;

  async function setup(params: Record<string, string>): Promise<void> {
    params$ = new BehaviorSubject<ParamMap>(convertToParamMap(params));
    await TestBed.configureTestingModule({
      imports: [MigrationComponent, HttpClientTestingModule, NoopAnimationsModule, RouterTestingModule],
      providers: [
        { provide: ActivatedRoute, useValue: { paramMap: params$.asObservable() } },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(MigrationComponent);
    component = fixture.componentInstance;
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  }

  function flushCommon(): void {
    http.expectOne('/api/v1/reports/reconciliation').flush([{ run_id: REPORT.run_id, status: 'SUCCEEDED', started_at: null, finished_at: null, closes: false }]);
    http.match('/config/peer.json').forEach(r => r.flush({ peer_app_url: '' }));
  }

  it('defaults to the latest run and renders summary + failures', async () => {
    await setup({});
    http.expectOne('/api/v1/reports/reconciliation/latest').flush(REPORT);
    flushCommon();
    fixture.detectChanges();

    expect(component.report?.run_id).toBe(REPORT.run_id);
    expect(component.runIdInput).toBe(REPORT.run_id);
    expect(component.filteredFailures.length).toBe(3);
    expect(component.issues).toContain('MIG-07');
    expect(component.issueCounts['MIG-07']).toBe(1);

    const el: HTMLElement = fixture.nativeElement;
    expect(el.querySelectorAll('table.grid').length).toBe(3);
    expect(el.querySelector('tr.mig07')).toBeTruthy();
    expect(el.querySelector('.sessions a')?.getAttribute('href')).toBe('https://example.invalid/sessions/abc');

    // CSV goes through HttpClient (bearer header) rather than a plain anchor
    const click = spyOn(HTMLAnchorElement.prototype, 'click');
    spyOn(URL, 'createObjectURL').and.returnValue('blob:csv');
    component.openFile('csv');
    http.expectOne(`/api/v1/reports/reconciliation/${REPORT.run_id}.csv`).flush(new Blob(['a,b']));
    expect(click).toHaveBeenCalled();
  });

  it('ignores a late response for a run the user has navigated away from', async () => {
    await setup({ runId: 'run-a' });
    flushCommon();
    const slow = http.expectOne('/api/v1/reports/reconciliation/run-a');
    params$.next(convertToParamMap({ runId: 'run-b' }));
    expect(slow.cancelled).toBeTrue();
    http.expectOne('/api/v1/reports/reconciliation/run-b').flush({ ...REPORT, run_id: 'run-b' });
    expect(component.report?.run_id).toBe('run-b');
  });

  it('filters failures by rule', async () => {
    await setup({ runId: REPORT.run_id });
    http.expectOne(`/api/v1/reports/reconciliation/${REPORT.run_id}`).flush(REPORT);
    flushCommon();

    component.ruleFilter = 'ORPHAN_PARENT';
    component.applyFilter();
    expect(component.filteredFailures.map(f => f.issue)).toEqual(['MIG-05']);

    component.ruleFilter = '';
    component.issueFilter = 'MIG-07';
    component.applyFilter();
    expect(component.filteredFailures.length).toBe(1);
    expect(component.filteredFailures[0].rule).toBe('CLASS_TOTAL_MISMATCH');
  });

  it('shows the namespace hint when there is no migration here', async () => {
    await setup({});
    http.expectOne('/api/v1/reports/reconciliation/latest').flush(
      { error: 'no migration in this namespace', hint: 'set ARCHIVE_STORE=azuresql' },
      { status: 404, statusText: 'Not Found' },
    );
    flushCommon();
    fixture.detectChanges();

    expect(component.report).toBeNull();
    expect(component.error).toBe('no migration in this namespace');
    expect(component.errorHint).toContain('ARCHIVE_STORE');
  });

  it('passes the archive docId route param to the compare panel', async () => {
    await setup({ docId: 'DOC-42' });
    http.expectOne('/api/v1/reports/reconciliation/latest').flush(REPORT);
    flushCommon();
    http.match('/api/v1/archive/documents/DOC-42').forEach(r => r.flush({ doc_id: 'DOC-42', store: 'db2', versions: [] }));
    http.match('/api/v1/archive/documents/DOC-42/hash').forEach(r => r.flush({ doc_id: 'DOC-42', store: 'db2', algorithm: 'SHA-256', document_hash: 'x' }));
    expect(component.docId).toBe('DOC-42');
  });
});
