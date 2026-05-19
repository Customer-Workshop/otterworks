import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { of } from 'rxjs';
import { AnalyticsComponent } from './analytics.component';
import { AdminApiService } from '../../core/services/admin-api.service';

const mockReport = {
  activeUsers: [{ label: 'Mon', value: 10 }],
  storageUsage: [{ label: 'Mon', value: 50 }],
  documentActivity: [{ label: 'Mon', value: 15 }],
  topFileTypes: [{ label: 'PDF', value: 30 }],
  userSignups: [{ label: 'Mon', value: 5 }],
  peakHours: [{ label: '9am', value: 20 }],
};

describe('AnalyticsComponent', () => {
  let component: AnalyticsComponent;
  let fixture: ComponentFixture<AnalyticsComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        AnalyticsComponent,
        NoopAnimationsModule,
      ],
      providers: [
        { provide: AdminApiService, useValue: { getAnalyticsReport: () => of(mockReport) } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AnalyticsComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should start with loading state', () => {
    expect(component.loading).toBeTrue();
  });

  it('should load analytics data', () => {
    fixture.detectChanges();
    expect(component.loading).toBeFalse();
  });

  it('should show page title', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Analytics');
  });

  it('should have chart configurations', () => {
    expect(component.lineChartOptions).toBeDefined();
    expect(component.barChartOptions).toBeDefined();
    expect(component.pieChartOptions).toBeDefined();
  });
});
