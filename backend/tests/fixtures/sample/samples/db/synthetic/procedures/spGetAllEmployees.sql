-- SYNTHETIC: not part of the MIT base sample. Reconstructed/added for the cross-layer dependency graph PoC.
-- (reconstructed)
CREATE PROCEDURE dbo.spGetAllEmployees
AS
BEGIN
    SELECT EmployeeID, Name, Gender, Department, City
    FROM dbo.tblEmployee
    ORDER BY EmployeeID;
END
