import { ComponentFixture, TestBed, fakeAsync, tick, flush, discardPeriodicTasks } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { UsersComponent } from './users.component';
import { provideHttpClient, withInterceptorsFromDi } from '@angular/common/http';

describe('UsersComponent', () => {
  let component: UsersComponent;
  let fixture: ComponentFixture<UsersComponent>;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
    imports: [UsersComponent,
        RouterTestingModule,
        NoopAnimationsModule],
    providers: [provideHttpClient(withInterceptorsFromDi()), provideHttpClientTesting()]
}).compileComponents();

    fixture = TestBed.createComponent(UsersComponent);
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

  it('should load users', fakeAsync(() => {
    fixture.detectChanges();
    const req = httpMock.expectOne('/api/v1/admin/users');
    req.flush({ users: [{ id: '1', email: 'a@b.c', display_name: 'Alice', role: 'admin', status: 'active', created_at: '2024-01-01' }] });
    flush();
    fixture.detectChanges();
    expect(component.loading).toBeFalse();
    expect(component.dataSource.data.length).toBeGreaterThan(0);
    flush();
  }));

  it('should have correct displayed columns', () => {
    expect(component.displayedColumns).toEqual([
      'displayName', 'role', 'status', 'department', 'lastLogin', 'actions',
    ]);
  });

  it('should apply text filter', fakeAsync(() => {
    fixture.detectChanges();
    const req = httpMock.expectOne('/api/v1/admin/users');
    req.flush({ users: [{ id: '1', email: 'alice@b.c', display_name: 'Alice', role: 'admin', status: 'active', created_at: '2024-01-01' }] });
    flush();
    fixture.detectChanges();
    const event = { target: { value: 'alice' } } as unknown as Event;
    component.applyFilter(event);
    expect(component.dataSource.filter).toBe('alice');
    flush();
  }));

  it('should display page title', fakeAsync(() => {
    fixture.detectChanges();
    const req = httpMock.expectOne('/api/v1/admin/users');
    req.flush({ users: [] });
    flush();
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('User Management');
    flush();
  }));
});
