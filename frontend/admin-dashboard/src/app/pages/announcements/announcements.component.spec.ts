import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { of } from 'rxjs';
import { AnnouncementsComponent } from './announcements.component';
import { AdminApiService } from '../../core/services/admin-api.service';

const mockAnnouncements = [
  { id: '1', title: 'Maintenance', message: 'Scheduled downtime', priority: 'high' as const, status: 'published' as const, targetAudience: 'all', createdAt: new Date() },
];

describe('AnnouncementsComponent', () => {
  let component: AnnouncementsComponent;
  let fixture: ComponentFixture<AnnouncementsComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        AnnouncementsComponent,
        NoopAnimationsModule,
      ],
      providers: [
        {
          provide: AdminApiService,
          useValue: {
            getAnnouncements: () => of(mockAnnouncements),
            createAnnouncement: () => of({}),
            publishAnnouncement: () => of({}),
            deleteAnnouncement: () => of({}),
          },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AnnouncementsComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should start with loading state', () => {
    expect(component.loading).toBeTrue();
  });

  it('should load announcements', () => {
    fixture.detectChanges();
    expect(component.loading).toBeFalse();
    expect(component.announcements.length).toBe(1);
  });

  it('should show page title', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Announcement');
  });
});
