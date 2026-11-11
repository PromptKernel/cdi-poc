// SYNTHETIC: added for the cross-layer dependency graph PoC; not part of the MIT base sample.
using System.Collections.Generic;
using System.Data;
using System.Data.SqlClient;
using ASPCoreWithAngular.Synthetic.Services;
using Microsoft.Extensions.Configuration;

namespace ASPCoreWithAngular.Synthetic.DataAccess
{
    public class DepartmentDataAccess
    {
        private readonly string connectionString;

        public DepartmentDataAccess(IConfiguration configuration)
        {
            connectionString = configuration["ConnectionStrings:DefaultConnection"];
        }

        public IEnumerable<DepartmentHeadcount> ReadHeadcount()
        {
            var list = new List<DepartmentHeadcount>();
            using (SqlConnection con = new SqlConnection(connectionString))
            {
                SqlCommand cmd = new SqlCommand("spGetDepartmentHeadcount", con);
                cmd.CommandType = CommandType.StoredProcedure;
                con.Open();
                SqlDataReader rdr = cmd.ExecuteReader();
                while (rdr.Read())
                {
                    list.Add(new DepartmentHeadcount
                    {
                        DepartmentName = rdr["DepartmentName"].ToString(),
                        Headcount = (int)rdr["Headcount"],
                        HeadcountLimit = (int)rdr["HeadcountLimit"]
                    });
                }
            }
            return list;
        }

        public IEnumerable<string> ReadEmployeesByDepartment(string department)
        {
            var list = new List<string>();
            using (SqlConnection con = new SqlConnection(connectionString))
            {
                SqlCommand cmd = new SqlCommand("spGetEmployeesByDepartment", con);
                cmd.CommandType = CommandType.StoredProcedure;
                cmd.Parameters.AddWithValue("@Department", department);
                con.Open();
                SqlDataReader rdr = cmd.ExecuteReader();
                while (rdr.Read())
                {
                    list.Add(rdr["Name"].ToString());
                }
            }
            return list;
        }

        // "Referenced, not found" case: spArchiveEmployee is deliberately NOT defined in repo db.
        public int Archive(int id)
        {
            using (SqlConnection con = new SqlConnection(connectionString))
            {
                SqlCommand cmd = new SqlCommand("spArchiveEmployee", con);
                cmd.CommandType = CommandType.StoredProcedure;
                cmd.Parameters.AddWithValue("@EmpId", id);
                con.Open();
                cmd.ExecuteNonQuery();
                return 1;
            }
        }
    }
}
