-- SYNTHETIC: not part of the MIT base sample. Reconstructed/added for the cross-layer dependency graph PoC.
-- SYNTHETIC ADDITION: the ONE dynamic-SQL string. Target table is built at runtime => cannot be statically resolved.
CREATE PROCEDURE dbo.spSearchEmployees
    @Column SYSNAME, @Term VARCHAR(50)
AS
BEGIN
    DECLARE @sql NVARCHAR(400);
    SET @sql = N'SELECT EmployeeID, Name FROM dbo.tblEmployee WHERE ' + QUOTENAME(@Column) + N' LIKE @t';
    EXEC sp_executesql @sql, N'@t VARCHAR(50)', @t = @Term;
END
