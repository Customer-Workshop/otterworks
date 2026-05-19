import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { ActivatedRoute, Router } from '@angular/router';
import { of } from 'rxjs';
import { UserDetailComponent } from './user-detail.component';
import { AdminApiService } from '../../core/services/admin-api.service';

const mockUser = {
  id: '1', displayName: 'Alice', email: 'alice@test.com',
  storageUsed: 500000, storageQuota: 1000000,
  role: 'user', status: 'active',
  createdAt: new Date(), lastActive: new Date(),
};

describe('UserDetailComponent', () => {
  let component: UserDetailComponent;
  let fixture: ComponentFixture<UserDetailComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        UserDetailComponent,
        NoopAnimationsModule,
      ],
      providers: [
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: { get: () => '1' } } },
        },
        { provide: Router, useValue: { navigate: jasmine.createSpy('navigate') } },
        {
          provide: AdminApiService,
          useValue: {
            getUser: () => of(mockUser),
            getUserActivity: () => of([]),
            updateStorageQuota: () => of({}),
            updateUserStatus: () => of({}),
          },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(UserDetailComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should start with loading state', () => {
    expect(component.loading).toBeTrue();
  });

  it('should load user details', () => {
    fixture.detectChanges();
    expect(component.loading).toBeFalse();
    expect(component.user).toBeTruthy();
    expect(component.user!.displayName).toBe('Alice');
  });

  it('should show user name', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Alice');
  });
});
