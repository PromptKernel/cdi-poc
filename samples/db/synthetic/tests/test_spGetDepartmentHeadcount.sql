-- SYNTHETIC: not part of the MIT base sample. Reconstructed/added for the cross-layer dependency graph PoC.
-- SYNTHETIC ADDITION: SQL test (tSQLt-style; NOT executed in this PoC - no SQL Server).
-- @covers dbo.spGetDepartmentHeadcount
CREATE PROCEDURE [DepartmentTests].[test spGetDepartmentHeadcount counts employees per department]
AS
BEGIN
    EXEC dbo.spGetDepartmentHeadcount;
END
