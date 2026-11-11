-- SYNTHETIC: not part of the MIT base sample. Reconstructed/added for the cross-layer dependency graph PoC.
-- SYNTHETIC ADDITION: view over both tables.
CREATE VIEW dbo.vwEmployeeDepartment AS
SELECT e.EmployeeID, e.Name, e.Department, d.HeadcountLimit
FROM dbo.tblEmployee e
INNER JOIN dbo.tblDepartment d ON d.DepartmentName = e.Department;
