import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { Router } from '@angular/router';
import { Subject, of, throwError } from 'rxjs';
import { LoginComponent } from './login.component';
import { ApiError } from '../../core/models/api-error';
import { AuthResponse } from '../../core/models/auth.model';
import { OtterWorksApiService } from '../../core/services/otterworks-api.service';
import { SessionService } from '../../core/services/session.service';

function authResponse(overrides: Partial<AuthResponse> = {}): AuthResponse {
  return {
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    tokenType: 'Bearer',
    expiresIn: 3600,
    user: { id: 'u1', email: 'otter@otterworks.io', displayName: 'Otter' },
    ...overrides,
  };
}

describe('LoginComponent', () => {
  let fixture: ComponentFixture<LoginComponent>;
  let component: LoginComponent;
  let api: jasmine.SpyObj<OtterWorksApiService>;
  let session: SessionService;
  let router: Router;

  beforeEach(async () => {
    localStorage.clear();
    api = jasmine.createSpyObj<OtterWorksApiService>('OtterWorksApiService', ['login']);

    await TestBed.configureTestingModule({
      imports: [LoginComponent, HttpClientTestingModule, RouterTestingModule, NoopAnimationsModule],
      providers: [{ provide: OtterWorksApiService, useValue: api }],
    }).compileComponents();

    fixture = TestBed.createComponent(LoginComponent);
    component = fixture.componentInstance;
    session = TestBed.inject(SessionService);
    router = TestBed.inject(Router);
    spyOn(router, 'navigate').and.resolveTo(true);
    fixture.detectChanges();
  });

  function setCredentials(email: string, password: string): void {
    component.loginForm.setValue({ email, password });
    fixture.detectChanges();
  }

  function submitButton(): HTMLButtonElement {
    return fixture.nativeElement.querySelector('button[type="submit"]') as HTMLButtonElement;
  }

  it('renders the empty state: blank fields, no error, no progress bar, disabled submit', () => {
    const element = fixture.nativeElement as HTMLElement;
    expect(component.loginForm.getRawValue()).toEqual({ email: '', password: '' });
    expect(element.textContent).toContain('Sign in');
    expect(element.textContent).toContain('Welcome back to OtterWorks.');
    expect(element.textContent).toContain('No account?');
    expect(element.querySelector('input[type="password"]')).toBeTruthy();
    expect(element.querySelector('.error-message')).toBeNull();
    expect(element.querySelector('mat-progress-bar')).toBeNull();
    expect(submitButton().disabled).toBeTrue();
  });

  it('keeps submit disabled when only one field is filled', () => {
    setCredentials('otter@otterworks.io', '');
    expect(component.canSubmit()).toBeFalse();

    setCredentials('', 'secret');
    expect(component.canSubmit()).toBeFalse();
  });

  it('keeps submit disabled for a whitespace-only email but enables it for a whitespace-only password', () => {
    setCredentials('   ', 'secret');
    expect(component.canSubmit()).toBeFalse();

    setCredentials('otter@otterworks.io', '   ');
    expect(component.canSubmit()).toBeTrue();
  });

  it('enables submit for any non-blank email without format validation', () => {
    setCredentials('not-an-email', 'x');
    fixture.detectChanges();
    expect(component.canSubmit()).toBeTrue();
    expect(submitButton().disabled).toBeFalse();
  });

  it('sends a trimmed email and the password verbatim', () => {
    api.login.and.returnValue(of(authResponse()));
    setCredentials('  otter@otterworks.io  ', '  pass  ');
    component.onSubmit();

    expect(api.login).toHaveBeenCalledWith('otter@otterworks.io', '  pass  ');
  });

  it('stores the session and navigates to documents on success', () => {
    const response = authResponse();
    api.login.and.returnValue(of(response));
    setCredentials('otter@otterworks.io', 'secret');
    component.onSubmit();

    expect(session.accessToken()).toBe('access-token');
    expect(session.currentUserName()).toBe('Otter');
    expect(router.navigate).toHaveBeenCalledWith(['/documents']);
    expect(component.isBusy).toBeFalse();
    expect(component.errorMessage).toBeNull();
  });

  it('shows the empty-response error when a 2xx response carries no access token', () => {
    api.login.and.returnValue(of(authResponse({ accessToken: '' })));
    setCredentials('otter@otterworks.io', 'secret');
    component.onSubmit();
    fixture.detectChanges();

    expect(component.errorMessage).toBe('Login succeeded but the server returned an empty response.');
    expect(session.isAuthenticated()).toBeFalse();
    expect(router.navigate).not.toHaveBeenCalled();
    expect(component.isBusy).toBeFalse();
  });

  it('shows the server-derived error, keeps the entered values and re-enables submit', () => {
    api.login.and.returnValue(throwError(() => new ApiError(401, 'Invalid credentials')));
    setCredentials('otter@otterworks.io', 'secret');
    component.onSubmit();
    fixture.detectChanges();

    const error = fixture.nativeElement.querySelector('.error-message') as HTMLElement;
    expect(error.textContent).toContain('Invalid credentials');
    expect(component.loginForm.getRawValue()).toEqual({
      email: 'otter@otterworks.io',
      password: 'secret',
    });
    expect(component.isBusy).toBeFalse();
    expect(submitButton().disabled).toBeFalse();
    expect(router.navigate).not.toHaveBeenCalled();
  });

  it('shows a progress bar while busy, clears the previous error and blocks re-submission', () => {
    const pending = new Subject<AuthResponse>();
    api.login.and.returnValue(pending.asObservable());
    component.errorMessage = 'stale error';
    setCredentials('otter@otterworks.io', 'secret');

    component.onSubmit();
    fixture.detectChanges();

    expect(component.isBusy).toBeTrue();
    expect(component.errorMessage).toBeNull();
    expect(fixture.nativeElement.querySelector('mat-progress-bar')).toBeTruthy();
    expect(submitButton().disabled).toBeTrue();
    expect(component.loginForm.enabled).toBeTrue();

    component.onSubmit();
    expect(api.login).toHaveBeenCalledTimes(1);

    pending.next(authResponse());
    pending.complete();
    fixture.detectChanges();
    expect(component.isBusy).toBeFalse();
    expect(fixture.nativeElement.querySelector('mat-progress-bar')).toBeNull();
  });

  it('does not call the API when submitted with an incomplete form', () => {
    component.onSubmit();
    expect(api.login).not.toHaveBeenCalled();
  });

  it('submits the form on enter (ngSubmit) when enabled', () => {
    api.login.and.returnValue(of(authResponse()));
    setCredentials('otter@otterworks.io', 'secret');
    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit')
    );

    expect(api.login).toHaveBeenCalled();
  });

  it('navigates to register from "Create one" without calling the API, even while busy', () => {
    api.login.and.returnValue(new Subject<AuthResponse>().asObservable());
    setCredentials('otter@otterworks.io', 'secret');
    component.onSubmit();
    fixture.detectChanges();

    const link = fixture.nativeElement.querySelector('.link-button') as HTMLButtonElement;
    expect(link.disabled).toBeFalse();
    link.click();

    expect(router.navigate).toHaveBeenCalledWith(['/register']);
    expect(api.login).toHaveBeenCalledTimes(1);
  });
});
