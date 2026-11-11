-- SYNTHETIC: not part of the MIT base sample. Reconstructed/added for the cross-layer dependency graph PoC.
-- (reconstructed from columns read/written by the sample's C# data-access layer)
CREATE TABLE dbo.tblEmployee (
    EmployeeID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    Name       VARCHAR(20) NOT NULL,
    City       VARCHAR(20) NOT NULL,
    Department VARCHAR(20) NOT NULL,
    Gender     VARCHAR(6)  NOT NULL
);
