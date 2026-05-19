import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { of } from 'rxjs';
import { HealthComponent } from './health.component';
import { AdminApiService } from '../../core/services/admin-api.service';

const mockServices = [
  { name: 'auth-service', status: 'healthy', latency: 12, lastChecked: new Date() },
  { name: 'file-service', status: 'degraded', latency: 250, lastChecked: new Date() },
  { name: 'search-service', status: 'down', latency: 0, lastChecked: new Date() },
];

describe('HealthComponent', () => {
  let component: HealthComponent;
  let fixture: ComponentFixture<HealthComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        HealthComponent,
        NoopAnimationsModule,
      ],
      providers: [
        { provide: AdminApiService, useValue: { getSystemHealth: () => of(mockServices) } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(HealthComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should start with loading state', () => {
    expect(component.loading).toBeTrue();
  });

  it('should load system health data', () => {
    fixture.detectChanges();
    expect(component.loading).toBeFalse();
    expect(component.services.length).toBeGreaterThan(0);
  });

  it('should compute health counts', () => {
    fixture.detectChanges();
    const total = component.healthyCounts.healthy +
                  component.healthyCounts.degraded +
                  component.healthyCounts.down;
    expect(total).toBe(component.services.length);
  });

  it('should display page title', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('System Health');
  });
});
