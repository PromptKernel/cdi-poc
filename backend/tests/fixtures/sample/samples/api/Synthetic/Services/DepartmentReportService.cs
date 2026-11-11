// SYNTHETIC: added for the cross-layer dependency graph PoC; not part of the MIT base sample.
using System.Collections.Generic;
using System.Linq;
using ASPCoreWithAngular.Synthetic.DataAccess;

namespace ASPCoreWithAngular.Synthetic.Services
{
    // "Business service" layer (rules and calculation between the API and SQL): rules/calculation between API and SQL.
    public class DepartmentReportService : IDepartmentReportService
    {
        private readonly DepartmentDataAccess dal;

        public DepartmentReportService(DepartmentDataAccess _dal)
        {
            dal = _dal;
        }

        public IEnumerable<DepartmentHeadcount> GetHeadcountReport()
        {
            var rows = dal.ReadHeadcount().ToList();
            foreach (var r in rows)
            {
                r.OverLimit = IsOverLimit(r);
            }
            return rows;
        }

        public bool IsOverLimit(DepartmentHeadcount row)
        {
            return row.Headcount > row.HeadcountLimit;
        }

        public IEnumerable<string> GetEmployeeNames(string department)
        {
            return dal.ReadEmployeesByDepartment(department);
        }

        public int ArchiveEmployee(int id)
        {
            return dal.Archive(id);
        }
    }
}
