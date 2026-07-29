/**
 * DataPreviewPanel - 数据预览面板
 *
 * 展示已选因子/表的数据预览、统计信息、元数据编辑。
 */

import { Card, Spin, Space, Select, DatePicker, InputNumber, Switch, Button, Tag, Descriptions, Divider } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import DataTable from '../../components/DataTable/DataTable'
import MetadataEditor from '../../components/MetadataEditor/MetadataEditor'
import type { FactorInfo, FactorTable, FactorData, FactorStats } from '../../services/factor'
import { isWritableDB } from '../../services/connection'

const { RangePicker } = DatePicker

interface DataPreviewPanelProps {
  // 选中状态
  selectedFactor: FactorInfo | null
  selectedTable: FactorTable | null
  factorData: FactorData | null
  loadingData: boolean
  factorStats: FactorStats | null
  factorMeta: Record<string, any> | null
  tableMeta: Record<string, any> | null
  // 查询参数
  dateRange: [dayjs.Dayjs, dayjs.Dayjs] | null
  limit: number
  filterNaN: boolean
  selectedIds: string[]
  // 连接信息
  dbType: string
  // 回调
  onDateRangeChange: (dates: [dayjs.Dayjs, dayjs.Dayjs] | null) => void
  onLimitChange: (limit: number) => void
  onFilterNaNChange: (filter: boolean) => void
  onSelectedIdsChange: (ids: string[]) => void
  onRefresh: () => void
  onFactorMetadataSave: (metadata: Record<string, any>) => Promise<void>
  onTableMetadataSave: (metadata: Record<string, any>) => Promise<void>
}

function DataPreviewPanel({
  selectedFactor, selectedTable, factorData, loadingData,
  factorStats, factorMeta, tableMeta,
  dateRange, limit, filterNaN, selectedIds, dbType,
  onDateRangeChange, onLimitChange, onFilterNaNChange, onSelectedIdsChange, onRefresh,
  onFactorMetadataSave, onTableMetadataSave,
}: DataPreviewPanelProps) {
  const title = selectedFactor
    ? `${selectedFactor.table_name} / ${selectedFactor.name}`
    : selectedTable
      ? `${selectedTable.name} / 表信息`
      : '数据预览'

  return (
    <Card
      title={title}
      size="small"
      style={{ height: '100%' }}
      bodyStyle={{ padding: 0, height: 'calc(100% - 46px)', overflow: 'auto' }}
    >
      {selectedFactor ? (
        <Spin spinning={loadingData}>
          {/* 操作栏 */}
          <div style={{ padding: '8px 16px', borderBottom: '1px solid #f0f0f0' }}>
            <Space size="small" wrap>
              <Select
                mode="tags" size="small" placeholder="筛选 code"
                value={selectedIds} onChange={onSelectedIdsChange}
                style={{ minWidth: 150, maxWidth: 250 }}
                maxTagCount="responsive" allowClear
              />
              <RangePicker size="small" value={dateRange}
                onChange={(dates) => onDateRangeChange(dates as [dayjs.Dayjs, dayjs.Dayjs])} />
              <InputNumber size="small" value={limit}
                onChange={(v) => onLimitChange(v || 1000)} min={1} max={10000}
                style={{ width: 90 }} addonBefore="行数" />
              <Space size={4}>
                <Switch size="small" checked={filterNaN} onChange={onFilterNaNChange} />
                <span style={{ fontSize: 12 }}>过滤缺失值</span>
              </Space>
              <Button size="small" icon={<ReloadOutlined />} onClick={onRefresh}>刷新</Button>
            </Space>
          </div>

          {/* 因子统计信息 */}
          {factorStats && (
            <div style={{ padding: '6px 16px', borderBottom: '1px solid #f0f0f0', background: '#fafafa' }}>
              <Space size="middle" wrap style={{ fontSize: 12 }}>
                <span>
                  <span style={{ color: '#888' }}>起止ID：</span>
                  <Tag>{factorStats.first_id ?? '-'}</Tag>
                  <span style={{ color: '#ccc' }}>~</span>
                  <Tag>{factorStats.last_id ?? '-'}</Tag>
                  <span style={{ color: '#888' }}>数量：</span>
                  <Tag color="blue">{factorStats.id_count}</Tag>
                </span>
                <span>
                  <span style={{ color: '#888' }}>起止时间：</span>
                  <Tag>{factorStats.first_dt ?? '-'}</Tag>
                  <span style={{ color: '#ccc' }}>~</span>
                  <Tag>{factorStats.last_dt ?? '-'}</Tag>
                  <span style={{ color: '#888' }}>数量：</span>
                  <Tag color="green">{factorStats.dt_count}</Tag>
                </span>
              </Space>
            </div>
          )}

          {/* 因子元数据 */}
          <div style={{ padding: '8px 16px', borderBottom: '1px solid #f0f0f0' }}>
            <MetadataEditor
              title="因子信息"
              metadata={factorMeta || {}}
              onSave={onFactorMetadataSave}
              readonly={!isWritableDB(dbType)}
            />
          </div>

          <DataTable
            data={factorData?.data || {}}
            columns={factorData?.columns || []}
            index={factorData?.index || []}
            loading={loadingData}
          />
        </Spin>
      ) : selectedTable ? (
        <div style={{ padding: '16px' }}>
          <Descriptions title="表基本信息" column={2} size="small"
            labelStyle={{ color: '#666', fontSize: 12 }}
            contentStyle={{ fontSize: 12 }}>
            <Descriptions.Item label="表名">{selectedTable.name}</Descriptions.Item>
            <Descriptions.Item label="因子数量">{selectedTable.factor_count ?? '-'}</Descriptions.Item>
            {selectedTable.description && (
              <Descriptions.Item label="描述">{selectedTable.description}</Descriptions.Item>
            )}
          </Descriptions>
          <Divider style={{ margin: '12px 0' }} />
          <MetadataEditor
            title="因子表信息"
            metadata={tableMeta || {}}
            onSave={onTableMetadataSave}
            readonly={!isWritableDB(dbType)}
          />
        </div>
      ) : (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%', color: '#999' }}>
          请从左侧因子树中选择一个表或因子
        </div>
      )}
    </Card>
  )
}

export default DataPreviewPanel
