import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { Router } from '@angular/router';
import { RouterTestingModule } from '@angular/router/testing';
import { Subject, of, throwError } from 'rxjs';
import { ApiError } from '../../core/models/api-error';
import { AuthResponse } from '../../core/models/auth.model';
import { OtterWorksApiService } from '../../core/services/otterworks-api.service';
import { SessionService } from '../../core/services/session.service';
import { RegisterComponent } from './register.component';

function authResponse(overrides: Partial<AuthResponse> = {}): AuthResponse {
  return {
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    tokenType: 'Bearer',
    expiresIn: 3600,
    user: { id: 'u-1', email: 'ada@example.com', displayName: 'Ada Otter' },
    ...overrides,
  };
}

describe('RegisterComponent', () => {
  let fixture: ComponentFixture<RegisterComponent>;
  let component: RegisterComponent;
  let api: jasmine.SpyObj<OtterWorksApiService>;
  let session: SessionService;
  let router: Router;

  beforeEach(async () => {
    localStorage.clear();
    api = jasmine.createSpyObj<OtterWorksApiService>('OtterWorksApiService', ['register']);

    await TestBed.configureTestingModule({
      imports: [
        RegisterComponent,
        HttpClientTestingModule,
        RouterTestingModule,
        NoopAnimationsModule,
      ],
      providers: [{ provide: OtterWorksApiService, useValue: api }],
    }).compileComponents();

    fixture = TestBed.createComponent(RegisterComponent);
    component = fixture.componentInstance;
    session = TestBed.inject(SessionService);
    router = TestBed.inject(Router);
    spyOn(router, 'navigate').and.resolveTo(true);
    fixture.detectChanges();
  });

  function fill(displayName: string, email: string, password: string): void {
    component.form.setValue({ displayName, email, password });
    fixture.detectChanges();
  }

  function text(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  function submitButton(): HTMLButtonElement {
    return (fixture.nativeElement as HTMLElement).querySelector(
      'button[type="submit"]'
    ) as HTMLButtonElement;
  }

  describe('initial state', () => {
    it('renders the card heading, subtitle, labels and password hint', () => {
      expect(text()).toContain('Create account');
      expect(text()).toContain('Get started with OtterWorks.');
      expect(text()).toContain('Display name');
      expect(text()).toContain('Email');
      expect(text()).toContain('Password');
      expect(text()).toContain('At least 8 characters.');
    });

    it('starts with an empty form, no error line, no progress bar and a disabled submit', () => {
      const host = fixture.nativeElement as HTMLElement;
      expect(component.form.getRawValue()).toEqual({
        displayName: '',
        email: '',
        password: '',
      });
      expect(host.querySelector('.error')).toBeNull();
      expect(host.querySelector('mat-progress-bar')).toBeNull();
      expect(submitButton().disabled).toBeTrue();
    });

    it('renders the masked password box and the footer link back to login', () => {
      const host = fixture.nativeElement as HTMLElement;
      expect(host.querySelector('input[type="password"]')).toBeTruthy();
      expect(text()).toContain('Already have an account?');
      const link = host.querySelector('a.link') as HTMLAnchorElement;
      expect(link.textContent?.trim()).toBe('Sign in');
      expect(link.getAttribute('href')).toBe('/login');
    });
  });

  describe('submit enablement', () => {
    it('stays disabled while a required field is blank or whitespace-only', () => {
      fill('Ada Otter', '', 'password123');
      expect(component.canSubmit()).toBeFalse();

      fill('   ', 'ada@example.com', 'password123');
      expect(component.canSubmit()).toBeFalse();

      fill('Ada Otter', '   ', 'password123');
      expect(component.canSubmit()).toBeFalse();

      fill('Ada Otter', 'ada@example.com', '');
      expect(component.canSubmit()).toBeFalse();
      expect(submitButton().disabled).toBeTrue();
    });

    it('enables submit once all three fields are filled, whitespace password included', () => {
      fill('Ada Otter', 'ada@example.com', '    ');
      expect(component.canSubmit()).toBeTrue();
      expect(submitButton().disabled).toBeFalse();
    });

    it('is disabled for the duration of an in-flight request', () => {
      const pending = new Subject<AuthResponse>();
      api.register.and.returnValue(pending.asObservable());

      fill('Ada Otter', 'ada@example.com', 'password123');
      component.register();
      fixture.detectChanges();

      expect(component.isBusy()).toBeTrue();
      expect(component.canSubmit()).toBeFalse();
      expect(submitButton().disabled).toBeTrue();

      component.register();
      expect(api.register).toHaveBeenCalledTimes(1);

      pending.next(authResponse());
      pending.complete();
    });
  });

  describe('client-side validation', () => {
    it('rejects a password shorter than 8 characters without calling the API', () => {
      fill('Ada Otter', 'ada@example.com', 'short');
      component.register();
      fixture.detectChanges();

      expect(api.register).not.toHaveBeenCalled();
      expect(component.isBusy()).toBeFalse();
      expect(component.errorMessage()).toBe('Password must be at least 8 characters.');
      expect(text()).toContain('Password must be at least 8 characters.');
      expect(component.form.getRawValue().password).toBe('short');
      expect(submitButton().disabled).toBeFalse();
    });

    it('does not validate the email format client-side', () => {
      api.register.and.returnValue(of(authResponse()));
      fill('Ada Otter', 'not-an-email', 'password123');
      component.register();

      expect(api.register).toHaveBeenCalledWith('Ada Otter', 'not-an-email', 'password123');
    });
  });

  describe('registration request', () => {
    it('trims the display name and email but sends the password verbatim', () => {
      api.register.and.returnValue(of(authResponse()));
      fill('  Ada Otter  ', '  ada@example.com  ', '  password123  ');
      component.register();

      expect(api.register).toHaveBeenCalledWith(
        'Ada Otter',
        'ada@example.com',
        '  password123  '
      );
    });

    it('shows the progress bar only while the request is in flight', () => {
      const pending = new Subject<AuthResponse>();
      api.register.and.returnValue(pending.asObservable());

      fill('Ada Otter', 'ada@example.com', 'password123');
      component.register();
      fixture.detectChanges();
      expect(
        (fixture.nativeElement as HTMLElement).querySelector('mat-progress-bar')
      ).toBeTruthy();

      pending.next(authResponse());
      pending.complete();
      fixture.detectChanges();
      expect(
        (fixture.nativeElement as HTMLElement).querySelector('mat-progress-bar')
      ).toBeNull();
    });

    it('clears a previous error at the start of a new submit', () => {
      const pending = new Subject<AuthResponse>();
      fill('Ada Otter', 'ada@example.com', 'short');
      component.register();
      expect(component.errorMessage()).toBeTruthy();

      api.register.and.returnValue(pending.asObservable());
      fill('Ada Otter', 'ada@example.com', 'password123');
      component.register();
      expect(component.errorMessage()).toBeNull();

      pending.complete();
    });

    it('stores the session and navigates to documents on success', () => {
      const response = authResponse();
      api.register.and.returnValue(of(response));

      fill('Ada Otter', 'ada@example.com', 'password123');
      component.register();

      expect(session.accessToken()).toBe('access-token');
      expect(session.currentUserName()).toBe('Ada Otter');
      expect(router.navigate).toHaveBeenCalledWith(['/documents']);
      expect(component.isBusy()).toBeFalse();
    });

    it('treats a 2xx response without an access token as a degenerate success', () => {
      api.register.and.returnValue(
        of(authResponse({ accessToken: undefined as unknown as string }))
      );

      fill('Ada Otter', 'ada@example.com', 'password123');
      component.register();
      fixture.detectChanges();

      expect(component.errorMessage()).toBe(
        'Registration succeeded but the server returned an empty response.'
      );
      expect(session.isAuthenticated()).toBeFalse();
      expect(router.navigate).not.toHaveBeenCalled();
      expect(text()).toContain('Registration succeeded but the server returned an empty response.');
    });

    it('shows the server error message verbatim and preserves the entered values', () => {
      api.register.and.returnValue(
        throwError(() => new ApiError(409, 'Email already registered'))
      );

      fill('Ada Otter', 'ada@example.com', 'password123');
      component.register();
      fixture.detectChanges();

      expect(component.errorMessage()).toBe('Email already registered');
      expect(text()).toContain('Email already registered');
      expect(component.form.getRawValue()).toEqual({
        displayName: 'Ada Otter',
        email: 'ada@example.com',
        password: 'password123',
      });
      expect(session.isAuthenticated()).toBeFalse();
      expect(router.navigate).not.toHaveBeenCalled();
      expect(component.isBusy()).toBeFalse();
      expect(submitButton().disabled).toBeFalse();
      expect(
        (fixture.nativeElement as HTMLElement).querySelector('mat-progress-bar')
      ).toBeNull();
    });

    it('shows the transport-failure message when the backend is unreachable', () => {
      api.register.and.returnValue(
        throwError(
          () =>
            new ApiError(
              0,
              'Could not reach the OtterWorks backend. Verify it is running and that the ' +
                'API base URL is correct.'
            )
        )
      );

      fill('Ada Otter', 'ada@example.com', 'password123');
      component.register();

      expect(component.errorMessage()).toContain('Could not reach the OtterWorks backend.');
    });
  });

  it('submits the form when the default (Enter) submit fires', () => {
    api.register.and.returnValue(of(authResponse()));
    fill('Ada Otter', 'ada@example.com', 'password123');

    const form = (fixture.nativeElement as HTMLElement).querySelector(
      'form'
    ) as HTMLFormElement;
    form.dispatchEvent(new Event('submit'));

    expect(api.register).toHaveBeenCalled();
  });
});
