// SYNTHETIC: added for the cross-layer dependency graph PoC; not part of the MIT base sample.
using System.Collections.Generic;
using ASPCoreWithAngular.Synthetic.Services;
using Microsoft.AspNetCore.Mvc;

namespace ASPCoreWithAngular.Synthetic.Controllers
{
    [Route("api/[controller]")]
    public class DepartmentController : Controller
    {
        private readonly IDepartmentReportService report;

        public DepartmentController(IDepartmentReportService _report)
        {
            report = _report;
        }

        [HttpGet]
        [Route("Headcount")]
        public IEnumerable<DepartmentHeadcount> Headcount()
        {
            return report.GetHeadcountReport();
        }

        [HttpGet]
        [Route("Employees/{department}")]
        public IEnumerable<string> EmployeesIn(string department)
        {
            return report.GetEmployeeNames(department);
        }

        [HttpPost]
        [Route("Archive/{id}")]
        public int Archive(int id)
        {
            return report.ArchiveEmployee(id);
        }
    }
}
