-- SYNTHETIC: not part of the MIT base sample. Reconstructed/added for the cross-layer dependency graph PoC.
-- (reconstructed)
CREATE PROCEDURE dbo.spUpdateEmployee
    @EmpId INT, @Name VARCHAR(20), @City VARCHAR(20), @Department VARCHAR(20), @Gender VARCHAR(6)
AS
BEGIN
    UPDATE dbo.tblEmployee
    SET Name = @Name, City = @City, Department = @Department, Gender = @Gender
    WHERE EmployeeID = @EmpId;
END
