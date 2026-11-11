// SYNTHETIC: added for the cross-layer dependency graph PoC; not part of the MIT base sample.
using System.Collections.Generic;

namespace ASPCoreWithAngular.Synthetic.Services
{
    public class DepartmentHeadcount
    {
        public string DepartmentName { get; set; }
        public int Headcount { get; set; }
        public int HeadcountLimit { get; set; }
        public bool OverLimit { get; set; }
    }

    public interface IDepartmentReportService
    {
        IEnumerable<DepartmentHeadcount> GetHeadcountReport();
        IEnumerable<string> GetEmployeeNames(string department);
        int ArchiveEmployee(int id);
    }
}
