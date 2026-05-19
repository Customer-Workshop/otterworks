import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { of } from 'rxjs';
import { UsersComponent } from './users.component';
import { AdminApiService } from '../../core/services/admin-api.service';

const mockUsers = [
  { id: '1', displayName: 'Alice', email: 'alice@test.com', role: 'admin', status: 'active', department: 'Engineering', lastLogin: new Date(), storageUsed: 500000, storageQuota: 1000000, createdAt: new Date(), lastActive: new Date() },
  { id: '2', displayName: 'Bob', email: 'bob@test.com', role: 'user', status: 'active', department: 'Marketing', lastLogin: new Date(), storageUsed: 200000, storageQuota: 1000000, createdAt: new Date(), lastActive: new Date() },
];

describe('UsersComponent', () => {
  let component: UsersComponent;
  let fixture: ComponentFixture<UsersComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        UsersComponent,
        NoopAnimationsModule,
      ],
      providers: [
        { provide: Router, useValue: { navigate: jasmine.createSpy('navigate') } },
        {
          provide: AdminApiService,
          useValue: {
            getUsers: () => of(mockUsers),
            updateUserStatus: () => of({}),
            deleteUser: () => of({}),
          },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(UsersComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should start with loading state', () => {
    expect(component.loading).toBeTrue();
  });

  it('should load users', () => {
    fixture.detectChanges();
    expect(component.loading).toBeFalse();
    expect(component.dataSource.data.length).toBeGreaterThan(0);
  });

  it('should have correct displayed columns', () => {
    expect(component.displayedColumns).toEqual([
      'displayName', 'role', 'status', 'department', 'lastLogin', 'actions',
    ]);
  });

  it('should apply text filter', () => {
    fixture.detectChanges();
    const event = { target: { value: 'alice' } } as unknown as Event;
    component.applyFilter(event);
    expect(component.dataSource.filter).toBe('alice');
  });

  it('should display page title', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('User Management');
  });
});
