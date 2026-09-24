import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { Router } from '@angular/router';
import { AuthService, AuthUser } from './auth.service';

describe('AuthService', () => {
  let service: AuthService;
  let router: Router;
  let httpMock: HttpTestingController;

  /** Fails the gateway login request so the service takes the offline mock path. */
  const gatewayOffline = () =>
    httpMock.expectOne('/api/v1/auth/login').error(new ProgressEvent('error'));

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule, RouterTestingModule],
    });
    service = TestBed.inject(AuthService);
    router = TestBed.inject(Router);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should not be authenticated initially', () => {
    expect(service.isAuthenticated).toBeFalse();
    expect(service.currentUser).toBeNull();
  });

  it('should login successfully with valid credentials', fakeAsync(() => {
    let loggedInUser: AuthUser | undefined;
    service.login('admin@otterworks.io', 'admin123').subscribe(user => {
      loggedInUser = user;
    });
    gatewayOffline();
    tick(900);
    expect(loggedInUser).toBeTruthy();
    expect(loggedInUser!.email).toBe('admin@otterworks.io');
    expect(loggedInUser!.role).toBe('admin');
    expect(service.isAuthenticated).toBeTrue();
    expect(service.currentUser).toBeTruthy();
  }));

  it('should use the gateway token when /api/v1/auth/login succeeds', fakeAsync(() => {
    let loggedInUser: AuthUser | undefined;
    service.login('admin@otterworks.io', 'admin123').subscribe(user => { loggedInUser = user; });
    const req = httpMock.expectOne('/api/v1/auth/login');
    expect(req.request.method).toBe('POST');
    req.flush({
      accessToken: 'gateway.jwt.token',
      refreshToken: 'r',
      tokenType: 'Bearer',
      expiresIn: 3600,
      user: { id: 'u-1', email: 'admin@otterworks.io', displayName: 'Presenter', avatarUrl: null },
    });
    tick();
    expect(loggedInUser!.token).toBe('gateway.jwt.token');
    expect(loggedInUser!.id).toBe('u-1');
    expect(service.getToken()).toBe('gateway.jwt.token');
  }));

  it('should store token in localStorage after login', fakeAsync(() => {
    service.login('admin@otterworks.io', 'admin123').subscribe();
    gatewayOffline();
    tick(900);
    expect(localStorage.getItem('ow_admin_token')).toBeTruthy();
    expect(localStorage.getItem('ow_admin_user')).toBeTruthy();
  }));

  it('should clear auth state on logout', fakeAsync(() => {
    service.login('admin@otterworks.io', 'admin123').subscribe();
    gatewayOffline();
    tick(900);
    spyOn(router, 'navigate');
    service.logout();
    expect(service.isAuthenticated).toBeFalse();
    expect(service.currentUser).toBeNull();
    expect(localStorage.getItem('ow_admin_token')).toBeNull();
    expect(router.navigate).toHaveBeenCalledWith(['/login']);
  }));

  it('should emit user on currentUser$ observable', fakeAsync(() => {
    const emitted: (AuthUser | null)[] = [];
    service.currentUser$.subscribe(user => emitted.push(user));
    service.login('admin@otterworks.io', 'admin123').subscribe();
    gatewayOffline();
    tick(900);
    expect(emitted.length).toBeGreaterThanOrEqual(2);
    expect(emitted[emitted.length - 1]).toBeTruthy();
  }));

  it('should return token from getToken()', fakeAsync(() => {
    expect(service.getToken()).toBeNull();
    service.login('admin@otterworks.io', 'admin123').subscribe();
    gatewayOffline();
    tick(900);
    expect(service.getToken()).toBeTruthy();
    expect(service.getToken()!.startsWith('mock-jwt-token-')).toBeTrue();
  }));

  it('should reject login with empty password', fakeAsync(() => {
    let error: Error | undefined;
    service.login('admin@otterworks.io', '').subscribe({
      error: (e: Error) => { error = e; },
    });
    gatewayOffline();
    tick(900);
    expect(error).toBeTruthy();
    expect(error!.message).toBe('Invalid credentials');
  }));
});
