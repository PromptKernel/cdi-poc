-- SYNTHETIC: not part of the MIT base sample. Reconstructed/added for the cross-layer dependency graph PoC.
-- (reconstructed)
CREATE PROCEDURE dbo.spGetCityList
AS
BEGIN
    SELECT CityID, CityName FROM dbo.tblCities;
END
