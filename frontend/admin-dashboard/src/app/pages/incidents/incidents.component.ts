import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatChipsModule } from '@angular/material/chips';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatBadgeModule } from '@angular/material/badge';
import { MatTooltipModule } from '@angular/material/tooltip';
import { AdminApiService } from '../../core/services/admin-api.service';
import { Incident, AFFECTED_SERVICES } from '../../core/models/incident.model';
import { Subscription, interval } from 'rxjs';

@Component({
  selector: 'app-incidents',
  standalone: true,
  imports: [
    CommonModule, FormsModule, MatCardModule, MatIconModule, MatButtonModule,
    MatProgressSpinnerModule, MatChipsModule, MatInputModule, MatFormFieldModule,
    MatSelectModule, MatSnackBarModule, MatBadgeModule, MatTooltipModule,
  ],
  template: `
    <div class="page-container">
      <div class="page-header">
        <div>
          <h1 class="page-title">Incident Response</h1>
          <p class="page-subtitle">Create incident tickets to trigger automated Devin investigation sessions</p>
        </div>
        <button mat-raised-button color="warn" (click)="showCreateForm = !showCreateForm">
          <mat-icon>{{ showCreateForm ? 'close' : 'add_alert' }}</mat-icon>
          {{ showCreateForm ? 'Cancel' : 'Report Incident' }}
        </button>
      </div>

      <!-- Status summary chips -->
      <div class="status-summary" *ngIf="!loading">
        <div class="summary-chip active" (click)="filterStatus = filterStatus === 'active' ? '' : 'active'">
          <mat-icon>warning</mat-icon>
          <span>{{ activeCount }} Active</span>
        </div>
        <div class="summary-chip investigating" (click)="filterStatus = filterStatus === 'investigating' ? '' : 'investigating'">
          <mat-icon>smart_toy</mat-icon>
          <span>{{ investigatingCount }} Devin Investigating</span>
        </div>
        <div class="summary-chip resolved" (click)="filterStatus = filterStatus === 'resolved' ? '' : 'resolved'">
          <mat-icon>check_circle</mat-icon>
          <span>{{ resolvedCount }} Resolved</span>
        </div>
      </div>

      <!-- Create form -->
      <mat-card *ngIf="showCreateForm" class="create-form">
        <mat-card-header>
          <mat-card-title>
            <mat-icon>add_alert</mat-icon>
            Report New Incident
          </mat-card-title>
          <mat-card-subtitle>A Devin session will automatically be created to investigate this incident</mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          <mat-form-field appearance="outline" class="full-width">
            <mat-label>Incident Title</mat-label>
            <input matInput [(ngModel)]="newIncident.title" placeholder="Brief description of the issue">
          </mat-form-field>

          <mat-form-field appearance="outline" class="full-width">
            <mat-label>Description</mat-label>
            <textarea matInput [(ngModel)]="newIncident.description" rows="4"
              placeholder="Detailed description: what's happening, error messages, affected users..."></textarea>
          </mat-form-field>

          <div class="form-row">
            <mat-form-field appearance="outline">
              <mat-label>Severity</mat-label>
              <mat-select [(ngModel)]="newIncident.severity">
                <mat-option value="low">Low</mat-option>
                <mat-option value="medium">Medium</mat-option>
                <mat-option value="high">High</mat-option>
                <mat-option value="critical">Critical</mat-option>
              </mat-select>
            </mat-form-field>

            <mat-form-field appearance="outline">
              <mat-label>Affected Service</mat-label>
              <mat-select [(ngModel)]="newIncident.affectedService">
                <mat-option *ngFor="let svc of affectedServices" [value]="svc.value">
                  {{ svc.label }}
                </mat-option>
              </mat-select>
            </mat-form-field>
          </div>

          <button mat-raised-button color="warn" (click)="createIncident()"
            [disabled]="!newIncident.title || !newIncident.description || creating">
            <mat-icon>{{ creating ? 'hourglass_empty' : 'smart_toy' }}</mat-icon>
            {{ creating ? 'Creating Devin Session...' : 'Create Incident & Launch Devin' }}
          </button>
        </mat-card-content>
      </mat-card>

      <!-- Loading -->
      <div *ngIf="loading" class="loading-container">
        <mat-spinner diameter="40"></mat-spinner>
      </div>

      <!-- Incidents list -->
      <div class="incidents-list" *ngIf="!loading">
        <mat-card *ngFor="let incident of filteredIncidents" class="incident-card"
          [class]="'severity-border-' + incident.severity">
          <mat-card-content>
            <div class="incident-header">
              <div class="incident-info">
                <div class="incident-title-row">
                  <h3>{{ incident.title }}</h3>
                </div>
                <div class="incident-badges">
                  <span class="severity-chip" [class]="'severity-' + incident.severity">
                    {{ incident.severity }}
                  </span>
                  <span class="status-chip" [class]="'status-' + incident.status">
                    <mat-icon class="chip-icon">{{ getStatusIcon(incident.status) }}</mat-icon>
                    {{ incident.status }}
                  </span>
                  <span class="service-chip" *ngIf="incident.affectedService">
                    <mat-icon class="chip-icon">dns</mat-icon>
                    {{ incident.affectedService }}
                  </span>
                </div>
              </div>
            </div>

            <p class="incident-description">{{ incident.description }}</p>

            <!-- Devin Session Status -->
            <div class="devin-session" *ngIf="incident.devinSessionId">
              <div class="devin-header">
                <mat-icon class="devin-icon">smart_toy</mat-icon>
                <span class="devin-label">Devin Session</span>
                <span class="devin-status" [class]="'devin-' + (incident.devinSessionStatus || 'unknown')">
                  {{ incident.devinSessionStatus || 'pending' }}
                </span>
              </div>
              <div class="devin-details">
                <span class="session-id">{{ incident.devinSessionId }}</span>
                <a *ngIf="incident.devinSessionUrl" [href]="incident.devinSessionUrl"
                  target="_blank" rel="noopener" class="session-link">
                  <mat-icon>open_in_new</mat-icon>
                  View Session
                </a>
              </div>
            </div>

            <div class="devin-session devin-pending" *ngIf="!incident.devinSessionId && incident.active">
              <mat-icon class="devin-icon">smart_toy</mat-icon>
              <span>No Devin session - click to trigger investigation</span>
            </div>

            <div class="incident-meta">
              <span>Created {{ incident.createdAt | date:'medium' }}</span>
              <span *ngIf="incident.resolvedAt">Resolved {{ incident.resolvedAt | date:'medium' }}</span>
            </div>
          </mat-card-content>
        </mat-card>
      </div>

      <!-- Empty state -->
      <div *ngIf="!loading && filteredIncidents.length === 0" class="empty-state">
        <mat-icon>check_circle_outline</mat-icon>
        <p *ngIf="filterStatus">No {{ filterStatus }} incidents</p>
        <p *ngIf="!filterStatus">No incidents reported</p>
        <button mat-stroked-button color="warn" (click)="showCreateForm = true" *ngIf="!showCreateForm">
          Report First Incident
        </button>
      </div>
    </div>
  `,
  styles: [`
    .page-container{padding:0}.page-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:24px}
    .page-title{font-size:1.5rem;font-weight:600;color:#333;margin:0}.page-subtitle{font-size:.85rem;color:#777;margin:4px 0 0}
    .loading-container{display:flex;justify-content:center;padding:60px}
    .status-summary{display:flex;gap:12px;margin-bottom:24px;flex-wrap:wrap}
    .summary-chip{display:flex;align-items:center;gap:6px;padding:8px 16px;border-radius:8px;font-size:.85rem;font-weight:500;cursor:pointer}
    .summary-chip .mat-icon{font-size:18px;width:18px;height:18px}
    .summary-chip.active{background:#fff3e0;color:#e65100}.summary-chip.investigating{background:#e3f2fd;color:#1565c0}.summary-chip.resolved{background:#e8f5e9;color:#2e7d32}
    .create-form{margin-bottom:24px;border-left:4px solid #f44336}.create-form mat-card-title{display:flex;align-items:center;gap:8px}
    .full-width{width:100%}.form-row{display:flex;gap:16px}
    .incidents-list{display:flex;flex-direction:column;gap:16px}
    .incident-card{border-left:4px solid transparent}.severity-border-low{border-left-color:#4caf50}.severity-border-medium{border-left-color:#2196f3}.severity-border-high{border-left-color:#ff9800}.severity-border-critical{border-left-color:#f44336}
    .incident-header{display:flex;justify-content:space-between;align-items:flex-start}.incident-info{flex:1}
    .incident-title-row h3{margin:0 0 8px;font-size:1.05rem}.incident-badges{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
    .severity-chip,.status-chip,.service-chip{display:flex;align-items:center;gap:3px;padding:3px 8px;border-radius:4px;font-size:.7rem;font-weight:600;text-transform:uppercase}
    .chip-icon{font-size:13px;width:13px;height:13px}
    .severity-low{background:#e8f5e9;color:#2e7d32}.severity-medium{background:#e3f2fd;color:#1565c0}.severity-high{background:#fff3e0;color:#e65100}.severity-critical{background:#ffebee;color:#c62828}
    .status-open{background:#fff3e0;color:#e65100}.status-investigating{background:#e3f2fd;color:#1565c0}.status-resolved{background:#e8f5e9;color:#2e7d32}.status-closed{background:#eceff1;color:#546e7a}
    .service-chip{background:#f3e5f5;color:#7b1fa2}
    .incident-description{color:#555;line-height:1.6;margin:16px 0;font-size:.9rem}
    .devin-session{background:#f8f9ff;border:1px solid #e0e7ff;border-radius:8px;padding:12px 16px;margin:12px 0}
    .devin-header{display:flex;align-items:center;gap:8px;margin-bottom:6px}
    .devin-icon{color:#1565c0;font-size:20px;width:20px;height:20px}.devin-label{font-weight:600;font-size:.85rem;color:#333}
    .devin-status{padding:2px 8px;border-radius:12px;font-size:.7rem;font-weight:600;text-transform:uppercase}
    .devin-running{background:#e3f2fd;color:#1565c0}.devin-stopped{background:#e8f5e9;color:#2e7d32}.devin-failed{background:#ffebee;color:#c62828}.devin-unknown{background:#eceff1;color:#546e7a}.devin-blocked{background:#fff3e0;color:#e65100}
    .devin-details{display:flex;align-items:center;gap:16px;font-size:.8rem}
    .session-id{color:#999;font-family:monospace;font-size:.75rem}
    .session-link{display:flex;align-items:center;gap:4px;color:#1565c0;text-decoration:none;font-weight:500}
    .session-link:hover{text-decoration:underline}.session-link .mat-icon{font-size:16px;width:16px;height:16px}
    .devin-pending{display:flex;align-items:center;gap:8px;color:#999;font-size:.85rem;background:#fafafa;border-color:#eee}
    .incident-meta{display:flex;gap:16px;font-size:.8rem;color:#999;flex-wrap:wrap;margin-top:8px}
    .empty-state{display:flex;flex-direction:column;align-items:center;padding:60px;color:#999}
    .empty-state .mat-icon{font-size:48px;width:48px;height:48px;margin-bottom:12px}
  `],
})
export class IncidentsComponent implements OnInit, OnDestroy {
  incidents: Incident[] = [];
  loading = true;
  creating = false;
  showCreateForm = false;
  filterStatus = '';
  affectedServices = AFFECTED_SERVICES;
  newIncident: Partial<Incident> = { severity: 'high', affectedService: '' };

