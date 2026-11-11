// SYNTHETIC: added for the cross-layer dependency graph PoC; not part of the MIT base sample.
import { Injectable, Inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { RuntimeConfigService } from './runtime-config.service';

@Injectable({ providedIn: 'root' })
export class DepartmentReportService {
  private baseUrl: string;

  constructor(private _http: HttpClient, private _config: RuntimeConfigService, @Inject('BASE_URL') baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  // CONFIG-BUILT ROUTE: path prefix comes from runtime config, so the target API route cannot be resolved statically.
  getHeadcount() {
    const url = this.baseUrl + this._config.get('reportsRoute') + 'Headcount';
    return this._http.get(url);
  }

  getEmployeesIn(department: string) {
    return this._http.get(this.baseUrl + 'api/Department/Employees/' + department);
  }

  // WHOLE URL IS A RUNTIME VALUE: nothing static to match against API routes.
  exportReport(url: string) {
    return this._http.get(url);
  }

  archive(id: number) {
    return this._http.post(this.baseUrl + 'api/Department/Archive/' + id, {});
  }
}
