import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { catchError, forkJoin, of } from 'rxjs';
import { BillingReportService } from '../../core/services/billing-report.service';
import {
  BillingLineRow, MonthEndReport, ReconciliationReport,
} from '../../core/models/billing-report.model';

@Component({
  selector: 'app-billing-report',
  standalone: true,
  imports: [
    CommonModule, FormsModule, MatCardModule, MatIconModule, MatButtonModule,
    MatProgressSpinnerModule, MatFormFieldModule, MatInputModule,
  ],
  template: `
    <div class="page-container">
      <div class="page-header">
        <div class="title-row">
          <h1 class="page-title">Billing Report</h1>
          <span class="source-badge" *ngIf="report" [class]="'engine-' + report.source.engine">
            <mat-icon>{{ report.source.engine === 'mongodb' ? 'eco' : 'dns' }}</mat-icon>
            {{ sourceLabel }}
          </span>
        </div>
        <div class="header-actions">
          <mat-form-field appearance="outline" class="ns-field" subscriptSizing="dynamic">
            <mat-label>Namespace</mat-label>
            <input matInput [(ngModel)]="ns" (keyup.enter)="refresh()" />
          </mat-form-field>
          <button mat-raised-button color="primary" (click)="refresh()">
            <mat-icon>refresh</mat-icon> Refresh
          </button>
        </div>
      </div>

      <div class="recon-banner" *ngIf="recon" [class]="'recon-' + recon.status">
        <mat-icon>{{ reconIcon }}</mat-icon>
        <div class="recon-text">
          <span class="recon-title">{{ reconTitle }}</span>
          <span class="recon-detail">{{ reconDetail }}</span>
        </div>
      </div>

      <div *ngIf="loading" class="loading-container">
        <mat-spinner diameter="40"></mat-spinner>
      </div>

      <div *ngIf="error && !loading" class="error-container">
        <mat-icon>error_outline</mat-icon>
        <p>{{ error }}</p>
        <button mat-raised-button color="primary" (click)="refresh()">Retry</button>
      </div>

      <ng-container *ngIf="!loading && report">
        <div class="summary-tiles">
          <div class="tile">
            <span class="tile-value">{{ totalInvoices | number }}</span>
            <span class="tile-label">Invoices</span>
          </div>
          <div class="tile">
            <span class="tile-value">{{ totalBilled | currency }}</span>
            <span class="tile-label">Billed (header totals)</span>
          </div>
          <div class="tile" *ngIf="recon">
            <span class="tile-value">{{ recon.balances.customer_count | number }}</span>
            <span class="tile-label">Customers</span>
          </div>
          <div class="tile balances-tile" *ngIf="recon" [class.drifted]="recon.status === 'fail'">
            <span class="tile-value">{{ recon.balances.current_balance_total | currency }}</span>
            <span class="tile-label">Current balances</span>
          </div>
        </div>

        <mat-card class="report-card">
          <mat-card-header><mat-card-title>Invoices by status</mat-card-title></mat-card-header>
          <mat-card-content>
            <table class="report-table">
              <thead><tr><th>Status</th><th class="num">Invoices</th><th class="num">Header total</th></tr></thead>
              <tbody>
                <tr *ngFor="let row of report.by_status">
                  <td>{{ row.status }}</td>
                  <td class="num">{{ row.invoice_count | number }}</td>
                  <td class="num">{{ toNumber(row.header_total_amt) | currency }}</td>
                </tr>
              </tbody>
            </table>
          </mat-card-content>
        </mat-card>

        <mat-card class="report-card">
          <mat-card-header><mat-card-title>Lines by status and type</mat-card-title></mat-card-header>
          <mat-card-content>
            <table class="report-table">
              <thead>
                <tr>
                  <th>Status</th><th>Line type</th><th class="num">Lines</th>
                  <th class="num">Amount</th><th class="num">Tax</th><th class="num">Invoices touched</th>
                </tr>
              </thead>
              <tbody>
                <tr *ngFor="let row of report.by_status_line_type">
                  <td>{{ row.status }}</td>
                  <td>{{ row.line_type }}</td>
                  <td class="num">{{ row.line_count | number }}</td>
                  <td class="num">{{ toNumber(row.line_amount) | currency }}</td>
                  <td class="num">{{ toNumber(row.line_tax) | currency }}</td>
                  <td class="num">{{ row.invoices_touched | number }}</td>
                </tr>
              </tbody>
            </table>
          </mat-card-content>
        </mat-card>

        <p class="report-footer" *ngIf="report">
          {{ report.source.system }} — {{ report.source.detail }} ·
          batch {{ report.batch_no }} · generated {{ report.generated_at }}
        </p>
      </ng-container>
    </div>
  `,
  styles: [`
    .page-container { padding: 0; }
    .page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; flex-wrap: wrap; gap: 12px; }
    .title-row { display: flex; align-items: center; gap: 16px; }
    .page-title { font-size: 1.5rem; font-weight: 600; color: #333; margin: 0; }
    .header-actions { display: flex; align-items: center; gap: 12px; }
    .ns-field { width: 160px; }

    .source-badge {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 6px 14px; border-radius: 16px; font-weight: 600; font-size: 0.85rem;
    }
    .source-badge.engine-oracle { background: #fff3e0; color: #e65100; }
    .source-badge.engine-mongodb { background: #e8f5e9; color: #2e7d32; }

    .recon-banner {
      display: flex; align-items: center; gap: 12px;
      padding: 14px 20px; border-radius: 8px; margin-bottom: 24px;
    }
    .recon-banner .mat-icon { font-size: 28px; width: 28px; height: 28px; }
    .recon-text { display: flex; flex-direction: column; }
    .recon-title { font-weight: 600; }
    .recon-detail { font-size: 0.85rem; opacity: 0.85; }
    .recon-baseline { background: #e3f2fd; color: #1565c0; }
    .recon-pass { background: #e8f5e9; color: #2e7d32; }
    .recon-fail { background: #ffebee; color: #c62828; }

    .loading-container { display: flex; justify-content: center; padding: 60px; }
    .error-container { display: flex; flex-direction: column; align-items: center; padding: 60px; color: #c62828; }
    .error-container .mat-icon { font-size: 48px; width: 48px; height: 48px; margin-bottom: 16px; }
    .error-container p { margin-bottom: 16px; }

    .summary-tiles { display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
    .tile {
      display: flex; flex-direction: column; gap: 4px; flex: 1; min-width: 160px;
      padding: 16px 24px; border-radius: 8px; background: #f5f5f5;
    }
    .tile-value { font-size: 1.4rem; font-weight: 600; color: #333; }
    .tile-label { font-size: 0.85rem; color: #666; }
    .balances-tile.drifted { background: #ffebee; }
    .balances-tile.drifted .tile-value { color: #c62828; }

    .report-card { margin-bottom: 24px; }
    .report-table { width: 100%; border-collapse: collapse; }
    .report-table th, .report-table td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; }
    .report-table th.num, .report-table td.num { text-align: right; }
    .report-footer { color: #888; font-size: 0.8rem; }
  `],
})
export class BillingReportComponent implements OnInit {
  ns = 'demo';
  loading = true;
  error = '';
  report: MonthEndReport | null = null;
  recon: ReconciliationReport | null = null;

