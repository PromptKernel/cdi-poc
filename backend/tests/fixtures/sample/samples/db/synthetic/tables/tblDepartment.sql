-- SYNTHETIC: not part of the MIT base sample. Reconstructed/added for the cross-layer dependency graph PoC.
-- SYNTHETIC ADDITION: second table.
CREATE TABLE dbo.tblDepartment (
    DepartmentID    INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    DepartmentName  VARCHAR(20) NOT NULL,
    HeadcountLimit  INT NOT NULL
);
