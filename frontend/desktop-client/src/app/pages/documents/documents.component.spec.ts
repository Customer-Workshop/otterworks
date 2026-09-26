import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { Router } from '@angular/router';
import { Subject, of, throwError } from 'rxjs';
import { DocumentsComponent } from './documents.component';
import { ApiError } from '../../core/models/api-error';
import { DocumentListResponse, OtterDocument } from '../../core/models/document.model';
import { FileListResponse } from '../../core/models/file.model';
import { OtterWorksApiService } from '../../core/services/otterworks-api.service';
import { SessionService } from '../../core/services/session.service';

function makeDocument(overrides: Partial<OtterDocument> = {}): OtterDocument {
  return {
    id: 'doc-1',
    title: 'Release Notes from Windows client',
    content: null,
    content_type: 'text/plain',
    owner_id: 'user-1',
    folder_id: null,
    is_deleted: false,
    word_count: 0,
    version: 1,
    created_at: '2026-07-13T03:24:00',
    updated_at: '2026-07-13T03:24:00',
    ...overrides,
  };
}

function listOf(items: OtterDocument[]): DocumentListResponse {
  return { items, total: items.length, page: 1, size: 50, pages: 1 };
}

const emptyFiles: FileListResponse = { files: [], total: 0, page: 1, page_size: 50 };

