import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { MigrationApiService } from './migration-api.service';

describe('MigrationApiService', () => {
  let service: MigrationApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [HttpClientTestingModule] });
    service = TestBed.inject(MigrationApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('uses the /api/v1 gateway base for reconciliation reports', () => {
    service.getReport('latest').subscribe();
    http.expectOne('/api/v1/reports/reconciliation/latest').flush({ run_id: 'r1' });
    expect(service.csvUrl('r 1')).toBe('/api/v1/reports/reconciliation/r%201.csv');
    expect(service.htmlUrl('r1')).toBe('/api/v1/reports/reconciliation/r1.html');
  });

  it('builds local and peer document URLs', () => {
    expect(service.documentUrl('DOC1')).toBe('/api/v1/archive/documents/DOC1');
    expect(service.documentUrl('DOC1', 'https://peer.example')).toBe('https://peer.example/api/archive/documents/DOC1');
  });

  it('reads PEER_APP_URL from /config/peer.json and strips trailing slashes', () => {
    let peer = '';
    service.peerAppUrl().subscribe(p => (peer = p));
    http.expectOne('/config/peer.json').flush({ peer_app_url: 'https://api-t-peer.example/' });
    expect(peer).toBe('https://api-t-peer.example');
  });

  it('treats a missing peer config as no peer', () => {
    let peer = 'unset';
    service.peerAppUrl().subscribe(p => (peer = p));
    http.expectOne('/config/peer.json').flush('nope', { status: 404, statusText: 'Not Found' });
    expect(peer).toBe('');
  });
});
