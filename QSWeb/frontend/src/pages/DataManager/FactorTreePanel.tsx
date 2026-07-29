/**
 * FactorTreePanel - 因子树浏览面板
 *
 * 展示选中连接的因子表树，支持表/因子选择和右键操作。
 */

import { Card } from 'antd'
import FactorTree from '../../components/FactorTree/FactorTree'
import type { FactorInfo, FactorTable } from '../../services/factor'
import { isWritableDB } from '../../services/connection'

interface FactorTreePanelProps {
  connectionId: string
  connectionName: string
  dbType: string
  treeRefreshKey: number
  onFactorSelect: (factor: FactorInfo) => void
  onTableSelect: (table: FactorTable) => void
  onTableRename: (oldName: string, newName: string) => Promise<void>
  onTableDelete: (tableNames: string[]) => Promise<void>
  onFactorRename: (tableName: string, oldName: string, newName: string) => Promise<void>
  onFactorDelete: (tableName: string, factorNames: string[]) => Promise<void>
}

function FactorTreePanel({
  connectionId, connectionName, dbType, treeRefreshKey,
  onFactorSelect, onTableSelect,
  onTableRename, onTableDelete, onFactorRename, onFactorDelete,
}: FactorTreePanelProps) {
  return (
    <Card
      title="因子浏览"
      size="small"
      style={{ height: '100%' }}
      bodyStyle={{ padding: 0, height: 'calc(100% - 46px)', overflow: 'hidden' }}
    >
      <FactorTree
        key={`${connectionId}-${treeRefreshKey}`}
        connectionId={connectionId}
        connectionName={connectionName}
        readonly={!isWritableDB(dbType)}
        onFactorSelect={onFactorSelect}
        onTableSelect={onTableSelect}
        onTableRename={onTableRename}
        onTableDelete={onTableDelete}
        onFactorRename={onFactorRename}
        onFactorDelete={onFactorDelete}
      />
    </Card>
  )
}

export default FactorTreePanel
