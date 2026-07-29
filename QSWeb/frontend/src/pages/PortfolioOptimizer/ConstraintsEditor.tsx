/**
 * ConstraintsEditor - 约束条件编辑器
 *
 * 约束列表展示 + 添加/编辑约束弹窗。
 */

import { useState } from 'react'
import { Button, List, Tag, Space, Typography, Empty, Popconfirm, Modal, Form, Select, InputNumber } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import type { ConstraintDef } from '../../services/portfolio'
import { CONSTRAINT_TYPES } from '../../services/portfolio'

const { Text } = Typography

const CONSTRAINT_DEFAULTS: Record<string, any> = {
  budget: { up_limit: 1.0, down_limit: 1.0 },
  box: { lbs: 0.0, ubs: 0.1 },
  turnover: { up_limit: 0.5, constraint_type: '总换手限制' },
  cardinality: { max_nonzero: 50 },
}

interface ConstraintsEditorProps {
  constraints: ConstraintDef[]
  onConstraintsChange: (constraints: ConstraintDef[]) => void
}

function ConstraintsEditor({ constraints, onConstraintsChange }: ConstraintsEditorProps) {
  const [modalOpen, setModalOpen] = useState(false)
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [constraintType, setConstraintType] = useState<ConstraintDef['type']>('budget')
  const [constraintValues, setConstraintValues] = useState<Record<string, any>>({})

  const handleAdd = () => {
    setEditingIndex(null)
    setConstraintType('budget')
    setConstraintValues({ ...CONSTRAINT_DEFAULTS.budget })
    setModalOpen(true)
  }

  const handleEdit = (index: number) => {
    const c = constraints[index]
    setEditingIndex(index)
    setConstraintType(c.type)
    setConstraintValues({ ...(CONSTRAINT_DEFAULTS[c.type] || {}), ...c })
    setModalOpen(true)
  }

  const handleDelete = (index: number) => {
    onConstraintsChange(constraints.filter((_, i) => i !== index))
  }

  const handleOk = () => {
    const newConstraint: ConstraintDef = { type: constraintType, ...constraintValues }
    if (editingIndex !== null) {
      onConstraintsChange(constraints.map((c, i) => (i === editingIndex ? newConstraint : c)))
    } else {
      onConstraintsChange([...constraints, newConstraint])
    }
    setModalOpen(false)
  }

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <Text strong>约束条件</Text>
        <Button size="small" type="dashed" icon={<PlusOutlined />} onClick={handleAdd}>
          添加约束
        </Button>
      </div>

      {constraints.length === 0 ? (
        <Empty description="暂无约束，点击「添加约束」配置" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ margin: '12px 0' }} />
      ) : (
        <List
          size="small"
          dataSource={constraints}
          renderItem={(c, i) => (
            <List.Item
              actions={[
                <Button key="edit" size="small" type="link" icon={<EditOutlined />} onClick={() => handleEdit(i)} />,
                <Popconfirm key="del" title="确定删除该约束？" onConfirm={() => handleDelete(i)}>
                  <Button size="small" type="link" danger icon={<DeleteOutlined />} />
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                title={
                  <Space>
                    <Tag color="blue">{CONSTRAINT_TYPES.find((t) => t.value === c.type)?.label || c.type}</Tag>
                  </Space>
                }
                description={
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {JSON.stringify({ ...c, type: undefined })}
                  </Text>
                }
              />
            </List.Item>
          )}
        />
      )}

      {/* 约束编辑弹窗 */}
      <Modal title={editingIndex !== null ? '编辑约束' : '添加约束'}
        open={modalOpen} onOk={handleOk} onCancel={() => setModalOpen(false)} destroyOnClose>
        <Form layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item label="约束类型">
            <Select
              value={constraintType}
              onChange={(v) => { setConstraintType(v); setConstraintValues({ ...(CONSTRAINT_DEFAULTS[v] || {}) }) }}
              options={CONSTRAINT_TYPES.map((t) => ({ value: t.value, label: `${t.label}  —  ${t.desc}` }))}
            />
          </Form.Item>
          {constraintType === 'budget' && (
            <>
              <Form.Item label="权重下限">
                <InputNumber min={0} max={1} step={0.1} value={constraintValues.down_limit}
                  onChange={(v) => setConstraintValues({ ...constraintValues, down_limit: v ?? 1.0 })} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item label="权重上限">
                <InputNumber min={0} max={1} step={0.1} value={constraintValues.up_limit}
                  onChange={(v) => setConstraintValues({ ...constraintValues, up_limit: v ?? 1.0 })} style={{ width: '100%' }} />
              </Form.Item>
            </>
          )}
          {constraintType === 'box' && (
            <>
              <Form.Item label="个股权重下限">
                <InputNumber min={0} max={1} step={0.01} value={constraintValues.lbs}
                  onChange={(v) => setConstraintValues({ ...constraintValues, lbs: v ?? 0.0 })} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item label="个股权重上限">
                <InputNumber min={0} max={1} step={0.01} value={constraintValues.ubs}
                  onChange={(v) => setConstraintValues({ ...constraintValues, ubs: v ?? 0.1 })} style={{ width: '100%' }} />
              </Form.Item>
            </>
          )}
          {constraintType === 'turnover' && (
            <>
              <Form.Item label="换手率上限">
                <InputNumber min={0} max={1} step={0.05} value={constraintValues.up_limit}
                  onChange={(v) => setConstraintValues({ ...constraintValues, up_limit: v ?? 0.5 })} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item label="约束类型">
                <Select value={constraintValues.constraint_type}
                  onChange={(v) => setConstraintValues({ ...constraintValues, constraint_type: v })}
                  options={[
                    { value: '总换手限制', label: '总换手限制' },
                    { value: '总买入限制', label: '总买入限制' },
                    { value: '总卖出限制', label: '总卖出限制' },
                  ]} />
              </Form.Item>
            </>
          )}
          {constraintType === 'cardinality' && (
            <Form.Item label="最大持仓数">
              <InputNumber min={1} max={500} step={1} value={constraintValues.max_nonzero}
                onChange={(v) => setConstraintValues({ ...constraintValues, max_nonzero: v ?? 50 })} style={{ width: '100%' }} />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </>
  )
}

export default ConstraintsEditor
