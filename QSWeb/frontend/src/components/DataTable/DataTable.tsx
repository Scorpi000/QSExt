import { useMemo } from 'react'
import { Table, Empty } from 'antd'
import type { ColumnsType } from 'antd/es/table'

interface DataTableProps {
  data: Record<string, any>
  columns: string[]
  index: string[]
  loading?: boolean
}

function DataTable({ data, columns, index, loading }: DataTableProps) {
  // 将数据转换为表格格式
  const { tableData, tableColumns } = useMemo(() => {
    if (!data || !columns || !index) {
      return { tableData: [], tableColumns: [] }
    }

    // 构建列定义（不显示行号列）
    const cols: ColumnsType<any> = columns.map((col) => ({
      title: col,
      dataIndex: col,
      key: col,
      width: 120,
      align: 'right' as const,
      sorter: (a: any, b: any) => {
        const va = a[col] ?? 0
        const vb = b[col] ?? 0
        return va - vb
      },
      render: (val: any) => {
        if (val === null || val === undefined) return '-'
        if (typeof val === 'number') {
          return val.toFixed(4)
        }
        return String(val)
      },
    }))

    // 构建数据
    const rows = index.map((dt, i) => {
      const row: any = {
        key: dt,
      }
      columns.forEach((col) => {
        row[col] = data[col]?.[i] ?? null
      })
      return row
    })

    return { tableData: rows, tableColumns: cols }
  }, [data, columns, index])

  if (!data || tableData.length === 0) {
    return (
      <Empty
        description="暂无数据"
        style={{ padding: '60px 0' }}
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      />
    )
  }

  return (
    <Table
      columns={tableColumns}
      dataSource={tableData}
      loading={loading}
      scroll={{ x: 'max-content', y: 500 }}
      pagination={{
        pageSize: 100,
        showSizeChanger: true,
        showQuickJumper: true,
        showTotal: (total) => `共 ${total} 行`,
      }}
      size="small"
      bordered
    />
  )
}

export default DataTable
