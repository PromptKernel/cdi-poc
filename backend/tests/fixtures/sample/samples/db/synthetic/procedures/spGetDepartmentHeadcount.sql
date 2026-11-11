-- SYNTHETIC: not part of the MIT base sample. Reconstructed/added for the cross-layer dependency graph PoC.
-- SYNTHETIC ADDITION: procedure reading both tables directly.
CREATE PROCEDURE dbo.spGetDepartmentHeadcount
AS
BEGIN
    SELECT d.DepartmentName, COUNT(e.EmployeeID) AS Headcount, d.HeadcountLimit
    FROM dbo.tblDepartment d
    LEFT JOIN dbo.tblEmployee e ON e.Department = d.DepartmentName
    GROUP BY d.DepartmentName, d.HeadcountLimit;
END
