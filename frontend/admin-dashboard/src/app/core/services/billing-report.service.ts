import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import {
  DunningAttempt, FinanceBatchReport, MonthEndReport, OverdueAccount, ReconciliationReport,
} from '../models/billing-report.model';

// The billing report backend is whichever estate currently serves the report
// contract (see docs/tech-partnerships/billing-report-contract.md). The dev
// proxy maps /billing-api to it; swapping the backend never touches this app.
@Injectable({ providedIn: 'root' })
export class BillingReportService {
  private readonly baseUrl = '/billing-api/api/reports';

  constructor(private http: HttpClient) {}

  getMonthEndReport(ns: string): Observable<MonthEndReport> {
    return this.http.get<MonthEndReport>(`${this.baseUrl}/month-end`, { params: { ns } });
  }

  getReconciliation(ns: string): Observable<ReconciliationReport> {
    return this.http.get<ReconciliationReport>(`${this.baseUrl}/reconciliation`, { params: { ns } });
  }

  getFinanceReport(ns: string): Observable<FinanceBatchReport> {
    return this.http.get<FinanceBatchReport>(`${this.baseUrl}/finance`, { params: { ns } });
  }

  getOverdueAccounts(asOf: string): Observable<OverdueAccount[]> {
    return this.http.get<OverdueAccount[]>('/api/v1/billing/admin/overdue', { params: { as_of: asOf } });
  }

  getDunningAttempts(asOf: string): Observable<DunningAttempt[]> {
    return this.http.get<DunningAttempt[]>('/api/v1/billing/admin/dunning', { params: { as_of: asOf } });
  }
}
