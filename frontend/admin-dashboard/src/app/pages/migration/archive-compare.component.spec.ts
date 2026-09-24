import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { ArchiveCompareComponent } from './archive-compare.component';
import { ArchiveDocument } from '../../core/models/migration.model';

function doc(store: string, ownerName: string, eventTs: string): ArchiveDocument {
  return {
    doc_id: 'DOC-42',
    store,
    versions: [{
      arch_key: 'DA00000000000042', version_no: 3, retention_class: 'FIN7',
      last_access_ts: '2016-03-01-10.15.30.123456789012', storage_charge: '1234.50000000', unit_rate: '0.01000000',
      owner_name: ownerName, disposition_dt: '2023-03-01', legal_hold: false, checksum_alg: 'SHA256', content_sha256: 'abc', byte_size: 10, source_sys: 'DMS',
      events: [{
        audit_key: 'FA000000000000000123', event_type: 'VIEW', event_ts: eventTs, actor_id: 'U00000000042',
        retention_class: 'FIN7', disposition_code: '00', client_ip: '10.1.2.3', detail_text: 'VIEW v3',
      }],
    }],
  };
}

describe('ArchiveCompareComponent', () => {
  let fixture: ComponentFixture<ArchiveCompareComponent>;
  let component: ArchiveCompareComponent;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ArchiveCompareComponent, HttpClientTestingModule, NoopAnimationsModule],
    }).compileComponents();
    fixture = TestBed.createComponent(ArchiveCompareComponent);
    component = fixture.componentInstance;
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('picks up PEER_APP_URL and fetches both sides', () => {
    component.docId = 'DOC-42';
    component.autoLoad = true;
    fixture.detectChanges();
    http.expectOne('/config/peer.json').flush({ peer_app_url: 'https://peer.example' });

    http.expectOne('/api/v1/reports/archive/documents/DOC-42').flush(doc('db2', 'LOPEZ, M.', '2015-07-02-08.00.00.000000000001'));
    http.expectOne('/api/v1/reports/archive/documents/DOC-42/hash').flush({ document_hash: 'h1' });
    http.expectOne('https://peer.example/api/v1/reports/archive/documents/DOC-42').flush(doc('azuresql', 'LOPEZ, M.', '2015-07-02-08.00.00.000000000001'));
    http.expectOne('https://peer.example/api/v1/reports/archive/documents/DOC-42/hash').flush({ document_hash: 'h1' });
    fixture.detectChanges();

    expect(component.sides.length).toBe(2);
    expect(component.verdict).toBe('match');
    expect(component.mismatchCount).toBe(0);
    expect(component.differs(component.sides[0].document!.versions[0], 'owner_name')).toBeFalse();
  });

  it('highlights fields and events that differ between deployments', () => {
    component.docId = 'DOC-42';
    component.peerUrl = 'https://peer.example/';
    fixture.detectChanges();
    http.expectOne('/config/peer.json').flush({ peer_app_url: '' });

    component.load();
    http.expectOne('/api/v1/reports/archive/documents/DOC-42').flush(doc('db2', 'LOPEZ, M.', '2015-07-02-08.00.00.000000000001'));
    http.expectOne('/api/v1/reports/archive/documents/DOC-42/hash').flush({ document_hash: 'h1' });
    http.expectOne('https://peer.example/api/v1/reports/archive/documents/DOC-42').flush(doc('azuresql', 'LOPEZ, M', '2015-07-02-08.00.00.000000000000'));
    http.expectOne('https://peer.example/api/v1/reports/archive/documents/DOC-42/hash').flush({ document_hash: 'h2' });
    fixture.detectChanges();

    expect(component.verdict).toBe('mismatch');
    expect(component.mismatchCount).toBe(2);
    const v0 = component.sides[0].document!.versions[0];
    expect(component.differs(v0, 'owner_name')).toBeTrue();
    expect(component.eventDiffers(v0, v0.events[0])).toBeTrue();
    // one field row + one event row highlighted on each of the two sides
    expect(fixture.nativeElement.querySelectorAll('tr.diff').length).toBe(4);
  });

  it('flags a version that exists on only one side', () => {
    component.docId = 'DOC-42';
    component.peerUrl = 'https://peer.example';
    fixture.detectChanges();
    http.expectOne('/config/peer.json').flush({ peer_app_url: '' });

    component.load();
    const two = doc('db2', 'LOPEZ, M.', '2015-07-02-08.00.00.000000000001');
    const v1 = two.versions[0];
    two.versions = [
      v1,
      { ...v1, version_no: 2, arch_key: 'DA00000000000043' },
      { ...v1, version_no: 3, arch_key: 'DA00000000000044' },
    ];
    const one = doc('azuresql', 'LOPEZ, M.', '2015-07-02-08.00.00.000000000001');
    one.versions = [v1, { ...v1, version_no: 3, arch_key: 'DA00000000000044' }];
    http.expectOne('/api/v1/reports/archive/documents/DOC-42').flush(two);
    http.expectOne('/api/v1/reports/archive/documents/DOC-42/hash').flush({ document_hash: 'h1' });
    http.expectOne('https://peer.example/api/v1/reports/archive/documents/DOC-42').flush(one);
    http.expectOne('https://peer.example/api/v1/reports/archive/documents/DOC-42/hash').flush({ document_hash: 'h2' });
    fixture.detectChanges();

    expect(component.verdict).toBe('mismatch');
    expect(component.mismatchCount).toBe(1);
    const [local1, local2, local3] = component.sides[0].document!.versions;
    expect(component.versionMissing(local2)).toBeTrue();
    expect(component.versionMissing(local1)).toBeFalse();
    expect(component.versionMissing(local3)).toBeFalse();
    expect(component.differs(local3, 'arch_key')).toBeFalse();
    expect(fixture.nativeElement.querySelectorAll('.version.missing').length).toBe(1);
  });

  it('does not claim a match when a hash is missing on one side', () => {
    component.docId = 'DOC-42';
    component.peerUrl = 'https://peer.example';
    fixture.detectChanges();
    http.expectOne('/config/peer.json').flush({ peer_app_url: '' });

    component.load();
    const same = doc('db2', 'LOPEZ, M.', '2015-07-02-08.00.00.000000000001');
    http.expectOne('/api/v1/reports/archive/documents/DOC-42').flush(same);
    http.expectOne('/api/v1/reports/archive/documents/DOC-42/hash').flush({ document_hash: 'h1' });
    http.expectOne('https://peer.example/api/v1/reports/archive/documents/DOC-42').flush(same);
    http.expectOne('https://peer.example/api/v1/reports/archive/documents/DOC-42/hash')
      .flush({ error: 'boom' }, { status: 503, statusText: 'Unavailable' });
    fixture.detectChanges();

    expect(component.verdict).toBe('unknown');
    expect(component.mismatchCount).toBe(0);
    expect(fixture.nativeElement.querySelector('.verdict')?.textContent).toContain('Not proven identical');
  });


  it('shows the feature-off hint from a 404 and no verdict without a peer', () => {
    component.docId = 'DOC-42';
    fixture.detectChanges();
    http.expectOne('/config/peer.json').flush({ peer_app_url: '' });

    component.load();
    http.expectOne('/api/v1/reports/archive/documents/DOC-42').flush(
      { error: 'archive feature is not enabled', hint: 'set ARCHIVE_STORE' },
      { status: 404, statusText: 'Not Found' },
    );
    // forkJoin cancels the sibling hash request once the document request errors
    expect(http.expectOne('/api/v1/reports/archive/documents/DOC-42/hash').cancelled).toBeTrue();

    expect(component.sides.length).toBe(1);
    expect(component.sides[0].error).toContain('archive feature is not enabled');
    expect(component.sides[0].error).toContain('ARCHIVE_STORE');
    expect(component.verdict).toBeNull();
  });
});
