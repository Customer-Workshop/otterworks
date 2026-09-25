import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule, MatTableDataSource } from '@angular/material/table';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { catchError, of } from 'rxjs';
import { AdminApiService } from '../../core/services/admin-api.service';
import { AuthService } from '../../core/services/auth.service';
import {
  CreateReportRequest,
  Report,
  ReportCategory,
  ReportStatus,
  ReportType,
  REPORT_CATEGORIES,
  REPORT_STATUSES,
  REPORT_TYPES,
} from '../../core/models/report.model';

@Component({
  selector: 'app-reports',
  standalone: true,
  imports: [
    CommonModule, FormsModule, MatCardModule, MatTableModule, MatIconModule, MatButtonModule,
    MatProgressSpinnerModule, MatInputModule, MatFormFieldModule, MatSelectModule,
    MatTooltipModule, MatSnackBarModule,
  ],
  template: `
    <div class="page-container">
      <div class="page-header">
        <div>
          <h1 class="page-title">Reports</h1>
          <p class="page-subtitle">Generated reports from the report service</p>
        </div>
        <div class="header-actions">
          <button mat-stroked-button (click)="loadReports()" [disabled]="loading">
            <mat-icon>refresh</mat-icon>
            Refresh
          </button>
          <button mat-raised-button color="primary" (click)="showCreateForm = !showCreateForm">
            <mat-icon>{{ showCreateForm ? 'close' : 'add' }}</mat-icon>
            {{ showCreateForm ? 'Cancel' : 'New Report' }}
          </button>
        </div>
      </div>

      <mat-card *ngIf="showCreateForm" class="create-form">
        <mat-card-header>
          <mat-card-title>Create Report</mat-card-title>
        </mat-card-header>
        <mat-card-content>
          <mat-form-field appearance="outline" class="full-width">
            <mat-label>Report Name</mat-label>
            <input matInput [(ngModel)]="newReport.reportName" placeholder="Monthly Usage Report">
          </mat-form-field>

          <div class="form-row">
            <mat-form-field appearance="outline">
              <mat-label>Category</mat-label>
              <mat-select [(ngModel)]="newReport.category">
                <mat-option *ngFor="let category of categories" [value]="category">
                  {{ label(category) }}
                </mat-option>
              </mat-select>
            </mat-form-field>

            <mat-form-field appearance="outline">
              <mat-label>Format</mat-label>
              <mat-select [(ngModel)]="newReport.reportType">
                <mat-option *ngFor="let type of types" [value]="type">{{ type }}</mat-option>
              </mat-select>
            </mat-form-field>
          </div>

          <button mat-raised-button color="primary" (click)="createReport()"
            [disabled]="!newReport.reportName || creating">
            {{ creating ? 'Creating...' : 'Create' }}
          </button>
        </mat-card-content>
      </mat-card>

      <div class="toolbar">
        <mat-form-field appearance="outline" class="filter-field">
          <mat-label>Status</mat-label>
          <mat-select [(value)]="statusFilter" (selectionChange)="loadReports()">
            <mat-option value="">All Statuses</mat-option>
            <mat-option *ngFor="let status of statuses" [value]="status">{{ label(status) }}</mat-option>
          </mat-select>
        </mat-form-field>
      </div>

      <div *ngIf="loading" class="loading-container">
        <mat-spinner diameter="40"></mat-spinner>
      </div>

      <div *ngIf="!loading && error" class="error-container">
        <mat-icon>error_outline</mat-icon>
        <p>{{ error }}</p>
        <button mat-stroked-button color="primary" (click)="loadReports()">Retry</button>
      </div>

      <div class="table-container" *ngIf="!loading && !error && dataSource.data.length > 0">
        <table mat-table [dataSource]="dataSource" class="reports-table">
          <ng-container matColumnDef="reportName">
            <th mat-header-cell *matHeaderCellDef>Name</th>
            <td mat-cell *matCellDef="let report">
              <div class="name-cell">
                <span>{{ report.reportName }}</span>
                <span class="report-type">{{ report.reportType }}</span>
              </div>
            </td>
          </ng-container>

          <ng-container matColumnDef="category">
            <th mat-header-cell *matHeaderCellDef>Category</th>
            <td mat-cell *matCellDef="let report">{{ label(report.category) }}</td>
          </ng-container>

          <ng-container matColumnDef="status">
            <th mat-header-cell *matHeaderCellDef>Status</th>
            <td mat-cell *matCellDef="let report">
              <span class="status-chip" [class]="'status-' + report.status">{{ report.status }}</span>
              <span class="status-error" *ngIf="report.errorMessage" [matTooltip]="report.errorMessage">
                <mat-icon>info_outline</mat-icon>
              </span>
            </td>
          </ng-container>

          <ng-container matColumnDef="createdAt">
            <th mat-header-cell *matHeaderCellDef>Created</th>
            <td mat-cell *matCellDef="let report">{{ report.createdAt | date:'medium' }}</td>
          </ng-container>

          <ng-container matColumnDef="actions">
            <th mat-header-cell *matHeaderCellDef>Actions</th>
            <td mat-cell *matCellDef="let report">
              <button mat-icon-button color="primary" aria-label="Download report"
                [disabled]="report.status !== 'COMPLETED' || downloadingId === report.id"
                matTooltip="Download" (click)="downloadReport(report)">
                <mat-icon>download</mat-icon>
              </button>
            </td>
          </ng-container>

          <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
          <tr mat-row *matRowDef="let row; columns: displayedColumns;"></tr>
        </table>
      </div>

      <div *ngIf="!loading && !error && dataSource.data.length === 0" class="empty-state">
        <mat-icon>description</mat-icon>
        <p *ngIf="statusFilter">No {{ label(statusFilter) }} reports</p>
        <p *ngIf="!statusFilter">No reports yet</p>
      </div>
    </div>
  `,
  styles: [`
    .page-container { padding: 0; }
    .page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; }
    .page-title { font-size: 1.5rem; font-weight: 600; color: #333; margin: 0; }
    .page-subtitle { font-size: .85rem; color: #777; margin: 4px 0 0; }
    .header-actions { display: flex; gap: 12px; }

    .create-form { margin-bottom: 24px; }
    .full-width { width: 100%; }
    .form-row { display: flex; gap: 16px; }

    .toolbar { display: flex; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }
    .filter-field { width: 200px; }

    .loading-container { display: flex; justify-content: center; padding: 60px; }

    .error-container { display: flex; flex-direction: column; align-items: center; padding: 60px; color: #c62828; }
    .error-container .mat-icon { font-size: 48px; width: 48px; height: 48px; margin-bottom: 16px; }
    .error-container p { margin-bottom: 16px; }

    .table-container {
      background: white; border-radius: 8px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.08); overflow: hidden;
    }

    .reports-table { width: 100%; }

    .name-cell { display: flex; flex-direction: column; }
    .report-type { font-size: .7rem; color: #999; text-transform: uppercase; }

    .status-chip {
      padding: 3px 8px; border-radius: 4px; font-size: .7rem;
      font-weight: 600; text-transform: uppercase;
    }

    .status-PENDING { background: #eceff1; color: #546e7a; }
    .status-GENERATING { background: #e3f2fd; color: #1565c0; }
    .status-COMPLETED { background: #e8f5e9; color: #2e7d32; }
    .status-FAILED { background: #ffebee; color: #c62828; }

    .status-error { color: #c62828; margin-left: 6px; vertical-align: middle; }
    .status-error .mat-icon { font-size: 16px; width: 16px; height: 16px; }

    .empty-state { display: flex; flex-direction: column; align-items: center; padding: 60px; color: #999; }
    .empty-state .mat-icon { font-size: 48px; width: 48px; height: 48px; margin-bottom: 12px; }
  `],
})
export class ReportsComponent implements OnInit {
  displayedColumns = ['reportName', 'category', 'status', 'createdAt', 'actions'];
  dataSource = new MatTableDataSource<Report>([]);
  loading = true;
  creating = false;
  error = '';
  statusFilter: ReportStatus | '' = '';
  showCreateForm = false;
  downloadingId: number | null = null;

