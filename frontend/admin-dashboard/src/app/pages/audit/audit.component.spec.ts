import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { of } from 'rxjs';
import { AuditComponent } from './audit.component';
import { AdminApiService } from '../../core/services/admin-api.service';

const mockEvents = [
  { id: '1', action: 'LOGIN', user: 'admin', ipAddress: '127.0.0.1', timestamp: new Date(), result: 'SUCCESS', details: '' },
];

describe('AuditComponent', () => {
  let component: AuditComponent;
  let fixture: ComponentFixture<AuditComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        AuditComponent,
        NoopAnimationsModule,
      ],
      providers: [
        { provide: AdminApiService, useValue: { getAuditEvents: () => of(mockEvents) } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AuditComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should start with loading state', () => {
    expect(component.loading).toBeTrue();
  });

  it('should show page title', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Audit');
  });

  it('should load audit events', () => {
    fixture.detectChanges();
    expect(component.loading).toBeFalse();
    expect(component.dataSource.data.length).toBe(1);
  });
});
