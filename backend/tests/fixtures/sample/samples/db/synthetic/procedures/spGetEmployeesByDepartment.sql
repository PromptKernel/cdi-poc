-- SYNTHETIC: not part of the MIT base sample. Reconstructed/added for the cross-layer dependency graph PoC.
-- SYNTHETIC ADDITION: reads the view (procedure -> view -> tables).
CREATE PROCEDURE dbo.spGetEmployeesByDepartment
    @Department VARCHAR(20)
AS
BEGIN
    SELECT EmployeeID, Name, Department FROM dbo.vwEmployeeDepartment
    WHERE Department = @Department;
END
