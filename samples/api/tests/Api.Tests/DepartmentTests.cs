// SYNTHETIC tests (PoC). Two mapping methods are demonstrated on purpose:
//  1) naming convention  <Controller>_<Action>_<Behaviour>   -> DepartmentController.Headcount
//  2) explicit annotation  // @covers <qualified node name>
using System.Linq;
using ASPCoreWithAngular.Synthetic.Controllers;
using ASPCoreWithAngular.Synthetic.Services;
using Xunit;

namespace Api.Tests
{
    public class DepartmentTests
    {
        private class FakeReport : IDepartmentReportService
        {
            public System.Collections.Generic.IEnumerable<DepartmentHeadcount> GetHeadcountReport() =>
                new[] { new DepartmentHeadcount { DepartmentName = "IT", Headcount = 3, HeadcountLimit = 2, OverLimit = true } };
            public System.Collections.Generic.IEnumerable<string> GetEmployeeNames(string department) => new[] { "A" };
            public int ArchiveEmployee(int id) => 1;
        }

        [Fact]
        public void DepartmentController_Headcount_ReturnsRows()
        {
            var c = new DepartmentController(new FakeReport());
            Assert.Single(c.Headcount());
        }

        // @covers ASPCoreWithAngular.Synthetic.Services.DepartmentReportService.IsOverLimit(ASPCoreWithAngular.Synthetic.Services.DepartmentHeadcount)
        [Fact]
        public void OverLimit_flag_true_when_headcount_exceeds_limit()
        {
            var svc = new DepartmentReportService(null);
            Assert.True(svc.IsOverLimit(new DepartmentHeadcount { Headcount = 3, HeadcountLimit = 2 }));
        }
    }
}
