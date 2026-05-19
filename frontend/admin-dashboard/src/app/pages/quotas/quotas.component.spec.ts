import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { of } from 'rxjs';
import { QuotasComponent } from './quotas.component';
import { AdminApiService } from '../../core/services/admin-api.service';

const mockUsers = [
  { id: '1', displayName: 'Alice', email: 'alice@test.com', storageUsed: 500000, storageQuota: 1000000, role: 'user', status: 'active', createdAt: new Date(), lastActive: new Date() },
];

describe('QuotasComponent', () => {
  let component: QuotasComponent;
  let fixture: ComponentFixture<QuotasComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        QuotasComponent,
        NoopAnimationsModule,
      ],
      providers: [
        {
          provide: AdminApiService,
          useValue: {
            getUsers: () => of(mockUsers),
            updateStorageQuota: () => of({}),
          },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(QuotasComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should start with loading state', () => {
    expect(component.loading).toBeTrue();
  });

  it('should load quotas data', () => {
    fixture.detectChanges();
    expect(component.loading).toBeFalse();
    expect(component.dataSource.data.length).toBe(1);
  });

  it('should show page title', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Quota');
  });
});
