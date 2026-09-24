import { TestBed } from '@angular/core/testing';
import { HTTP_INTERCEPTORS, HttpClient, HttpContext } from '@angular/common/http';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { JwtInterceptor } from './jwt.interceptor';
import { AuthService } from '../services/auth.service';
import { PEER_REQUEST } from '../services/migration-api.service';

describe('JwtInterceptor', () => {
  let http: HttpClient;
  let ctrl: HttpTestingController;
  let auth: jasmine.SpyObj<AuthService>;

  beforeEach(() => {
    auth = jasmine.createSpyObj<AuthService>('AuthService', ['getToken', 'logout']);
    auth.getToken.and.returnValue('tok');
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [
        { provide: AuthService, useValue: auth },
        { provide: HTTP_INTERCEPTORS, useClass: JwtInterceptor, multi: true },
      ],
    });
    http = TestBed.inject(HttpClient);
    ctrl = TestBed.inject(HttpTestingController);
  });

  afterEach(() => ctrl.verify());

  it('logs out on a 401 from the local API', () => {
    http.get('/api/v1/reports/reconciliation/latest').subscribe({ error: () => undefined });
    const req = ctrl.expectOne('/api/v1/reports/reconciliation/latest');
    expect(req.request.headers.get('Authorization')).toBe('Bearer tok');
    req.flush({}, { status: 401, statusText: 'Unauthorized' });
    expect(auth.logout).toHaveBeenCalled();
  });

  it('keeps the session when the peer deployment returns 401', () => {
    http.get('https://peer.example/api/v1/reports/archive/documents/D1', {
      context: new HttpContext().set(PEER_REQUEST, true),
    }).subscribe({ error: () => undefined });
    ctrl.expectOne('https://peer.example/api/v1/reports/archive/documents/D1')
      .flush({}, { status: 401, statusText: 'Unauthorized' });
    expect(auth.logout).not.toHaveBeenCalled();
  });
});
