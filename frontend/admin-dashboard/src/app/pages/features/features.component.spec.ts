import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { of } from 'rxjs';
import { FeaturesComponent } from './features.component';
import { AdminApiService } from '../../core/services/admin-api.service';

const mockFlags = [
  { id: '1', name: 'dark_mode', description: 'Enable dark mode', enabled: true, scope: 'global', updatedAt: new Date() },
];

describe('FeaturesComponent', () => {
  let component: FeaturesComponent;
  let fixture: ComponentFixture<FeaturesComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        FeaturesComponent,
        NoopAnimationsModule,
      ],
      providers: [
        {
          provide: AdminApiService,
          useValue: {
            getFeatureFlags: () => of(mockFlags),
            toggleFeatureFlag: () => of({}),
          },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(FeaturesComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should start with loading state', () => {
    expect(component.loading).toBeTrue();
  });

  it('should load feature flags', () => {
    fixture.detectChanges();
    expect(component.loading).toBeFalse();
    expect(component.flags.length).toBe(1);
  });

  it('should show page title', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Feature');
  });
});
