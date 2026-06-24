import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { HealthComponent } from './health.component';
import { provideHttpClient, withInterceptorsFromDi } from '@angular/common/http';

describe('HealthComponent', () => {
  let component: HealthComponent;
  let fixture: ComponentFixture<HealthComponent>;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
    imports: [HealthComponent,
        NoopAnimationsModule],
    providers: [provideHttpClient(withInterceptorsFromDi()), provideHttpClientTesting()]
}).compileComponents();

    fixture = TestBed.createComponent(HealthComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should start with loading state', () => {
    expect(component.loading).toBeTrue();
  });

  it('should load system health data', fakeAsync(() => {
    fixture.detectChanges();
    const req = httpMock.expectOne('/api/v1/admin/health/services');
    req.flush({ services: [{ name: 'auth-service', status: 'healthy', latency_ms: 5 }], timestamp: '2024-01-01T00:00:00Z' });
    tick();
    fixture.detectChanges();
    expect(component.loading).toBeFalse();
    expect(component.services.length).toBeGreaterThan(0);
  }));

  it('should compute health counts', fakeAsync(() => {
    fixture.detectChanges();
    const req = httpMock.expectOne('/api/v1/admin/health/services');
    req.flush({ services: [{ name: 'auth-service', status: 'healthy', latency_ms: 5 }, { name: 'file-service', status: 'degraded', latency_ms: 50 }], timestamp: '2024-01-01T00:00:00Z' });
    tick();
    fixture.detectChanges();
    const total = component.healthyCounts.healthy +
                  component.healthyCounts.degraded +
                  component.healthyCounts.down;
    expect(total).toBe(component.services.length);
  }));

  it('should display page title', fakeAsync(() => {
    fixture.detectChanges();
    const req = httpMock.expectOne('/api/v1/admin/health/services');
    req.flush({ services: [], timestamp: '2024-01-01T00:00:00Z' });
    tick();
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('System Health');
  }));
});
