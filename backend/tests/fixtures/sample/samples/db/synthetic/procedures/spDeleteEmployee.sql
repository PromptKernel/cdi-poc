-- SYNTHETIC: not part of the MIT base sample. Reconstructed/added for the cross-layer dependency graph PoC.
-- (reconstructed)
CREATE PROCEDURE dbo.spDeleteEmployee
    @EmpId INT
AS
BEGIN
    DELETE FROM dbo.tblEmployee WHERE EmployeeID = @EmpId;
END
