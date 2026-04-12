import { useMemo, useState } from 'react'

function compareValues(a, b) {
  if (typeof a === 'number' && typeof b === 'number') return a - b
  return String(a).localeCompare(String(b), undefined, { sensitivity: 'base' })
}

export default function DataTable({
  columns,
  rows,
  pageSize = 10,
  searchQuery = '',
  rowClassName,
  emptyMessage = 'No records found.',
}) {
  const defaultSortKey = columns.find((column) => column.sortable)?.key || columns[0]?.key
  const [sortKey, setSortKey] = useState(defaultSortKey)
  const [sortDirection, setSortDirection] = useState('asc')
  const [currentPage, setCurrentPage] = useState(1)

  const filteredRows = useMemo(() => {
    if (!searchQuery.trim()) return rows

    const needle = searchQuery.trim().toLowerCase()
    return rows.filter((row) =>
      Object.values(row).some((value) => String(value).toLowerCase().includes(needle))
    )
  }, [rows, searchQuery])

  const sortedRows = useMemo(() => {
    const sorted = [...filteredRows]
    const selectedColumn = columns.find((column) => column.key === sortKey)
    if (!selectedColumn) return sorted

    const accessor = selectedColumn.sortAccessor || ((row) => row[selectedColumn.key])

    sorted.sort((left, right) => {
      const result = compareValues(accessor(left), accessor(right))
      return sortDirection === 'asc' ? result : -result
    })

    return sorted
  }, [columns, filteredRows, sortDirection, sortKey])

  const pageCount = Math.max(1, Math.ceil(sortedRows.length / pageSize))
  const safePage = Math.min(currentPage, pageCount)
  const paginatedRows = sortedRows.slice((safePage - 1) * pageSize, safePage * pageSize)

  const toggleSort = (key, sortable) => {
    if (!sortable) return
    if (sortKey === key) {
      setSortDirection((current) => (current === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDirection('asc')
    }
    setCurrentPage(1)
  }

  return (
    <div className="table-shell">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                className={column.sortable ? 'sortable' : ''}
                onClick={() => toggleSort(column.key, column.sortable)}
                scope="col"
              >
                <span>{column.label}</span>
                {column.sortable && sortKey === column.key ? (
                  <small>{sortDirection === 'asc' ? ' ^' : ' v'}</small>
                ) : null}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {paginatedRows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="empty-cell">{emptyMessage}</td>
            </tr>
          ) : (
            paginatedRows.map((row) => (
              <tr key={row.id || row.companyName} className={rowClassName ? rowClassName(row) : ''}>
                {columns.map((column) => (
                  <td key={`${row.id || row.companyName}-${column.key}`}>
                    {column.render ? column.render(row) : row[column.key]}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>

      <div className="table-footer">
        <p>
          Showing {paginatedRows.length === 0 ? 0 : (safePage - 1) * pageSize + 1}-
          {(safePage - 1) * pageSize + paginatedRows.length} of {sortedRows.length}
        </p>
        <div className="pagination-controls">
          <button type="button" onClick={() => setCurrentPage((p) => Math.max(1, p - 1))} disabled={safePage === 1}>
            Prev
          </button>
          <span>{safePage} / {pageCount}</span>
          <button type="button" onClick={() => setCurrentPage((p) => Math.min(pageCount, p + 1))} disabled={safePage === pageCount}>
            Next
          </button>
        </div>
      </div>
    </div>
  )
}