  constructor(private billingReports: BillingReportService) {}

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.loading = true;
    this.error = '';
    forkJoin({
      report: this.billingReports.getMonthEndReport(this.ns),
      recon: this.billingReports.getReconciliation(this.ns),
    }).pipe(
      catchError(() => of(null)),
    ).subscribe(result => {
      this.loading = false;
      if (!result) {
        this.report = null;
        this.recon = null;
        this.error = 'Failed to load the billing report. The billing estate may be unavailable.';
        return;
      }
      this.report = result.report;
      this.recon = result.recon;
    });
  }

  get sourceLabel(): string {
    switch (this.report?.source.engine) {
      case 'oracle': return 'Legacy Oracle Estate';
      case 'mongodb': return 'MongoDB Atlas';
      default: return this.report?.source.engine ?? '';
    }
  }

  get totalInvoices(): number {
    return (this.report?.by_status ?? []).reduce((sum, row) => sum + row.invoice_count, 0);
  }

  get totalBilled(): number {
    return (this.report?.by_status ?? []).reduce((sum, row) => sum + this.toNumber(row.header_total_amt), 0);
  }

  get reconIcon(): string {
    switch (this.recon?.status) {
      case 'pass': return 'check_circle';
      case 'fail': return 'error';
      default: return 'verified';
    }
  }

  get reconTitle(): string {
    switch (this.recon?.status) {
      case 'pass': return 'Reconciliation passed';
      case 'fail': return 'Reconciliation FAILED';
      default: return 'Legacy source of truth';
    }
  }

  get reconDetail(): string {
    if (!this.recon) return '';
    if (this.recon.status === 'fail') {
      const failing = this.recon.checks.filter(c => c.status === 'fail').map(c => c.name);
      return `Failing checks: ${failing.join(', ')}`;
    }
    if (this.recon.status === 'pass') {
      return `${this.recon.checks.length} checks green against the legacy baseline`;
    }
    return 'This estate is the reconciliation baseline — nothing to compare against.';
  }

  toNumber(value: string): number {
    return Number(value);
  }

  trackRow(_: number, row: BillingLineRow): string {
    return `${row.status}:${row.line_type}`;
  }
}
