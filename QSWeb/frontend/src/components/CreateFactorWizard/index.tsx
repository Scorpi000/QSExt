/**
 * 衍生因子创建向导
 *
 * 步骤：算子选择 → 依赖选择 → 参数配置 → 预览
 */

import { useState, useEffect } from 'react'
import {
  Modal,
  Steps,
  Select,
  Transfer,
  Button,
  Space,
  message,
  Descriptions,
  Tag,
  Spin,
  Input,
  Alert,
} from 'antd'
import {
  getOperators,
  searchFactors,
  createDerivativeFactor,
  OperatorInfo,
  FactorSearchResult,
} from '../../services/registry'
import ArgForm from '../ArgForm'

interface CreateFactorWizardProps {
  open: boolean
  onClose: () => void
  onCreated?: () => void
}

function CreateFactorWizard({ open, onClose, onCreated }: CreateFactorWizardProps) {
  const [current, setCurrent] = useState(0)
  const [loading, setLoading] = useState(false)

  // Step 1: 选择算子
  const [operators, setOperators] = useState<OperatorInfo[]>([])
  const [selectedOperator, setSelectedOperator] = useState<OperatorInfo | null>(null)

  // Step 2: 选择依赖因子
  const [availableFactors, setAvailableFactors] = useState<FactorSearchResult[]>([])
  const [selectedDescriptors, setSelectedDescriptors] = useState<string[]>([])

  // Step 3: 参数配置
  const [factorName, setFactorName] = useState('')
  const [factorArgs, setFactorArgs] = useState<Record<string, any>>({})

  // Step 4: 创建
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    if (open) {
      setLoading(true)
      getOperators()
        .then((data) => setOperators(data as unknown as OperatorInfo[]))
        .catch(() => message.error('加载算子列表失败'))
        .finally(() => setLoading(false))
    }
  }, [open])

  useEffect(() => {
    if (current === 1) {
      // 加载可用因子
      searchFactors('', 50)
        .then((data) => setAvailableFactors(data as unknown as FactorSearchResult[]))
        .catch(() => message.error('加载因子列表失败'))
    }
  }, [current])

  const handleCreate = async () => {
    if (!selectedOperator || !factorName.trim()) {
      message.warning('请填写因子名称')
      return
    }
    setCreating(true)
    try {
      await createDerivativeFactor({
        name: factorName.trim(),
        operator_qsid: selectedOperator.qsid,
        descriptor_qsids: selectedDescriptors.join(','),
        factor_args_json: JSON.stringify(factorArgs),
      })
      message.success('衍生因子创建成功')
      onCreated?.()
      handleReset()
      onClose()
    } catch {
      message.error('创建失败')
    } finally {
      setCreating(false)
    }
  }

  const handleReset = () => {
    setCurrent(0)
    setSelectedOperator(null)
    setSelectedDescriptors([])
    setFactorName('')
    setFactorArgs({})
  }

  const steps = [
    {
      title: '选择算子',
      content: (
        <Spin spinning={loading}>
          <div style={{ padding: '16px 0' }}>
            <Select
              showSearch
              placeholder="搜索并选择算子..."
              style={{ width: '100%' }}
              value={selectedOperator?.qsid}
              onChange={(qsid) => {
                const op = operators.find((o) => o.qsid === qsid)
                setSelectedOperator(op || null)
                setFactorName('')
                setFactorArgs({})
              }}
              filterOption={(input, option) =>
                (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
              }
              options={operators.map((op) => ({
                label: `${op.name} (${op.operator_type})`,
                value: op.qsid,
              }))}
            />
            {selectedOperator && (
              <Descriptions size="small" column={1} style={{ marginTop: 12 }} labelStyle={{ color: '#666', fontSize: 12 }} contentStyle={{ fontSize: 12 }}>
                <Descriptions.Item label="类型">
                  <Tag>{selectedOperator.operator_type}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="类">{selectedOperator.class_name}</Descriptions.Item>
                <Descriptions.Item label="数据">{selectedOperator.data_type}</Descriptions.Item>
                {selectedOperator.description && (
                  <Descriptions.Item label="说明">{selectedOperator.description}</Descriptions.Item>
                )}
              </Descriptions>
            )}
          </div>
        </Spin>
      ),
    },
    {
      title: '选择依赖',
      content: (
        <div style={{ padding: '16px 0' }}>
          <Transfer
            dataSource={availableFactors.map((f) => ({
              key: f.qsid,
              title: f.name,
              description: `${f.factor_class} · ${f.operator_type || '-'}`,
            }))}
            targetKeys={selectedDescriptors}
            onChange={(keys) => setSelectedDescriptors(keys as string[])}
            render={(item) => item.title}
            listStyle={{ width: 250, height: 300 }}
            showSearch
            filterOption={(input, item) =>
              item.title.toLowerCase().includes(input.toLowerCase())
            }
          />
        </div>
      ),
    },
    {
      title: '参数配置',
      content: (
        <div style={{ padding: '16px 0' }}>
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontWeight: 500, fontSize: 13, marginBottom: 4 }}>因子名称</div>
            <Input
              placeholder="输入因子名称"
              value={factorName}
              onChange={(e) => setFactorName(e.target.value)}
            />
          </div>
          {selectedOperator && (
            <>
              <div style={{ fontWeight: 500, fontSize: 13, marginBottom: 8 }}>算子参数</div>
              <ArgForm
                className={selectedOperator.module_path + '.' + selectedOperator.class_name}
                formData={factorArgs}
                onChange={(data) => setFactorArgs(data)}
              />
            </>
          )}
        </div>
      ),
    },
    {
      title: '预览',
      content: (
        <div style={{ padding: '16px 0' }}>
          <Descriptions column={1} size="small" bordered labelStyle={{ fontSize: 12 }} contentStyle={{ fontSize: 12 }}>
            <Descriptions.Item label="因子名称">{factorName || '(未设置)'}</Descriptions.Item>
            <Descriptions.Item label="算子">
              {selectedOperator ? (
                <Tag>{selectedOperator.name}</Tag>
              ) : '(未选择)'}
            </Descriptions.Item>
            <Descriptions.Item label="依赖因子">
              {selectedDescriptors.length > 0
                ? selectedDescriptors.map((qsid) => (
                  <Tag key={qsid} style={{ fontSize: 11 }}>
                    {availableFactors.find((f) => f.qsid === qsid)?.name || qsid}
                  </Tag>
                ))
                : '(未选择)'}
            </Descriptions.Item>
            <Descriptions.Item label="参数">
              {Object.keys(factorArgs).length > 0
                ? JSON.stringify(factorArgs, null, 2)
                : '(默认)'}
            </Descriptions.Item>
          </Descriptions>
        </div>
      ),
    },
  ]

  return (
    <Modal
      title="创建衍生因子"
      open={open}
      onCancel={() => {
        handleReset()
        onClose()
      }}
      width={700}
      footer={null}
      destroyOnClose
    >
      <Steps
        current={current}
        size="small"
        style={{ marginBottom: 16 }}
        items={steps.map((s) => ({ title: s.title }))}
      />

      <div style={{ minHeight: 250 }}>{steps[current].content}</div>

      <div style={{ marginTop: 24, display: 'flex', justifyContent: 'space-between' }}>
        <div>
          {current > 0 && (
            <Button onClick={() => setCurrent((c) => c - 1)}>上一步</Button>
          )}
        </div>
        <Space>
          <Button onClick={() => { handleReset(); onClose(); }}>取消</Button>
          {current < steps.length - 1 && (
            <Button
              type="primary"
              onClick={() => setCurrent((c) => c + 1)}
              disabled={current === 0 && !selectedOperator}
            >
              下一步
            </Button>
          )}
          {current === steps.length - 1 && (
            <Button
              type="primary"
              onClick={handleCreate}
              loading={creating}
              disabled={!factorName.trim()}
            >
              创建
            </Button>
          )}
        </Space>
      </div>
    </Modal>
  )
}

export default CreateFactorWizard
