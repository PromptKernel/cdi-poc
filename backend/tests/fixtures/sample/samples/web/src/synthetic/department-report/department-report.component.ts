// SYNTHETIC: added for the cross-layer dependency graph PoC; not part of the MIT base sample.
import { Component } from '@angular/core';
import { DepartmentReportService } from '../department-report.service';

@Component({
  selector: 'app-department-report',
  template: '<h2>Department headcount (synthetic)</h2>'
})
export class DepartmentReportComponent {
  public rows: any[];
  public names: string[];

  constructor(private _report: DepartmentReportService) {
    this.loadHeadcount();
  }

  loadHeadcount() {
    this._report.getHeadcount().subscribe((data: any[]) => this.rows = data);
  }

  showEmployees(department: string) {
    this._report.getEmployeesIn(department).subscribe((data: string[]) => this.names = data);
  }

  archive(id: number) {
    this._report.archive(id).subscribe(() => this.loadHeadcount());
  }
}
