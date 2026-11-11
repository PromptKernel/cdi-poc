import { describe, expect, it } from 'vitest'
import { shortName } from '../components/GraphView'

describe('on-canvas labels', () => {
  it('drops namespaces from C# names but keeps class, member and parameters', () => {
    expect(shortName('ASPCoreWithAngular.Controllers.EmployeeController.Details(int)')).toBe('EmployeeController.Details(int)')
    expect(shortName('ASPCoreWithAngular.Interfaces.IEmployee.GetAllEmployees()')).toBe('IEmployee.GetAllEmployees()')
  })
  it('leaves short names, SQL names and request labels alone', () => {
    expect(shortName('dbo.tblEmployee')).toBe('dbo.tblEmployee')
    expect(shortName('GET api/Employee/Details/{}')).toBe('GET api/Employee/Details/{}')
    expect(shortName('FetchEmployeeComponent')).toBe('FetchEmployeeComponent')
  })
  it('truncates very long non-namespaced names from the left', () => {
    expect(shortName('x'.repeat(80)).length).toBeLessThanOrEqual(51)
  })
})
