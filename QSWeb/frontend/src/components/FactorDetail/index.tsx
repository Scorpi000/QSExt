/**
 * 因子详情面板
 */

import { useEffect } from 'react'
import { Spin, Descriptions, Tag, List, Empty, Typography, message } from 'antd'
import { getFactorDetail, FactorDetail as FactorDetailType } from '../../services/registry'
import { useFactorWorkbenchStore } from '../../stores/factorWorkbench'

const { Text } = Typography

function FactorDetail() {
  const {
    selectedQSID,
    selectedFactor,
    loadingDetail,
    setSelectedFactor,
    setLoadingDetail,
  } = useFactorWorkbenchStore()

  useEffect(() => {
    if (selectedQSID) {
      setLoadingDetail(true)
      getFactorDetail(selectedQSID)
        .then((data) => {
          setSelectedFactor(data as unknown as FactorDetailType)
        })
        .catch(() => {
          message.error('加载因子详情失败')
          setSelectedFactor(null)
        })
        .finally(() => {
          setLoadingDetail(false)
        })
    } else {
      setSelectedFactor(null)
    }
  }, [selectedQSID, setSelectedFactor, setLoadingDetail])

  if (!selectedQSID) {
    return (
      <Empty
        description="选择因子查看详情"
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        style={{ padding: '20px 0' }}
      />
    )
  }

  if (loadingDetail || !selectedFactor) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
        <Spin />
      </div>
    )
  }

  const factorClassMap: Record<string, { label: string; color: string }> = {
    DataFactor: { label: '数据因子', color: 'blue' },
    FactorTableFactor: { label: '因子表因子', color: 'geekblue' },
    DerivativeFactor: { label: '衍生因子', color: 'purple' },
  }
  const classInfo = factorClassMap[selectedFactor.factor_class] || { label: selectedFactor.factor_class, color: 'default' }

  return (
    <div style={{ padding: '12px', overflow: 'auto', height: '100%' }}>
      <Descriptions column={1} size="small" labelStyle={{ color: '#666', fontSize: 12, width: 80 }} contentStyle={{ fontSize: 12 }}>
        <Descriptions.Item label="名称">{selectedFactor.name}</Descriptions.Item>
        <Descriptions.Item label="QSID">
          <Text code style={{ fontSize: 11 }}>{selectedFactor.qsid}</Text>
        </Descriptions.Item>
        <Descriptions.Item label="类型">
          <Tag color={classInfo.color}>
            {classInfo.label}
          </Tag>
        </Descriptions.Item>
        {selectedFactor.data_type && (
          <Descriptions.Item label="数据类型">{selectedFactor.data_type}</Descriptions.Item>
        )}
        {selectedFactor.operator_name && (
          <Descriptions.Item label="算子">{selectedFactor.operator_name}</Descriptions.Item>
        )}
        {selectedFactor.operator_type && (
          <Descriptions.Item label="算子类型">
            <Tag>{selectedFactor.operator_type}</Tag>
          </Descriptions.Item>
        )}
        <Descriptions.Item label="深度">{selectedFactor.dependency_depth}</Descriptions.Item>
        {selectedFactor.description && (
          <Descriptions.Item label="描述">
            <Text style={{ fontSize: 12 }}>{selectedFactor.description}</Text>
          </Descriptions.Item>
        )}
      </Descriptions>

      {/* 依赖因子 */}
      {selectedFactor.descriptors.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontWeight: 500, fontSize: 12, marginBottom: 4, color: '#666' }}>
            上游依赖 ({selectedFactor.descriptors.length})
          </div>
          <List
            size="small"
            dataSource={selectedFactor.descriptors}
            renderItem={(item) => (
              <List.Item
                style={{ cursor: 'pointer', padding: '4px 8px' }}
                onClick={() => useFactorWorkbenchStore.getState().setSelectedQSID(item.qsid)}
              >
                <Text style={{ fontSize: 12 }}>{item.name}</Text>
              </List.Item>
            )}
            style={{ background: '#fafafa', borderRadius: 4 }}
          />
        </div>
      )}

      {/* 下游因子 */}
      {selectedFactor.dependents.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontWeight: 500, fontSize: 12, marginBottom: 4, color: '#666' }}>
            下游引用 ({selectedFactor.dependents.length})
          </div>
          <List
            size="small"
            dataSource={selectedFactor.dependents}
            renderItem={(item) => (
              <List.Item
                style={{ cursor: 'pointer', padding: '4px 8px' }}
                onClick={() => useFactorWorkbenchStore.getState().setSelectedQSID(item.qsid)}
              >
                <Text style={{ fontSize: 12 }}>{item.name}</Text>
              </List.Item>
            )}
            style={{ background: '#fafafa', borderRadius: 4 }}
          />
        </div>
      )}

      {/* 标签 */}
      {selectedFactor.tags.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontWeight: 500, fontSize: 12, marginBottom: 4, color: '#666' }}>标签</div>
          <div>
            {selectedFactor.tags.map((tag) => (
              <Tag key={tag} style={{ fontSize: 11, marginBottom: 4 }}>{tag}</Tag>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default FactorDetail
