-- SYNTHETIC: not part of the MIT base sample. Reconstructed/added for the cross-layer dependency graph PoC.
-- (reconstructed)
CREATE PROCEDURE dbo.spAddEmployee
    @Name VARCHAR(20), @City VARCHAR(20), @Department VARCHAR(20), @Gender VARCHAR(6)
AS
BEGIN
    INSERT INTO dbo.tblEmployee (Name, City, Department, Gender)
    VALUES (@Name, @City, @Department, @Gender);
END