  private pollSub?: Subscription;

  constructor(
    private api: AdminApiService,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.loadIncidents();
    // Poll for status updates every 10 seconds
    this.pollSub = interval(10000).subscribe(() => {
      if (this.incidents.some(i => i.active && i.devinSessionId)) {
        this.loadIncidents();
      }
    });
  }

  ngOnDestroy(): void {
    this.pollSub?.unsubscribe();
  }

  get activeCount(): number {
    return this.incidents.filter(i => i.active).length;
  }

  get investigatingCount(): number {
    return this.incidents.filter(i => i.status === 'investigating' && i.devinSessionId).length;
  }

  get resolvedCount(): number {
    return this.incidents.filter(i => i.status === 'resolved').length;
  }

  get filteredIncidents(): Incident[] {
    if (!this.filterStatus) return this.incidents;
    if (this.filterStatus === 'active') return this.incidents.filter(i => i.active);
    if (this.filterStatus === 'investigating') return this.incidents.filter(i => i.status === 'investigating');
    return this.incidents.filter(i => i.status === this.filterStatus);
  }

  loadIncidents(): void {
    this.api.getIncidents().subscribe({
      next: (incidents) => {
        this.incidents = incidents;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.snackBar.open('Failed to load incidents', 'Dismiss', { duration: 3000 });
      },
    });
  }

  createIncident(): void {
    if (!this.newIncident.title || !this.newIncident.description) return;

    this.creating = true;
    this.api.createIncident(this.newIncident).subscribe({
      next: (incident) => {
        this.incidents.unshift(incident);
        this.showCreateForm = false;
        this.creating = false;
        this.newIncident = { severity: 'high', affectedService: '' };

        const sessionMsg = incident.devinSessionId
          ? ` Devin session launched.`
          : ' (Devin session pending)';
        this.snackBar.open('Incident created!' + sessionMsg, 'Dismiss', { duration: 5000 });
      },
      error: () => {
        this.creating = false;
        this.snackBar.open('Failed to create incident', 'Dismiss', { duration: 3000 });
      },
    });
  }

  getStatusIcon(status: string): string {
    switch (status) {
      case 'open': return 'error_outline';
      case 'investigating': return 'smart_toy';
      case 'resolved': return 'check_circle';
      case 'closed': return 'cancel';
      default: return 'help_outline';
    }
  }
}
