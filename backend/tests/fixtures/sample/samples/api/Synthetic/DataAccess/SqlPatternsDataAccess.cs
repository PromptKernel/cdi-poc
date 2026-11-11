// SYNTHETIC: added for the cross-layer dependency graph PoC; not part of the MIT base sample.
// One method per way of building a SqlCommand, so the scanner's handling of each is tested (tests/expected_edges.yml).
using System.Data;
using System.Data.SqlClient;

namespace ASPCoreWithAngular.Synthetic.DataAccess
{
    public class SqlPatternsDataAccess
    {
        private const string CityProc = "spGetCityList";
        private readonly string connectionString = "";

        // constant field used as the command text
        public void ConstantField()
        {
            using (SqlConnection con = new SqlConnection(connectionString))
            {
                SqlCommand cmd = new SqlCommand(CityProc, con);
                cmd.CommandType = CommandType.StoredProcedure;
                con.Open();
                cmd.ExecuteNonQuery();
            }
        }

        // constant concatenation is folded by the compiler
        public void ConstantConcatenation()
        {
            using (SqlConnection con = new SqlConnection(connectionString))
            {
                SqlCommand cmd = new SqlCommand("sp" + "GetAllEmployees", con);
                cmd.CommandType = CommandType.StoredProcedure;
                con.Open();
                cmd.ExecuteNonQuery();
            }
        }

        // CommandText and CommandType both set in an object initializer
        public void ObjectInitializer()
        {
            using (SqlConnection con = new SqlConnection(connectionString))
            {
                var cmd = new SqlCommand
                {
                    CommandText = "spGetDepartmentHeadcount",
                    CommandType = CommandType.StoredProcedure,
                    Connection = con
                };
                con.Open();
                cmd.ExecuteNonQuery();
            }
        }

        // CommandText assigned after construction
        public void CommandTextAssignment()
        {
            using (SqlConnection con = new SqlConnection(connectionString))
            {
                var cmd = new SqlCommand();
                cmd.Connection = con;
                cmd.CommandText = "spGetEmployeesByDepartment";
                cmd.CommandType = CommandType.StoredProcedure;
                con.Open();
                cmd.ExecuteNonQuery();
            }
        }

        // target-typed new()
        public void TargetTypedNew()
        {
            using (SqlConnection con = new SqlConnection(connectionString))
            {
                SqlCommand cmd = new("spDeleteEmployee", con);
                cmd.CommandType = CommandType.StoredProcedure;
                con.Open();
                cmd.ExecuteNonQuery();
            }
        }

        // constructor argument plus a CommandType-only object initializer
        public void CtorWithInitializer()
        {
            using (SqlConnection con = new SqlConnection(connectionString))
            {
                var cmd = new SqlCommand("spAddEmployee", con) { CommandType = CommandType.StoredProcedure };
                con.Open();
                cmd.ExecuteNonQuery();
            }
        }

        // interpolated string with a runtime value: NOT statically resolvable
        public void InterpolatedSql(string department)
        {
            using (SqlConnection con = new SqlConnection(connectionString))
            {
                var sql = $"SELECT Name FROM dbo.tblEmployee WHERE Department = '{department}'";
                SqlCommand cmd = new SqlCommand(sql, con);
                con.Open();
                cmd.ExecuteNonQuery();
            }
        }

        // inline literal SQL text (not a stored-procedure call): reported UNRESOLVED, not parsed
        public void InlineLiteralSql()
        {
            using (SqlConnection con = new SqlConnection(connectionString))
            {
                SqlCommand cmd = new SqlCommand("SELECT COUNT(*) FROM dbo.tblEmployee", con);
                con.Open();
                cmd.ExecuteScalar();
            }
        }
    }
}
