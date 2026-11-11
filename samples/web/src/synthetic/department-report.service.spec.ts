// SYNTHETIC tests (PoC). Mapping demonstrated per test:
//  - "should be created": no annotation -> mapped only by file-name convention (department-report.service.ts)
//  - "archive ...": annotation directly above the test -> covers only that test's target
//  - second describe: annotation above the describe block -> inherited by tests inside it only
import { TestBed } from '@angular/core/testing';
import { DepartmentReportService } from './department-report.service';
import { DepartmentReportComponent } from './department-report/department-report.component';

describe('DepartmentReportService', () => {
  it('should be created', () => {
    const service: DepartmentReportService = TestBed.get(DepartmentReportService);
    expect(service).toBeTruthy();
  });

  // @covers DepartmentReportService.archive
  it('archive posts to the Department API', () => {
    const service: DepartmentReportService = TestBed.get(DepartmentReportService);
    expect(service.archive).toBeDefined();
  });
});

// @covers DepartmentReportComponent
describe('DepartmentReportComponent', () => {
  it('is declared', () => {
    expect(DepartmentReportComponent).toBeDefined();
  });
});
