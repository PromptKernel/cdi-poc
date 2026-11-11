import { describe, expect, it } from 'vitest'
import { shortName } from '../components/GraphView'

describe('on-canvas labels', () => {
  it('drops namespaces from C# names but keeps class, member and parameters', () => {
    expect(shortName('ShopApp.Controllers.ItemController.Details(int)')).toBe('ItemController.Details(int)')
    expect(shortName('ShopApp.Interfaces.IItem.GetAllItems()')).toBe('IItem.GetAllItems()')
  })
  it('leaves short names, SQL names and request labels alone', () => {
    expect(shortName('dbo.tblItem')).toBe('dbo.tblItem')
    expect(shortName('GET api/Item/Details/{}')).toBe('GET api/Item/Details/{}')
    expect(shortName('FetchItemComponent')).toBe('FetchItemComponent')
  })
  it('truncates very long non-namespaced names from the left', () => {
    expect(shortName('x'.repeat(80)).length).toBeLessThanOrEqual(51)
  })
})