describe('DocumentsComponent', () => {
  let api: jasmine.SpyObj<OtterWorksApiService>;
  let session: SessionService;
  let router: Router;
  let fixture: ComponentFixture<DocumentsComponent>;
  let component: DocumentsComponent;

  beforeEach(() => {
    api = jasmine.createSpyObj<OtterWorksApiService>('OtterWorksApiService', [
      'getDocuments',
      'createDocument',
      'getFiles',
    ]);
    api.getDocuments.and.returnValue(of(listOf([])));
    api.getFiles.and.returnValue(of(emptyFiles));

    TestBed.configureTestingModule({
      imports: [DocumentsComponent, HttpClientTestingModule],
      providers: [provideNoopAnimations(), { provide: OtterWorksApiService, useValue: api }],
    });

    session = TestBed.inject(SessionService);
    router = TestBed.inject(Router);
    spyOn(router, 'navigate').and.resolveTo(true);
  });

  async function create(): Promise<void> {
    fixture = TestBed.createComponent(DocumentsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  function query(testId: string): HTMLElement | null {
    return fixture.nativeElement.querySelector(`[data-testid="${testId}"]`);
  }

  function button(testId: string): HTMLButtonElement {
    return fixture.nativeElement.querySelector(`[data-testid="${testId}"]`) as HTMLButtonElement;
  }

  function titleInput(): HTMLInputElement {
    return fixture.nativeElement.querySelector('[data-testid="title-input"]') as HTMLInputElement;
  }

  function typeTitle(value: string): void {
    const input = titleInput();
    input.value = value;
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
  }

  it('loads documents on construction without any user action', async () => {
    await create();

    expect(api.getDocuments).toHaveBeenCalledTimes(1);
    expect(query('status-message')!.textContent!.trim()).toBe('0 document(s).');
  });

  it('shows the busy bar and hides the empty state until the first load completes', async () => {
    const pending = new Subject<DocumentListResponse>();
    api.getDocuments.and.returnValue(pending.asObservable());

    fixture = TestBed.createComponent(DocumentsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();

    expect(component.isBusy()).toBeTrue();
    expect(query('busy-bar')).not.toBeNull();
    expect(query('empty-state')).toBeNull();
    expect(query('status-message')!.textContent!.trim()).toBe('');
    expect(button('refresh-button').disabled).toBeTrue();
    expect(button('files-button').disabled).toBeTrue();
    expect(button('logout-button').disabled).toBeFalse();

    pending.next(listOf([]));
    pending.complete();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(query('busy-bar')).toBeNull();
    expect(query('empty-state')).not.toBeNull();
  });

  it('renders the empty state when there are no documents', async () => {
    await create();

    const empty = query('empty-state')!;
    expect(empty.textContent).toContain('No documents yet');
    expect(empty.textContent).toContain('Create your first document using the box above.');
  });

  it('renders a row per document with word count, version and updated timestamp', async () => {
    api.getDocuments.and.returnValue(of(listOf([makeDocument({ word_count: 12, version: 3 })])));
    await create();

    expect(query('empty-state')).toBeNull();
    expect(query('status-message')!.textContent!.trim()).toBe('1 document(s).');
    const row = fixture.nativeElement.querySelector('.document-row') as HTMLElement;
    expect(row.textContent).toContain('Release Notes from Windows client');
    expect(row.textContent).toContain('12 words · v3');
    expect(row.textContent).toContain('7/13/2026 3:24 AM');
  });

  it('replaces the whole list on Refresh', async () => {
    await create();
    api.getDocuments.and.returnValue(of(listOf([makeDocument({ id: 'doc-2', title: 'Second' })])));

    button('refresh-button').click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(api.getDocuments).toHaveBeenCalledTimes(2);
    expect(component.documents().map(d => d.id)).toEqual(['doc-2']);
    expect(query('status-message')!.textContent!.trim()).toBe('1 document(s).');
  });

  it('loads files into memory without rendering them, updating only the status', async () => {
    await create();
    api.getFiles.and.returnValue(
      of({
        files: [{ id: 'f1', name: 'a.txt', size: 3, content_type: 'text/plain', created_at: null }],
        total: 1,
        page: 1,
        page_size: 50,
      })
    );

    button('files-button').click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(component.files().length).toBe(1);
    expect(query('status-message')!.textContent!.trim()).toBe('1 file(s).');
    expect(fixture.nativeElement.textContent).not.toContain('a.txt');
  });

  it('disables New while the title is empty or whitespace only, and enables it once filled', async () => {
    await create();

    expect(button('create-button').disabled).toBeTrue();

    typeTitle('   ');
    expect(button('create-button').disabled).toBeTrue();

    typeTitle('Release Notes');
    expect(button('create-button').disabled).toBeFalse();
  });

  it('posts the trimmed title, clears the box, shows the created status and reloads', async () => {
    await create();
    const created = makeDocument({ id: 'doc-9', title: 'Release Notes' });
    api.createDocument.and.returnValue(of(created));
    const statuses: string[] = [];
    api.getDocuments.and.callFake(() => {
      statuses.push(component.statusMessage());
      return of(listOf([created]));
    });

    typeTitle('  Release Notes  ');
    button('create-button').click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(api.createDocument).toHaveBeenCalledOnceWith('Release Notes');
    expect(statuses).toEqual(['Created "Release Notes".']);
    expect(titleInput().value).toBe('');
    expect(query('status-message')!.textContent!.trim()).toBe('1 document(s).');
    expect(fixture.nativeElement.textContent).toContain('Release Notes');
  });

  it('shows API errors in the footer and keeps the previous list', async () => {
    api.getDocuments.and.returnValue(of(listOf([makeDocument()])));
    await create();
    api.getDocuments.and.returnValue(throwError(() => new ApiError(401, 'Unauthorized')));

    button('refresh-button').click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(query('error-message')!.textContent!.trim()).toBe('Unauthorized');
    expect(component.documents().length).toBe(1);
  });

  it('clears the error when the next command starts', async () => {
    api.getDocuments.and.returnValue(throwError(() => new ApiError(500, 'Boom')));
    await create();
    expect(query('error-message')).not.toBeNull();

    api.getDocuments.and.returnValue(of(listOf([])));
    button('refresh-button').click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(query('error-message')).toBeNull();
  });

  it('guards each command against re-entrancy while it is in flight', async () => {
    const pending = new Subject<DocumentListResponse>();
    api.getDocuments.and.returnValue(pending.asObservable());

    fixture = TestBed.createComponent(DocumentsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();

    void component.refresh();
    void component.refresh();
    expect(api.getDocuments).toHaveBeenCalledTimes(1);

    pending.next(listOf([]));
    pending.complete();
    await fixture.whenStable();
  });

  it('clears the session locally and returns to Login on Log out, with no API call', async () => {
    await create();
    spyOn(session, 'clear').and.callThrough();

    button('logout-button').click();

    expect(session.clear).toHaveBeenCalled();
    expect(router.navigate).toHaveBeenCalledWith(['/login']);
    expect(api.getFiles).not.toHaveBeenCalled();
    expect(api.createDocument).not.toHaveBeenCalled();
  });

  it('log out stays enabled while a request is in flight', async () => {
    api.getDocuments.and.returnValue(new Subject<DocumentListResponse>().asObservable());

    fixture = TestBed.createComponent(DocumentsComponent);
    fixture.detectChanges();

    expect(button('logout-button').disabled).toBeFalse();
  });
});
