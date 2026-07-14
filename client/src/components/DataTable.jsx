import { useId, useMemo, useState } from 'react'

function compareValues(a, b) {
  if (typeof a === 'number' && typeof b === 'number') return a - b
  return String(a).localeCompare(String(b), undefined, { sensitivity: 'base' })
}

function getRowKey(row, columns) {
  const knownKey = row.id
    || row.companyName
    || row.company_name
    || row.submission_id
    || row.narrative_id
    || row.user_id

  if (knownKey != null) return String(knownKey)

  return columns
    .map((column) => row[column.key])
    .filter((value) => ['string', 'number', 'boolean'].includes(typeof value))
    .join('|')
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
  const sortControlId = useId()

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
  const sortableColumns = columns.filter((column) => column.sortable)

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
      <div className="data-table-view">
        <table className="data-table">
          <thead>
            <tr>
              {columns.map((column) => {
                const isActiveSort = column.sortable && sortKey === column.key
                return (
                  <th
                    key={column.key}
                    className={column.sortable ? 'sortable' : ''}
                    scope="col"
                    aria-sort={isActiveSort ? (sortDirection === 'asc' ? 'ascending' : 'descending') : undefined}
                  >
                    {column.sortable ? (
                      <button type="button" className="data-sort-button" onClick={() => toggleSort(column.key, true)}>
                        <span>{column.label}</span>
                        {isActiveSort ? <span aria-hidden="true">{sortDirection === 'asc' ? '↑' : '↓'}</span> : null}
                      </button>
                    ) : <span>{column.label}</span>}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {paginatedRows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="empty-cell">{emptyMessage}</td>
              </tr>
            ) : (
              paginatedRows.map((row) => {
                const rowKey = getRowKey(row, columns)
                return (
                  <tr key={rowKey} className={rowClassName ? rowClassName(row) : ''}>
                    {columns.map((column) => (
                      <td key={`${rowKey}-${column.key}`}>
                        {column.render ? column.render(row) : row[column.key]}
                      </td>
                    ))}
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="data-card-view">
        {sortableColumns.length > 0 ? (
          <div className="data-card-sort">
            <label htmlFor={sortControlId}>Sort by</label>
            <select
              id={sortControlId}
              value={sortKey}
              onChange={(event) => {
                setSortKey(event.target.value)
                setCurrentPage(1)
              }}
            >
              {sortableColumns.map((column) => <option key={column.key} value={column.key}>{column.label}</option>)}
            </select>
            <button
              type="button"
              onClick={() => setSortDirection((current) => (current === 'asc' ? 'desc' : 'asc'))}
              aria-label={`Sort ${sortDirection === 'asc' ? 'descending' : 'ascending'}`}
            >
              <span aria-hidden="true">{sortDirection === 'asc' ? '↑' : '↓'}</span>
            </button>
          </div>
        ) : null}

        {paginatedRows.length === 0 ? (
          <p className="data-card-empty">{emptyMessage}</p>
        ) : (
          <div className="data-card-list">
            {paginatedRows.map((row) => {
              const rowKey = getRowKey(row, columns)
              return (
                <article className={`data-card ${rowClassName ? rowClassName(row) : ''}`} key={rowKey}>
                  <dl>
                    {columns.map((column) => (
                      <div key={`${rowKey}-mobile-${column.key}`}>
                        <dt>{column.label}</dt>
                        <dd>{column.render ? column.render(row) : row[column.key]}</dd>
                      </div>
                    ))}
                  </dl>
                </article>
              )
            })}
          </div>
        )}
      </div>

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
