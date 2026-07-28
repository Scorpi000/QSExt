/**
 * 报告中心页面
 *
 * 支持报告生成（异步任务 + 进度）、报告列表浏览、预览和下载。
 */

import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Card,
  Form,
  Select,
  Input,
  Button,
  DatePicker,
  Checkbox,
  Table,
  Tag,
  Space,
  Modal,
  Tabs,
  message,
  Progress,
  Popconfirm,
  Collapse,
  Spin,
  Empty,
} from 'antd'
import {
  PlusOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EyeOutlined,
  LinkOutlined,
  FileTextOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { getConnections, type Connection } from '../../services/connection'
import { getTables, getFactors, type FactorInfo, type FactorTable } from '../../services/factor'
import {
  listScenarios,
  generateReport,
  listReports,
  getReportContent,
  deleteReport,
  registerReport,
  getTask,
  getReportConfig,
  updateReportConfig,
  type ReportScenario,
  type ReportInfo,
  type ReportGenerateRequest,
  type FactorRef,
  type TaskStatus,
} from '../../services/report'

const { RangePicker } = DatePicker

// ─── FactorRef 选择器 ─────────────────────────────────────────

interface FactorRefSelectorProps {
  value?: FactorRef
  onChange?: (ref: FactorRef | undefined) => void
  label?: string
  allowClear?: boolean
}

function FactorRefSelector({ value, onChange, label, allowClear }: FactorRefSelectorProps) {
  const [connections, setConnections] = useState<Connection[]>([])
  const [tables, setTables] = useState<FactorTable[]>([])
  const [factors, setFactors] = useState<FactorInfo[]>([])
  const [connId, setConnId] = useState<string>(value?.conn_id || '')
  const [tableName, setTableName] = useState<string>(value?.table_name || '')
  const [factorName, setFactorName] = useState<string>(value?.factor_name || '')
  const [loadingTables, setLoadingTables] = useState(false)
  const [loadingFactors, setLoadingFactors] = useState(false)

  useEffect(() => {
    getConnections().then((d) => setConnections(d as unknown as Connection[])).catch(() => {})
  }, [])

  useEffect(() => {
    if (value) {
      setConnId(value.conn_id)
      setTableName(value.table_name)
      setFactorName(value.factor_name)
    }
  }, [value])

  const handleConnChange = async (id: string) => {
    setConnId(id)
    setTableName('')
    setFactorName('')
    setTables([])
    setFactors([])
    onChange?.(undefined)
    if (!id) return
    setLoadingTables(true)
    try {
      const res = await getTables(id)
      setTables(res as unknown as FactorTable[])
    } catch { setTables([]) }
    finally { setLoadingTables(false) }
  }

  const handleTableChange = async (name: string) => {
    setTableName(name)
    setFactorName('')
    setFactors([])
    onChange?.(undefined)
    if (!name) return
    setLoadingFactors(true)
    try {
      const res = await getFactors(connId, name)
      setFactors(res as unknown as FactorInfo[])
    } catch { setFactors([]) }
    finally { setLoadingFactors(false) }
  }

  const handleFactorChange = (name: string) => {
    setFactorName(name)
    if (name && connId && tableName) {
      onChange?.({ conn_id: connId, table_name: tableName, factor_name: name })
    } else {
      onChange?.(undefined)
    }
  }

  return (
    <Space wrap>
      {label && <span style={{ fontSize: 13, color: '#666', minWidth: 80 }}>{label}</span>}
      <Select
        placeholder="连接"
        style={{ width: 150 }}
        value={connId || undefined}
        onChange={handleConnChange}
        allowClear={allowClear}
        options={connections.map((c) => ({ value: c.id, label: c.name }))}
      />
      <Select
        placeholder="因子表"
        style={{ width: 300 }}
        value={tableName || undefined}
        onChange={handleTableChange}
        allowClear={allowClear}
        loading={loadingTables}
        options={tables.map((t) => ({ value: t.name, label: t.name }))}
      />
      <Select
        placeholder="因子"
        style={{ width: 300 }}
        value={factorName || undefined}
        onChange={handleFactorChange}
        allowClear={allowClear}
        loading={loadingFactors}
        showSearch
        filterOption={(input, option) =>
          (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
        }
        options={factors.map((f) => ({ value: f.name, label: f.name }))}
      />
    </Space>
  )
}

// ─── 多因子选择器 ─────────────────────────────────────────────

interface MultiFactorPickerProps {
  value?: FactorRef[]
  onChange?: (refs: FactorRef[]) => void
}

function MultiFactorPicker({ value = [], onChange }: MultiFactorPickerProps) {
  const [connections, setConnections] = useState<Connection[]>([])
  const [tables, setTables] = useState<FactorTable[]>([])
  const [factors, setFactors] = useState<FactorInfo[]>([])
  const [connId, setConnId] = useState<string>('')
  const [tableName, setTableName] = useState<string>('')
  const [selectedNames, setSelectedNames] = useState<string[]>([])
  const [loadingTables, setLoadingTables] = useState(false)
  const [loadingFactors, setLoadingFactors] = useState(false)

  useEffect(() => {
    getConnections().then((d) => setConnections(d as unknown as Connection[])).catch(() => {})
  }, [])

  const handleConnChange = async (id: string) => {
    setConnId(id)
    setTableName('')
    setFactors([])
    if (!id) return
    setLoadingTables(true)
    try {
      const res = await getTables(id)
      setTables(res as unknown as FactorTable[])
    } catch { setTables([]) }
    finally { setLoadingTables(false) }
  }

  const handleTableChange = async (name: string) => {
    setTableName(name)
    setFactors([])
    if (!name || !connId) return
    setLoadingFactors(true)
    try {
      const res = await getFactors(connId, name)
      setFactors(res as unknown as FactorInfo[])
    } catch { setFactors([]) }
    finally { setLoadingFactors(false) }
  }

  const addFactor = (name: string) => {
    if (!name || !connId || !tableName) return
    const exists = value.some(
      (r) => r.conn_id === connId && r.table_name === tableName && r.factor_name === name
    )
    if (exists) {
      message.warning('该因子已添加')
      return
    }
    const newRef: FactorRef = { conn_id: connId, table_name: tableName, factor_name: name }
    onChange?.([...value, newRef])
    setSelectedNames([])
  }

  const removeFactor = (ref: FactorRef) => {
    onChange?.(value.filter(
      (r) => !(r.conn_id === ref.conn_id && r.table_name === ref.table_name && r.factor_name === ref.factor_name)
    ))
  }

  return (
    <div>
      <Space wrap style={{ marginBottom: 8 }}>
        <Select
          placeholder="连接"
          style={{ width: 150 }}
          value={connId || undefined}
          onChange={handleConnChange}
          options={connections.map((c) => ({ value: c.id, label: c.name }))}
        />
        <Select
          placeholder="因子表"
          style={{ width: 300 }}
          value={tableName || undefined}
          onChange={handleTableChange}
          loading={loadingTables}
          options={tables.map((t) => ({ value: t.name, label: t.name }))}
        />
        <Select
          placeholder="选择要添加的因子"
          style={{ width: 220 }}
          value={selectedNames}
          onChange={(names) => {
            const last = names[names.length - 1]
            if (last) addFactor(last)
          }}
          mode="multiple"
          loading={loadingFactors}
          showSearch
          filterOption={(input, option) =>
            (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
          }
          options={factors.map((f) => ({ value: f.name, label: f.name }))}
        />
      </Space>
      <div>
        {value.map((ref) => (
          <Tag
            key={`${ref.conn_id}:${ref.table_name}:${ref.factor_name}`}
            closable
            onClose={() => removeFactor(ref)}
            color="blue"
          >
            {ref.factor_name}
          </Tag>
        ))}
        {value.length === 0 && <span style={{ color: '#999', fontSize: 12 }}>请添加至少一个被测因子</span>}
      </div>
    </div>
  )
}

// ─── 主页面 ──────────────────────────────────────────────────

export default function ReportCenter() {
  // 生成表单状态
  const [scenarios, setScenarios] = useState<ReportScenario[]>([])
  const [scenario, setScenario] = useState('single_factor')
  const [reportName, setReportName] = useState('')
  const [factorRefs, setFactorRefs] = useState<FactorRef[]>([])
  const [priceRef, setPriceRef] = useState<FactorRef | undefined>()
  const [maskRef, setMaskRef] = useState<FactorRef | undefined>()
  const [catDataRef, setCatDataRef] = useState<FactorRef | undefined>()
  const [weightRef, setWeightRef] = useState<FactorRef | undefined>()
  const defaultDateRange = useMemo<[string, string]>(() => {
    const end = dayjs()
    const start = dayjs().subtract(3, 'year')
    return [start.format('YYYY-MM-DD'), end.format('YYYY-MM-DD')]
  }, [])
  const [dateRange, setDateRange] = useState<[string, string] | null>(defaultDateRange)
  const [outputFormats, setOutputFormats] = useState<string[]>(['html'])
  const [modules, setModules] = useState<Record<string, boolean>>({
    ic: true,
    ic_decay: true,
    quantile_portfolio: true,
    factor_turnover: true,
  })

  // 任务状态
  const [taskId, setTaskId] = useState<string | null>(null)
  const [taskStatus, setTaskStatus] = useState<TaskStatus | null>(null)
  const [generating, setGenerating] = useState(false)

  // 报告列表
  const [reports, setReports] = useState<ReportInfo[]>([])
  const [loadingReports, setLoadingReports] = useState(false)
  const [filterScenario, setFilterScenario] = useState<string | undefined>()
  const [filterFactor, setFilterFactor] = useState<string>('')

  // 预览
  const [previewReport, setPreviewReport] = useState<ReportInfo | null>(null)
  const [previewContent, setPreviewContent] = useState<Record<string, string> | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewVisible, setPreviewVisible] = useState(false)

  // 注册
  const [registering, setRegistering] = useState<string | null>(null)

  // 配置
  const [outputDir, setOutputDir] = useState('')
  const [editingDir, setEditingDir] = useState(false)
  const [editDirValue, setEditDirValue] = useState('')
  const [savingDir, setSavingDir] = useState(false)

  // 初始化
  useEffect(() => {
    listScenarios().then((d) => setScenarios(d as unknown as ReportScenario[])).catch(() => {})
    loadReports()
    getReportConfig().then((d) => {
      const cfg = d as unknown as { output_dir: string }
      setOutputDir(cfg.output_dir)
    }).catch(() => {})
  }, [])

  // 轮询任务状态
  useEffect(() => {
    if (!taskId || taskStatus?.status === 'completed' || taskStatus?.status === 'failed') return
    const timer = setInterval(async () => {
      try {
        const res = await getTask(taskId)
        const t = res as unknown as TaskStatus
        setTaskStatus(t)
        if (t.status === 'completed' || t.status === 'failed') {
          setGenerating(false)
          if (t.status === 'completed') {
            message.success('报告生成完成！')
            loadReports()
          } else {
            message.error(t.error || '报告生成失败')
          }
        }
      } catch { /* ignore */ }
    }, 2000)
    return () => clearInterval(timer)
  }, [taskId, taskStatus?.status])

  const loadReports = useCallback(async () => {
    setLoadingReports(true)
    try {
      const res = await listReports({
        scenario: filterScenario,
        factor_name: filterFactor || undefined,
      })
      setReports(res as unknown as ReportInfo[])
    } catch { /* ignore */ }
    finally { setLoadingReports(false) }
  }, [filterScenario, filterFactor])

  useEffect(() => {
    loadReports()
  }, [loadReports])

  const handleGenerate = async () => {
    if (factorRefs.length === 0) {
      message.error('请至少选择一个被测因子')
      return
    }
    if (!dateRange) {
      message.error('请选择日期范围')
      return
    }
    if (outputFormats.length === 0) {
      message.error('请至少选择一个输出格式')
      return
    }

    const req: ReportGenerateRequest = {
      scenario,
      name: reportName || `${scenario} 报告`,
      factor_refs: factorRefs,
      price_ref: priceRef || null,
      mask_ref: maskRef || null,
      cat_data_ref: catDataRef || null,
      weight_ref: weightRef || null,
      start_date: dateRange[0],
      end_date: dateRange[1],
      output_formats: outputFormats,
      modules: modules as any,
    }

    setGenerating(true)
    try {
      const res = await generateReport(req)
      setTaskId((res as unknown as { task_id: string }).task_id)
      setTaskStatus(null)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '提交失败')
      setGenerating(false)
    }
  }

  const handlePreview = async (report: ReportInfo) => {
    setPreviewReport(report)
    setPreviewVisible(true)
    setPreviewContent(null)
    setPreviewLoading(true)
    try {
      const fmt = report.formats.includes('html') ? 'html' : report.formats[0]
      const res = await getReportContent(report.id, fmt)
      setPreviewContent(res as unknown as Record<string, string>)
    } catch {
      message.error('加载报告内容失败')
    }
    finally { setPreviewLoading(false) }
  }

  const handleDownload = (report: ReportInfo) => {
    // 通过获取内容再触发下载
    const fmt = report.formats.includes('html') ? 'html' : report.formats[0]
    getReportContent(report.id, fmt).then((res) => {
      const ext = fmt === 'markdown' ? 'md' : 'html'
      Object.entries(res as unknown as Record<string, string>).forEach(([name, content]) => {
        const blob = new Blob([content], { type: 'text/plain' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${name}.${ext}`
        a.click()
        URL.revokeObjectURL(url)
      })
    }).catch(() => message.error('下载失败'))
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteReport(id)
      message.success('删除成功')
      loadReports()
    } catch { message.error('删除失败') }
  }

  const handleRegister = async (report: ReportInfo) => {
    setRegistering(report.id)
    try {
      await registerReport(report.id, {})
      message.success('注册成功')
      loadReports()
    } catch { message.error('注册失败') }
    finally { setRegistering(null) }
  }

  const currentScenario = scenarios.find((s) => s.key === scenario)

  const handleSaveDir = async () => {
    setSavingDir(true)
    try {
      await updateReportConfig(editDirValue)
      setOutputDir(editDirValue)
      setEditingDir(false)
      message.success('保存成功')
    } catch { message.error('保存失败') }
    finally { setSavingDir(false) }
  }

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      {/* 存储配置 */}
      <div style={{
        marginBottom: 16,
        padding: '8px 16px',
        background: '#fafafa',
        borderRadius: 8,
        display: 'flex',
        alignItems: 'center',
        gap: 12,
      }}>
        <span style={{ color: '#666', fontSize: 13 }}>报告存储目录:</span>
        {editingDir ? (
          <Space>
            <Input
              style={{ width: 400 }}
              value={editDirValue}
              onChange={(e) => setEditDirValue(e.target.value)}
              placeholder="输入目录路径"
            />
            <Button size="small" type="primary" loading={savingDir} onClick={handleSaveDir}>
              保存
            </Button>
            <Button size="small" onClick={() => setEditingDir(false)}>取消</Button>
          </Space>
        ) : (
          <Space>
            <code style={{ fontSize: 12, background: '#fff', padding: '2px 8px', borderRadius: 4 }}>
              {outputDir}
            </code>
            <Button
              size="small"
              type="link"
              onClick={() => { setEditDirValue(outputDir); setEditingDir(true) }}
            >
              修改
            </Button>
          </Space>
        )}
      </div>

      {/* 报告生成 */}
      <Card
        title={<span><FileTextOutlined /> 生成新报告</span>}
        style={{ marginBottom: 24 }}
      >
        <Form layout="vertical">
          <Form.Item label="报告场景">
            <Select
              value={scenario}
              onChange={setScenario}
              style={{ width: 240 }}
              options={scenarios.map((s) => ({ value: s.key, label: s.name }))}
            />
            {currentScenario && (
              <div style={{ color: '#999', fontSize: 12, marginTop: 4 }}>
                {currentScenario.description}
              </div>
            )}
          </Form.Item>

          <Form.Item label="报告名称">
            <Input
              placeholder="可选，留空使用默认名称"
              value={reportName}
              onChange={(e) => setReportName(e.target.value)}
              style={{ width: 320 }}
            />
          </Form.Item>

          <Form.Item label="被测因子（必选）" required>
            <MultiFactorPicker value={factorRefs} onChange={setFactorRefs} />
          </Form.Item>

          <Form.Item label="价格因子（可选，用于计算收益率）">
            <FactorRefSelector
              value={priceRef}
              onChange={setPriceRef}
              allowClear
            />
          </Form.Item>

          <Collapse
            ghost
            size="small"
            items={[{
              key: 'optional',
              label: '其他可选因子 (Mask / 行业 / 权重)',
              children: (
                <>
                  <Form.Item label="Mask 因子">
                    <FactorRefSelector value={maskRef} onChange={setMaskRef} allowClear />
                  </Form.Item>
                  <Form.Item label="行业/分类因子">
                    <FactorRefSelector value={catDataRef} onChange={setCatDataRef} allowClear />
                  </Form.Item>
                  <Form.Item label="权重因子">
                    <FactorRefSelector value={weightRef} onChange={setWeightRef} allowClear />
                  </Form.Item>
                </>
              ),
            }]}
          />

          <Form.Item label="日期范围" required>
            <RangePicker
              value={dateRange ? [dayjs(dateRange[0]), dayjs(dateRange[1])] : null}
              onChange={(dates) => {
                if (dates && dates[0] && dates[1]) {
                  setDateRange([dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')])
                } else {
                  setDateRange(null)
                }
              }}
            />
          </Form.Item>

          <Form.Item label="输出格式">
            <Checkbox.Group
              value={outputFormats}
              onChange={(vals) => setOutputFormats(vals as string[])}
              options={[
                { label: 'HTML', value: 'html' },
                { label: 'Markdown', value: 'markdown' },
              ]}
            />
          </Form.Item>

          {currentScenario && currentScenario.module_options.length > 0 && (
            <Form.Item label="分析模块">
              <Space wrap>
                {currentScenario.module_options.map((mod) => (
                  <Checkbox
                    key={mod}
                    checked={modules[mod] !== false}
                    onChange={(e) => setModules({ ...modules, [mod]: e.target.checked })}
                  >
                    {{
                      ic: 'IC 分析',
                      ic_decay: 'IC 衰减',
                      quantile_portfolio: '分位数组合',
                      factor_turnover: '因子换手率',
                    }[mod] || mod}
                  </Checkbox>
                ))}
              </Space>
            </Form.Item>
          )}

          <Form.Item>
            <Space>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={handleGenerate}
                loading={generating}
              >
                生成报告
              </Button>
              {taskId && taskStatus && (
                <div style={{ minWidth: 300 }}>
                  <Progress
                    percent={Math.round(taskStatus.progress)}
                    status={
                      taskStatus.status === 'failed' ? 'exception'
                      : taskStatus.status === 'completed' ? 'success'
                      : 'active'
                    }
                    format={() => `${Math.round(taskStatus.progress)}%`}
                  />
                  <span style={{ fontSize: 12, color: '#666' }}>
                    {taskStatus.progress_message}
                  </span>
                </div>
              )}
            </Space>
          </Form.Item>
        </Form>
      </Card>

      {/* 报告列表 */}
      <Card
        title={<span><FileTextOutlined /> 已生成报告 ({reports.length})</span>}
        extra={
          <Space>
            <Select
              placeholder="场景筛选"
              allowClear
              style={{ width: 150 }}
              value={filterScenario}
              onChange={setFilterScenario}
              options={scenarios.map((s) => ({ value: s.key, label: s.name }))}
            />
            <Input
              placeholder="因子名筛选"
              allowClear
              style={{ width: 150 }}
              value={filterFactor}
              onChange={(e) => setFilterFactor(e.target.value)}
            />
            <Button icon={<ReloadOutlined />} onClick={loadReports}>刷新</Button>
          </Space>
        }
      >
        <Table
          dataSource={reports}
          rowKey="id"
          loading={loadingReports}
          pagination={{ pageSize: 10 }}
          scroll={{ x: 'max-content' }}
          locale={{ emptyText: <Empty description="暂无报告，请先生成" /> }}
          columns={[
            {
              title: '名称',
              dataIndex: 'name',
              key: 'name',
              width: 160,
              ellipsis: true,
            },
            {
              title: '场景',
              dataIndex: 'scenario',
              key: 'scenario',
              width: 100,
              render: (s: string) => (
                <Tag>{scenarios.find((sc) => sc.key === s)?.name || s}</Tag>
              ),
            },
            {
              title: '因子',
              dataIndex: 'factor_names',
              key: 'factors',
              width: 160,
              render: (names: string[]) => (
                <Space size={4} wrap>
                  {names.map((n) => <Tag key={n} color="blue">{n}</Tag>)}
                </Space>
              ),
            },
            {
              title: '格式',
              dataIndex: 'formats',
              key: 'formats',
              width: 100,
              render: (fmts: string[]) => (
                <Space>
                  {fmts.map((f) => <Tag key={f}>{f.toUpperCase()}</Tag>)}
                </Space>
              ),
            },
            {
              title: '状态',
              key: 'registered',
              width: 80,
              render: (_: any, r: ReportInfo) => (
                r.registered ? <Tag color="green">已注册</Tag> : <Tag>未注册</Tag>
              ),
            },
            {
              title: '日期范围',
              key: 'date',
              width: 200,
              render: (_: any, r: ReportInfo) => (
                <span style={{ fontSize: 12 }}>
                  {r.start_date} ~ {r.end_date}
                </span>
              ),
            },
            {
              title: '创建时间',
              dataIndex: 'created_at',
              key: 'created_at',
              width: 170,
              render: (t: string) => t?.slice(0, 19).replace('T', ' '),
            },
            {
              title: '操作',
              key: 'actions',
              width: 240,
              render: (_: any, r: ReportInfo) => (
                <Space size="small">
                  <Button
                    size="small"
                    type="link"
                    icon={<EyeOutlined />}
                    onClick={() => handlePreview(r)}
                  >
                    预览
                  </Button>
                  <Button
                    size="small"
                    type="link"
                    icon={<DownloadOutlined />}
                    onClick={() => handleDownload(r)}
                  >
                    下载
                  </Button>
                  <Button
                    size="small"
                    type="link"
                    icon={<LinkOutlined />}
                    loading={registering === r.id}
                    disabled={r.registered}
                    onClick={() => handleRegister(r)}
                  >
                    注册
                  </Button>
                  <Popconfirm
                    title="确认删除此报告？"
                    onConfirm={() => handleDelete(r.id)}
                  >
                    <Button
                      size="small"
                      type="link"
                      danger
                      icon={<DeleteOutlined />}
                    >
                      删除
                    </Button>
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      {/* 预览弹窗 */}
      <Modal
        title={previewReport ? `预览: ${previewReport.name}` : '预览报告'}
        open={previewVisible}
        onCancel={() => { setPreviewVisible(false); setPreviewContent(null) }}
        width="90%"
        style={{ top: 20 }}
        footer={null}
        destroyOnClose
      >
        {previewLoading ? (
          <div style={{ textAlign: 'center', padding: 48 }}>
            <Spin size="large" />
          </div>
        ) : previewContent ? (
          <Tabs
            items={Object.entries(previewContent).map(([name, content]) => ({
              key: name,
              label: name,
              children: (
                <div
                  style={{
                    border: '1px solid #f0f0f0',
                    borderRadius: 8,
                    padding: 16,
                    maxHeight: '70vh',
                    overflow: 'auto',
                  }}
                >
                  {previewReport?.formats.includes('html') && !name.endsWith('.md') ? (
                    <iframe
                      srcDoc={content}
                      style={{ width: '100%', height: '65vh', border: 'none' }}
                      title={name}
                    />
                  ) : (
                    <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: 13 }}>
                      {content}
                    </pre>
                  )}
                </div>
              ),
            }))}
          />
        ) : (
          <Empty description="无报告内容" />
        )}
      </Modal>
    </div>
  )
}
