import { useMemo, useState } from 'react'
import Button from './Button'
import EmptyState from './EmptyState'
import StatusBadge from '../StatusBadge'

function compareValues(a, b) {
  if (a === b) return 0
  if (a === null || a === undefined || a === '') return -1
  if (b === null || b === undefined || b === '') return 1
  if (typeof a === 'number' && typeof b === 'number') return a - b
  return String(a).localeCompare(String(b), undefined, { sensitivity: 'base' })
}

export default function DataTable({
  columns,
  rows,
  pageSize = 10,
  searchQuery = '',
  rowClassName,
  emptyTitle = 'Nothing to show',
  emptyMessage = 'There are no rows available for this view.',
  emptyActionLabel,
  onEmptyAction,
  onRowClick,
  rowKey = (row) => row.id || row.companyName || row.fieldKey,
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
  const hasRows = paginatedRows.length > 0

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
    <div className="ui-table-shell">
      <div className="ui-table-scroll">
        <table className="ui-table">
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
                    <span className="ui-table-sort">{sortDirection === 'asc' ? '↑' : '↓'}</span>
                  ) : null}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {!hasRows ? (
              <tr>
                <td colSpan={columns.length}>
                  <EmptyState
                    title={emptyTitle}
                    description={emptyMessage}
                    actionLabel={emptyActionLabel}
                    onAction={onEmptyAction}
                  />
                </td>
              </tr>
            ) : (
              paginatedRows.map((row) => {
                const key = rowKey(row)
                return (
                  <tr
                    key={key}
                    className={[rowClassName ? rowClassName(row) : '', onRowClick ? 'clickable' : '']
                      .filter(Boolean)
                      .join(' ')}
                    onClick={onRowClick ? () => onRowClick(row) : undefined}
                  >
                    {columns.map((column) => (
                      <td key={`${key}-${column.key}`}>
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

      <div className="ui-table-footer">
        <p>
          Showing {hasRows ? (safePage - 1) * pageSize + 1 : 0}-
          {hasRows ? (safePage - 1) * pageSize + paginatedRows.length : 0} of {sortedRows.length}
        </p>
        <div className="ui-pagination">
          <Button variant="secondary" onClick={() => setCurrentPage((p) => Math.max(1, p - 1))} disabled={safePage === 1}>
            Prev
          </Button>
          <span>
            {safePage} / {pageCount}
          </span>
          <Button
            variant="secondary"
            onClick={() => setCurrentPage((p) => Math.min(pageCount, p + 1))}
            disabled={safePage === pageCount}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  )
}

