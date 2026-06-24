import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { DashboardComponent } from './dashboard.component';
import { provideHttpClient, withInterceptorsFromDi } from '@angular/common/http';
import { provideCharts, withDefaultRegisterables } from 'ng2-charts';

describe('DashboardComponent', () => {
  let component: DashboardComponent;
  let fixture: ComponentFixture<DashboardComponent>;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
    imports: [DashboardComponent,
        NoopAnimationsModule],
    providers: [provideHttpClient(withInterceptorsFromDi()), provideHttpClientTesting(), provideCharts(withDefaultRegisterables())]
}).compileComponents();

    fixture = TestBed.createComponent(DashboardComponent);
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
    expect(component.stats).toBeNull();
  });

  it('should load dashboard stats', fakeAsync(() => {
    fixture.detectChanges();
    const reqs = httpMock.match('/api/v1/admin/metrics/summary');
    reqs.forEach(r => r.flush({ users: { total: 42, active: 10 }, storage: { total_used_bytes: 1024 }, audit: {} }));
    tick();
    fixture.detectChanges();
    expect(component.loading).toBeFalse();
    expect(component.stats).toBeTruthy();
    expect(component.stats!.totalUsers).toBeGreaterThan(0);
  }));

  it('should display stat cards when loaded', fakeAsync(() => {
    fixture.detectChanges();
    const reqs = httpMock.match('/api/v1/admin/metrics/summary');
    reqs.forEach(r => r.flush({ users: { total: 42, active: 10 }, storage: { total_used_bytes: 1024 }, audit: {} }));
    tick();
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    const statCards = compiled.querySelectorAll('.stat-card');
    expect(statCards.length).toBe(4);
  }));

  it('should show page title', fakeAsync(() => {
    fixture.detectChanges();
    const reqs = httpMock.match('/api/v1/admin/metrics/summary');
    reqs.forEach(r => r.flush({ users: { total: 1, active: 1 }, storage: {}, audit: {} }));
    tick();
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Dashboard');
  }));
});
