import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { of } from 'rxjs';
import { IncidentsComponent } from './incidents.component';
import { AdminApiService } from '../../core/services/admin-api.service';

const mockIncidents = [
  { id: '1', title: 'Service down', description: 'API not responding', severity: 'high', status: 'open', active: true, createdAt: new Date() },
];

describe('IncidentsComponent', () => {
  let component: IncidentsComponent;
  let fixture: ComponentFixture<IncidentsComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        IncidentsComponent,
        NoopAnimationsModule,
      ],
      providers: [
        {
          provide: AdminApiService,
          useValue: {
            getIncidents: () => of(mockIncidents),
            getAutoInvestigate: () => of({ enabled: true }),
            setAutoInvestigate: () => of({}),
            createIncident: () => of({}),
            resolveIncident: () => of({}),
            getChaosStatus: () => of({ enabled: false }),
            triggerChaos: () => of({}),
            resetChaos: () => of({ cleared: 0, resolved: 0 }),
          },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(IncidentsComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should show page title', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Incident');
  });

  it('should load incidents', () => {
    fixture.detectChanges();
    expect(component.incidents.length).toBe(1);
  });
});