  readonly statuses = REPORT_STATUSES;
  readonly categories = REPORT_CATEGORIES;
  readonly types = REPORT_TYPES;

  newReport: { reportName: string; category: ReportCategory; reportType: ReportType } = {
    reportName: '',
    category: 'USAGE_ANALYTICS',
    reportType: 'CSV',
  };

  constructor(
    private api: AdminApiService,
    private auth: AuthService,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.loadReports();
  }

  loadReports(): void {
    this.loading = true;
    this.error = '';
    this.api.getReports(this.statusFilter || undefined).pipe(
      catchError(() => {
        this.error = 'Could not load reports. The report service is unreachable.';
        return of(null);
      }),
    ).subscribe(reports => {
      this.dataSource.data = reports ?? [];
      this.loading = false;
    });
  }

  createReport(): void {
    this.creating = true;
    const request: CreateReportRequest = {
      reportName: this.newReport.reportName,
      category: this.newReport.category,
      reportType: this.newReport.reportType,
      requestedBy: this.auth.currentUser?.id || 'admin',
    };
    this.api.createReport(request).subscribe({
      next: () => {
        this.creating = false;
        this.showCreateForm = false;
        this.newReport = { reportName: '', category: 'USAGE_ANALYTICS', reportType: 'CSV' };
        this.snackBar.open('Report requested', 'Dismiss', { duration: 3000 });
        this.loadReports();
      },
      error: () => {
        this.creating = false;
        this.snackBar.open('Could not create the report', 'Dismiss', { duration: 5000 });
      },
    });
  }

  downloadReport(report: Report): void {
    this.downloadingId = report.id;
    this.api.downloadReport(report.id).subscribe({
      next: response => {
        this.downloadingId = null;
        const blob = response.body;
        if (!blob) {
          this.snackBar.open('Report file was empty', 'Dismiss', { duration: 5000 });
          return;
        }
        this.saveBlob(blob, this.fileName(report, response.headers.get('content-disposition')));
      },
      error: () => {
        this.downloadingId = null;
        this.snackBar.open(`Could not download "${report.reportName}"`, 'Dismiss', { duration: 5000 });
      },
    });
  }

  label(value: string): string {
    return value
      .split('_')
      .map(part => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
      .join(' ');
  }

  private fileName(report: Report, contentDisposition: string | null): string {
    const match = contentDisposition?.match(/filename="?([^"]+)"?/);
    if (match) {
      return match[1];
    }
    return `report-${report.id}.${String(report.reportType).toLowerCase()}`;
  }

  private saveBlob(blob: Blob, fileName: string): void {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = fileName;
    link.click();
    URL.revokeObjectURL(url);
  }
}
