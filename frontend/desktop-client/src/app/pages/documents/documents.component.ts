import { Component, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatListModule } from '@angular/material/list';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { firstValueFrom } from 'rxjs';
import { ApiError } from '../../core/models/api-error';
import { OtterDocument } from '../../core/models/document.model';
import { FileItem } from '../../core/models/file.model';
import { OtterWorksApiService } from '../../core/services/otterworks-api.service';
import { SessionService } from '../../core/services/session.service';

/**
 * Port of Views/DocumentsView.xaml + ViewModels/DocumentsViewModel.cs: the list of the
 * signed-in user's documents with a create box, a Files probe that only updates the status
 * text, and a log out action.
 */
@Component({
  selector: 'app-documents-page',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatListModule,
    MatProgressBarModule,
  ],
  template: `
    <section class="documents">
      <div class="toolbar">
        <div class="heading">
          <h2>Documents</h2>
          <span class="status" data-testid="status-message">{{ statusMessage() }}</span>
        </div>
        <div class="actions">
          <button
            type="button"
            mat-stroked-button
            class="secondary"
            data-testid="refresh-button"
            [disabled]="isBusy() || isLoadingDocuments()"
            (click)="refresh()"
          >
            Refresh
          </button>
          <button
            type="button"
            mat-stroked-button
            class="secondary"
            data-testid="files-button"
            [disabled]="isBusy() || isLoadingFiles()"
            (click)="loadFiles()"
          >
            Files
          </button>
          <button
            type="button"
            mat-stroked-button
            class="secondary"
            data-testid="logout-button"
            (click)="logout()"
          >
            Log out
          </button>
        </div>
      </div>

      <div class="card create-row">
        <mat-form-field appearance="outline" class="title-field" subscriptSizing="dynamic">
          <input
            matInput
            type="text"
            placeholder="New document title"
            data-testid="title-input"
            [formControl]="titleControl"
          />
        </mat-form-field>
        <button
          type="button"
          mat-flat-button
          color="primary"
          class="create-button"
          data-testid="create-button"
          [disabled]="!canCreate()"
          (click)="create()"
        >
          New
        </button>
      </div>

      <div class="card list-card">
        <mat-selection-list [multiple]="false" class="document-list" data-testid="document-list">
          <mat-list-option
            *ngFor="let document of documents(); trackBy: trackById"
            [value]="document"
            class="document-row"
          >
            <div class="row">
              <div class="row-main">
                <div class="row-title">{{ document.title }}</div>
                <div class="row-meta">{{ document.word_count }} words &middot; v{{ document.version }}</div>
              </div>
              <div class="row-updated">{{ formatUpdatedAt(document.updated_at) }}</div>
            </div>
          </mat-list-option>
        </mat-selection-list>

        <div class="empty-state" *ngIf="isEmpty()" data-testid="empty-state">
          <div class="empty-title">No documents yet</div>
          <div class="empty-hint">Create your first document using the box above.</div>
        </div>
      </div>

      <div class="footer">
        <mat-progress-bar
          *ngIf="isBusy()"
          mode="indeterminate"
          data-testid="busy-bar"
        ></mat-progress-bar>
        <div class="error" *ngIf="errorMessage()" data-testid="error-message">{{ errorMessage() }}</div>
      </div>
    </section>
  `,
  styles: [`
    .documents {
      display: flex;
      flex-direction: column;
      margin: 24px;
      height: calc(100vh - 100px);
    }

    .toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 16px;
    }

    .heading {
      display: flex;
      align-items: baseline;
    }

    .heading h2 {
      font-size: 22px;
      font-weight: bold;
      color: #111827;
    }

    .status {
      margin-left: 12px;
      color: #6b7280;
    }

    .actions {
      display: flex;
      gap: 8px;
    }

    .secondary.mat-mdc-outlined-button {
      background: #ffffff;
      border-color: #d1d5db;
      color: #111827;
    }

    .card {
      background: #ffffff;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
    }

    .create-row {
      display: flex;
      align-items: center;
      padding: 12px;
      margin-bottom: 16px;
    }

    .title-field {
      flex: 1;
      min-width: 0;
      font-size: 14px;
    }

    .create-button {
      min-width: 90px;
      margin-left: 10px;
    }

    .list-card {
      position: relative;
      flex: 1;
      min-height: 0;
      overflow: auto;
    }

    .document-list {
      padding-top: 0;
    }

    .row {
      display: flex;
      align-items: center;
      width: 100%;
      gap: 12px;
    }

    .row-main {
      flex: 1;
      min-width: 0;
    }

    .row-title {
      font-size: 15px;
      font-weight: 600;
      color: #111827;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .row-meta {
      font-size: 12px;
      color: #6b7280;
      margin-top: 2px;
    }

    .row-updated {
      font-size: 12px;
      color: #6b7280;
      white-space: nowrap;
    }

    .empty-state {
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      text-align: center;
    }

    .empty-title {
      font-size: 16px;
      font-weight: 600;
      color: #374151;
    }

    .empty-hint {
      color: #6b7280;
      margin-top: 4px;
    }

    .footer {
      margin-top: 12px;
    }

    .error {
      color: #dc2626;
      margin-top: 8px;
      white-space: pre-wrap;
    }
  `],
})
export class DocumentsComponent {
  private readonly api = inject(OtterWorksApiService);
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);

  readonly titleControl = new FormControl('', { nonNullable: true });

  private readonly documentsSignal = signal<OtterDocument[]>([]);
  private readonly filesSignal = signal<FileItem[]>([]);
  private readonly statusSignal = signal('');
  private readonly errorSignal = signal('');
  private readonly busySignal = signal(false);
  private readonly hasLoadedSignal = signal(false);
  private readonly titleSignal = signal('');

  private readonly loadingDocumentsSignal = signal(false);
  private readonly loadingFilesSignal = signal(false);
  private readonly creatingSignal = signal(false);

  readonly documents = this.documentsSignal.asReadonly();
  /** Loaded by the Files button but never rendered, mirroring DocumentsViewModel.Files. */
  readonly files = this.filesSignal.asReadonly();
  readonly statusMessage = this.statusSignal.asReadonly();
  readonly errorMessage = this.errorSignal.asReadonly();
  readonly isBusy = this.busySignal.asReadonly();
  readonly isLoadingDocuments = this.loadingDocumentsSignal.asReadonly();
  readonly isLoadingFiles = this.loadingFilesSignal.asReadonly();

  readonly isEmpty = computed(
    () => this.hasLoadedSignal() && this.documentsSignal().length === 0 && !this.busySignal()
  );

  readonly canCreate = computed(
    () => !this.busySignal() && !this.creatingSignal() && this.titleSignal().trim().length > 0
  );

  constructor() {
    this.titleControl.valueChanges.subscribe(value => this.titleSignal.set(value ?? ''));
    void this.loadDocuments();
  }

  trackById(_index: number, document: OtterDocument): string {
    return document.id;
  }

  /** WPF renders UpdatedAt with the general short date/time format, e.g. "7/13/2026 3:24 AM". */
  formatUpdatedAt(updatedAt: string | null): string {
    if (!updatedAt) {
      return '';
    }
    const parsed = new Date(updatedAt);
    if (Number.isNaN(parsed.getTime())) {
      return '';
    }
    const date = `${parsed.getMonth() + 1}/${parsed.getDate()}/${parsed.getFullYear()}`;
    const hours24 = parsed.getHours();
    const hours = hours24 % 12 === 0 ? 12 : hours24 % 12;
    const minutes = `${parsed.getMinutes()}`.padStart(2, '0');
    return `${date} ${hours}:${minutes} ${hours24 < 12 ? 'AM' : 'PM'}`;
  }

  async refresh(): Promise<void> {
    if (this.loadingDocumentsSignal()) {
      return;
    }
    await this.loadDocuments();
  }

  async create(): Promise<void> {
    if (this.creatingSignal()) {
      return;
    }
    const title = this.titleControl.value.trim();
    if (title.length === 0) {
      return;
    }

    this.creatingSignal.set(true);
    this.errorSignal.set('');
    this.busySignal.set(true);
    try {
      const created = await firstValueFrom(this.api.createDocument(title));
      this.titleControl.setValue('');
      if (created) {
        this.statusSignal.set(`Created "${created.title}".`);
      }
      await this.loadDocuments();
    } catch (error: unknown) {
      this.errorSignal.set(DocumentsComponent.messageOf(error));
    } finally {
      this.busySignal.set(false);
      this.creatingSignal.set(false);
    }
  }

  async loadFiles(): Promise<void> {
    if (this.loadingFilesSignal()) {
      return;
    }

    this.loadingFilesSignal.set(true);
    this.errorSignal.set('');
    this.busySignal.set(true);
    try {
      const result = await firstValueFrom(this.api.getFiles());
      const files = result?.files ?? [];
      this.filesSignal.set(files);
      this.statusSignal.set(`${files.length} file(s).`);
    } catch (error: unknown) {
      this.errorSignal.set(DocumentsComponent.messageOf(error));
    } finally {
      this.busySignal.set(false);
      this.loadingFilesSignal.set(false);
    }
  }

  /** Clears the session locally — the legacy client makes no API call on logout. */
  logout(): void {
    this.session.clear();
    void this.router.navigate(['/login']);
  }

  private async loadDocuments(): Promise<void> {
    this.loadingDocumentsSignal.set(true);
    this.errorSignal.set('');
    this.busySignal.set(true);
    try {
      const result = await firstValueFrom(this.api.getDocuments());
      const items = result?.items ?? [];
      this.documentsSignal.set(items);
      this.statusSignal.set(`${items.length} document(s).`);
    } catch (error: unknown) {
      this.errorSignal.set(DocumentsComponent.messageOf(error));
    } finally {
      this.hasLoadedSignal.set(true);
      this.busySignal.set(false);
      this.loadingDocumentsSignal.set(false);
    }
  }

  private static messageOf(error: unknown): string {
    if (error instanceof ApiError || error instanceof Error) {
      return error.message;
    }
    return String(error);
  }
}
