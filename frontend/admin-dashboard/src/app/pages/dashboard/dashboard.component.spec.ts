import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { DashboardComponent } from './dashboard.component';
import { provideHttpClient, withInterceptorsFromDi } from '@angular/common/http';

describe('DashboardComponent', () => {
  let component: DashboardComponent;
  let fixture: ComponentFixture<DashboardComponent>;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        DashboardComponent,
        NoopAnimationsModule,
      ],
      providers: [
        provideHttpClient(withInterceptorsFromDi()),
        provideHttpClientTesting(),
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(DashboardComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should start with loading state', () => {
    expect(component.loading).toBeTrue();
    expect(component.stats).toBeNull();
  });

  it('should load dashboard stats', fakeAsync(() => {
    fixture.detectChanges();
    const requests = httpMock.match('/api/v1/admin/metrics/summary');
    expect(requests.length).toBe(2);
    requests.forEach(request => request.flush({
      users: { total: 10, active: 3 },
      storage: { total_used_bytes: 1024 },
    }));
    tick(700);
    fixture.detectChanges();
    expect(component.loading).toBeFalse();
    expect(component.stats).toBeTruthy();
    expect(component.stats!.totalUsers).toBeGreaterThan(0);
  }));

  it('should display stat cards when loaded', fakeAsync(() => {
    fixture.detectChanges();
    const requests = httpMock.match('/api/v1/admin/metrics/summary');
    expect(requests.length).toBe(2);
    requests.forEach(request => request.flush({
      users: { total: 10, active: 3 },
      storage: { total_used_bytes: 1024 },
    }));
    tick(700);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    const statCards = compiled.querySelectorAll('.stat-card');
    expect(statCards.length).toBe(4);
  }));

  it('should show page title', fakeAsync(() => {
    fixture.detectChanges();
    const requests = httpMock.match('/api/v1/admin/metrics/summary');
    expect(requests.length).toBe(2);
    requests.forEach(request => request.flush({
      users: { total: 10, active: 3 },
      storage: { total_used_bytes: 1024 },
    }));
    tick(700);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Dashboard');
  }));
});
