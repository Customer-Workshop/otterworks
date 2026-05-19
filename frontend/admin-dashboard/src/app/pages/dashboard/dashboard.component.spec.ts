import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { of, Subject } from 'rxjs';
import { DashboardComponent } from './dashboard.component';
import { AdminApiService } from '../../core/services/admin-api.service';

const mockStats = {
  totalUsers: 120,
  activeUsers: 85,
  totalDocuments: 500,
  storageUsed: 1073741824,
  usersGrowth: 5,
  documentsGrowth: 12,
  storageGrowth: 3,
  sessionsGrowth: 8,
};

const mockReport = {
  activeUsers: [{ label: 'Mon', value: 10 }],
  storageUsage: [{ label: 'Mon', value: 50 }],
  documentActivity: [{ label: 'Mon', value: 15 }],
  topFileTypes: [{ label: 'PDF', value: 30 }],
  userSignups: [{ label: 'Mon', value: 5 }],
  peakHours: [{ label: '9am', value: 20 }],
};

describe('DashboardComponent', () => {
  let component: DashboardComponent;
  let fixture: ComponentFixture<DashboardComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        DashboardComponent,
        NoopAnimationsModule,
      ],
      providers: [
        {
          provide: AdminApiService,
          useValue: {
            getDashboardStats: () => of(mockStats),
            getAnalyticsReport: () => of(mockReport),
            statsChanged$: new Subject<void>(),
          },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(DashboardComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should start with loading state', () => {
    expect(component.loading).toBeTrue();
    expect(component.stats).toBeNull();
  });

  it('should load dashboard stats', () => {
    fixture.detectChanges();
    expect(component.loading).toBeFalse();
    expect(component.stats).toBeTruthy();
    expect(component.stats!.totalUsers).toBeGreaterThan(0);
  });

  it('should display stat cards when loaded', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    const statCards = compiled.querySelectorAll('.stat-card');
    expect(statCards.length).toBe(4);
  });

  it('should show page title', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Dashboard');
  });
});
