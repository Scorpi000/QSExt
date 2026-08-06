/**
 * ConnectionPanel - 因子库连接面板
 *
 * 展示连接列表、连接参数，提供新建/编辑/删除/重连操作。
 */

import { Card, Button, Space, Tag, Spin, Descriptions, Divider, Modal, Form, Input, Select, InputNumber } from 'antd'
import { PlusOutlined, ReloadOutlined, SyncOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import type { Connection, ConnectionCreate, ConnectionUpdate } from '../../services/connection'
import { DB_TYPES } from '../../services/connection'

interface ConnectionPanelProps {
  connections: Connection[]
  loading: boolean
  activeConnection: Connection | null
  onSelectConnection: (conn: Connection) => void
  onRefresh: () => void
  onCreate: (values: ConnectionCreate) => Promise<void>
  onEdit: (conn: Connection, values: ConnectionUpdate) => Promise<void>
  onDelete: (qsid: string, name: string) => void
  onReconnect: (qsid: string) => Promise<void>
  // Modal state
  createModalVisible: boolean
  onOpenCreate: () => void
  onCloseCreate: () => void
  createForm: any
  editModalVisible: boolean
  editingConnection: Connection | null
  onOpenEdit: (conn: Connection) => void
  onCloseEdit: () => void
  editForm: any
}

function getDbTypeColor(dbType: string) {
  const colors: Record<string, string> = {
    HDF5DB: 'blue', SQLDB: 'cyan', JYDB: 'geekblue',
    ClickHouseDB: 'orange', MongoDB: 'lime', Neo4jDB: 'purple',
  }
  return colors[dbType] || 'default'
}

function getSourceTag(source?: string) {
  if (source === 'settings') return <Tag color="green" style={{ fontSize: 10, lineHeight: '16px' }}>settings</Tag>
  if (source === 'neo4j') return <Tag color="default" style={{ fontSize: 10, lineHeight: '16px' }}>neo4j</Tag>
  return null
}

function ConnectionPanel({
  connections, loading, activeConnection, onSelectConnection, onRefresh,
  onDelete, onReconnect,
  createModalVisible, onOpenCreate, onCloseCreate, createForm, onCreate,
  editModalVisible, editingConnection, onOpenEdit, onCloseEdit, editForm, onEdit,
}: ConnectionPanelProps) {
  const handleCreate = async (values: ConnectionCreate) => {
    await onCreate(values)
    onCloseCreate()
    createForm.resetFields()
  }

  const handleEdit = async (values: ConnectionUpdate) => {
    if (!editingConnection) return
    await onEdit(editingConnection, values)
    onCloseEdit()
    editForm.resetFields()
  }

  const renderDbArgsForm = (dbType: string | undefined) => {
    if (dbType === 'HDF5DB') {
      return (
        <Form.Item name={['args', 'MainDir']} label="MainDir（主目录路径）" rules={[{ required: true, message: '请输入主目录路径' }]}>
          <Input placeholder="例如：D:/Data/HDF5DB" />
        </Form.Item>
      )
    }
    if (dbType === 'SQLDB') {
      return (
        <>
          <Form.Item name={['args', 'DBType']} label="DBType（数据库类型）" initialValue="MySQL" rules={[{ required: true }]}>
            <Select>
              <Select.Option value="MySQL">MySQL</Select.Option>
              <Select.Option value="PostgreSQL">PostgreSQL</Select.Option>
              <Select.Option value="SQL Server">SQL Server</Select.Option>
              <Select.Option value="Oracle">Oracle</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name={['args', 'IPAddr']} label="IPAddr（主机地址）" rules={[{ required: true }]}>
            <Input placeholder="127.0.0.1" />
          </Form.Item>
          <Form.Item name={['args', 'Port']} label="Port（端口）" initialValue={3306}>
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name={['args', 'User']} label="User（用户名）" initialValue="root">
            <Input />
          </Form.Item>
          <Form.Item name={['args', 'Pwd']} label="Pwd（密码）">
            <Input.Password />
          </Form.Item>
          <Form.Item name={['args', 'DBName']} label="DBName（数据库名）" rules={[{ required: true }]}>
            <Input placeholder="Scorpion" />
          </Form.Item>
        </>
      )
    }
    // Generic DB args for JYDB, ClickHouseDB, MongoDB, Neo4jDB
    if (dbType && ['JYDB', 'ClickHouseDB', 'MongoDB', 'Neo4jDB'].includes(dbType)) {
      return (
        <>
          <Form.Item name={['args', 'IPAddr']} label="IPAddr（主机地址）" rules={[{ required: true }]}>
            <Input placeholder="127.0.0.1" />
          </Form.Item>
          <Form.Item name={['args', 'Port']} label="Port（端口）">
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name={['args', 'User']} label="User（用户名）">
            <Input />
          </Form.Item>
          <Form.Item name={['args', 'Pwd']} label="Pwd（密码）">
            <Input.Password />
          </Form.Item>
          <Form.Item name={['args', 'DBName']} label="DBName（数据库名）" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
        </>
      )
    }
    return null
  }

  return (
    <>
      <Card
        title="因子库连接"
        size="small"
        extra={
          <Space size="small">
            <Button size="small" icon={<ReloadOutlined />} onClick={onRefresh} />
            <Button type="primary" size="small" icon={<PlusOutlined />} onClick={onOpenCreate}>
              新建
            </Button>
          </Space>
        }
        bodyStyle={{ padding: 0, height: 'calc(100% - 56px)', overflow: 'auto' }}
      >
        <Spin spinning={loading}>
          {connections.length > 0 ? (
            <div>
              {connections.map((conn) => (
                <div
                  key={conn.qsid}
                  style={{
                    padding: '12px 16px',
                    borderBottom: '1px solid #f0f0f0',
                    cursor: 'pointer',
                    background: activeConnection?.qsid === conn.qsid ? '#e6f7ff' : 'transparent',
                  }}
                  onClick={() => onSelectConnection(conn)}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Space>
                      <span style={{ fontWeight: 500 }}>{conn.name}</span>
                      <Tag color={getDbTypeColor(conn.db_type)}>{conn.db_type}</Tag>
                      {getSourceTag(conn.source)}
                    </Space>
                    <Space size="small">
                      <Button type="text" size="small" icon={<EditOutlined />}
                        disabled={conn.source === 'settings'}
                        onClick={(e) => { e.stopPropagation(); onOpenEdit(conn) }} />
                      <Button type="text" size="small" icon={<SyncOutlined />}
                        onClick={(e) => { e.stopPropagation(); onReconnect(conn.qsid) }} />
                      <Button type="text" size="small" danger icon={<DeleteOutlined />}
                        disabled={conn.source === 'settings'}
                        onClick={(e) => { e.stopPropagation(); onDelete(conn.qsid, conn.name) }} />
                    </Space>
                  </div>
                  <div style={{ color: '#bbb', fontSize: 11, marginTop: 2, userSelect: 'all' }}>
                    {conn.qsid}
                  </div>
                  {conn.description && (
                    <div style={{ color: '#999', fontSize: 12, marginTop: 2 }}>{conn.description}</div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div style={{ padding: '40px 16px', textAlign: 'center', color: '#999' }}>
              暂无连接，点击"新建"添加
            </div>
          )}

          {activeConnection && Object.keys(activeConnection.args).length > 0 && (
            <div style={{ padding: '0 16px 12px' }}>
              <Divider style={{ margin: '0 0 8px' }} />
              <Descriptions title="连接参数" column={1} size="small"
                labelStyle={{ color: '#666', fontSize: 12, padding: '2px 8px 2px 0' }}
                contentStyle={{ fontSize: 12, padding: '2px 0' }}>
                {Object.entries(activeConnection.args).map(([key, value]) => (
                  <Descriptions.Item key={key} label={key}>{JSON.stringify(value, null, 2)}</Descriptions.Item>
                ))}
              </Descriptions>
            </div>
          )}
        </Spin>
      </Card>

      {/* 新建连接对话框 */}
      <Modal title="新建连接" open={createModalVisible} onCancel={onCloseCreate}
        onOk={() => createForm.submit()} width={600}>
        <Form form={createForm} layout="vertical" onFinish={handleCreate}
          initialValues={{ db_type: 'HDF5DB', args: {} }}>
          <Form.Item name="name" label="连接名称" rules={[{ required: true, message: '请输入连接名称' }]}>
            <Input placeholder="例如：本地 HDF5 数据库" />
          </Form.Item>
          <Form.Item name="db_type" label="数据库类型" rules={[{ required: true, message: '请选择数据库类型' }]}>
            <Select>
              {DB_TYPES.map((type) => (
                <Select.Option key={type.value} value={type.value}>{type.icon} {type.label}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="可选描述" />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, cur) => prev.db_type !== cur.db_type}>
            {({ getFieldValue }) => renderDbArgsForm(getFieldValue('db_type'))}
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑连接对话框 */}
      <Modal title="编辑连接" open={editModalVisible} onCancel={onCloseEdit}
        onOk={() => editForm.submit()} width={600}>
        <Form form={editForm} layout="vertical" onFinish={handleEdit}>
          <Form.Item label="数据库类型">
            <Input value={editingConnection?.db_type} disabled />
          </Form.Item>
          <Form.Item name="name" label="连接名称" rules={[{ required: true, message: '请输入连接名称' }]}>
            <Input placeholder="例如：本地 HDF5 数据库" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="可选描述" />
          </Form.Item>
          <Form.Item noStyle shouldUpdate>
            {() => renderDbArgsForm(editingConnection?.db_type)}
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}

export { getDbTypeColor }
export default ConnectionPanel
