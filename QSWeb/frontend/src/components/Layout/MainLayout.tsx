/**
 * MainLayout - 全局布局
 *
 * 左侧导航菜单 + 顶部标题栏 + 内容区 + 右侧全局面板（因子池 | 全局配置，hover 召唤）。
 * 全局 AI 入口：FAB 悬浮按钮 + Ctrl+K 快捷键。
 */

import { useState, useEffect } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, theme, Button, Modal, Input, Select, message, Space } from 'antd'
import {
  DatabaseOutlined,
  ExperimentOutlined,
  LineChartOutlined,
  SafetyOutlined,
  PieChartOutlined,
  FileTextOutlined,
  UnorderedListOutlined,
  SaveOutlined,
  FolderOpenOutlined,
  RobotOutlined,
  GoldOutlined,
  SettingOutlined,
  PushpinOutlined,
  CodeOutlined,
} from '@ant-design/icons'
import FactorPoolPanel from '../FactorPoolPanel'
import FactorDiscover from '../FactorDiscover'
import GlobalConfigPanel from '../GlobalConfigPanel'
import AiChatDrawer from '../AiChatDrawer'
import { useFactorPoolStore } from '../../stores/factorPoolStore'
import { useGlobalConfigStore } from '../../stores/globalConfigStore'
import { savePool, loadPool, listPools, deletePool } from '../../services/factorPool'

const { Header, Sider, Content } = Layout

const menuItems = [
  { key: '/data', icon: <DatabaseOutlined />, label: '数据管理' },
  { key: '/risk', icon: <SafetyOutlined />, label: '风险管理' },
  { key: '/factor', icon: <ExperimentOutlined />, label: '因子工作台' },
  { key: '/backtest', icon: <LineChartOutlined />, label: '回测工作台' },
  { key: '/portfolio', icon: <PieChartOutlined />, label: '组合优化' },
  { key: '/report', icon: <FileTextOutlined />, label: '报告中心' },
  { key: '/ai', icon: <RobotOutlined />, label: 'AI 工作台' },
  { key: '/mining', icon: <GoldOutlined />, label: '因子挖掘' },
  { key: '/strategy', icon: <CodeOutlined />, label: '策略工作台' },
]

const POOL_COLLAPSED_WIDTH = 36
const POOL_EXPANDED_WIDTH = 360

function MainLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { token: { colorBgContainer, borderRadiusLG } } = theme.useToken()

  // 右侧面板状态
  const [poolExpanded, setPoolExpanded] = useState(false)
  const [poolPinned, setPoolPinned] = useState(false)
  const [rightPanelTab, setRightPanelTab] = useState<'pool' | 'config'>('pool')
  const [discoverOpen, setDiscoverOpen] = useState(false)

  // 启动时加载全局配置
  useEffect(() => {
    useGlobalConfigStore.getState().fetchConfig()
  }, [])

  // AI Drawer 状态
  const [aiDrawerOpen, setAiDrawerOpen] = useState(false)

  // Ctrl+K / Cmd+K 快捷键
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        // 输入框内不触发
        const tag = (e.target as HTMLElement)?.tagName?.toLowerCase()
        if (tag === 'input' || tag === 'textarea') return
        e.preventDefault()
        setAiDrawerOpen((prev) => !prev)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const handleMenuClick = ({ key }: { key: string }) => {
    navigate(key)
  }

  const poolWidth = (poolExpanded || poolPinned) ? POOL_EXPANDED_WIDTH : POOL_COLLAPSED_WIDTH

  // 因子池持久化
  const poolItems = useFactorPoolStore((s) => s.items)
  const setPoolItems = useFactorPoolStore((s) => s.setItems)
  const [saveModalOpen, setSaveModalOpen] = useState(false)
  const [poolName, setPoolName] = useState('')
  const [savedPools, setSavedPools] = useState<Array<{ Name: string; FactorCount: number }>>([])
  const [saving, setSaving] = useState(false)
  const [loadingPool, setLoadingPool] = useState(false)

  const handleSavePool = async () => {
    if (!poolName.trim()) { message.warning('请输入池子名称'); return }
    if (poolItems.length === 0) { message.warning('因子池为空，请先添加因子'); return }
    setSaving(true)
    try {
      await savePool(poolName.trim(), poolItems)
      message.success(`已保存: ${poolName.trim()}`)
      setSaveModalOpen(false)
      setPoolName('')
    } catch { message.error('保存失败') }
    finally { setSaving(false) }
  }

  const handleLoadPools = async () => {
    setLoadingPool(true)
    try {
      const data = await listPools() as unknown as Array<{ Name: string; FactorCount: number }>
      setSavedPools(data || [])
    } catch { setSavedPools([]) }
    finally { setLoadingPool(false) }
  }

  const handleLoadPool = async (name: string) => {
    try {
      const data = await loadPool(name) as unknown as { name: string; items: any[] }
      setPoolItems(data.items || [])
      message.success(`已加载: ${name} (${data.items?.length || 0} 个因子)`)
    } catch { message.error('加载失败') }
  }

  const handleDeletePool = async (name: string) => {
    try {
      await deletePool(name)
      message.success(`已删除: ${name}`)
      handleLoadPools()
    } catch { message.error('删除失败') }
  }

  const handlePoolMouseEnter = () => {
    if (!poolPinned) setPoolExpanded(true)
  }
  const handlePoolMouseLeave = () => {
    if (!poolPinned) setPoolExpanded(false)
  }

  return (
    <Layout style={{ height: '100vh' }}>
      <Sider
        collapsible collapsed={collapsed} onCollapse={setCollapsed}
        theme="light"
        style={{ overflow: 'auto', height: '100vh', position: 'fixed', left: 0, top: 0, bottom: 0, zIndex: 100 }}
      >
        <div style={{ height: 64, display: 'flex', alignItems: 'center', justifyContent: 'center', borderBottom: '1px solid #f0f0f0', padding: '8px' }}>
          {collapsed ? (
            <img src="/QSIcon.jpg" alt="QS" style={{ width: 64, height: 64, borderRadius: 4 }} />
          ) : (
            <img src="/QSLogo.jpg" alt="QSWeb" style={{ maxWidth: '100%', maxHeight: 96, objectFit: 'contain' }} />
          )}
        </div>
        <Menu mode="inline" selectedKeys={[location.pathname]} items={menuItems} onClick={handleMenuClick} style={{ borderRight: 0 }} />
      </Sider>

      <Layout style={{
        marginLeft: collapsed ? 80 : 200,
        marginRight: POOL_COLLAPSED_WIDTH,
        transition: 'all 0.2s',
      }}>
        <Header style={{
          padding: '0 24px', background: colorBgContainer,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          borderBottom: '1px solid #f0f0f0',
        }}>
          <h2 style={{ margin: 0, fontSize: 18 }}>
            {menuItems.find((item) => item.key === location.pathname)?.label || 'QSWeb'}
          </h2>
          <div style={{ color: '#999' }}>QuantStudio Web GUI v0.1.0</div>
        </Header>
        <Content style={{
          margin: 24, padding: 24, background: colorBgContainer,
          borderRadius: borderRadiusLG, overflow: 'auto',
        }}>
          <Outlet />
        </Content>
      </Layout>

      {/* 右侧全局面板 — hover 召唤（因子池 | 全局配置） */}
      <div
        onMouseEnter={handlePoolMouseEnter}
        onMouseLeave={handlePoolMouseLeave}
        style={{
          position: 'fixed',
          right: 0,
          top: 0,
          bottom: 0,
          width: poolWidth,
          zIndex: 99,
          background: poolExpanded || poolPinned ? colorBgContainer : '#fafafa',
          borderLeft: '1px solid #e8e8e8',
          boxShadow: (poolExpanded || poolPinned) ? '-4px 0 12px rgba(0,0,0,0.08)' : 'none',
          transition: 'width 0.2s, box-shadow 0.2s',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* 折叠态：竖向标签 */}
        {!poolExpanded && !poolPinned && (
          <div style={{
            height: '100%',
            display: 'flex',
            flexDirection: 'column',
            cursor: 'default',
            userSelect: 'none',
          }}>
            <div
              onClick={() => { setRightPanelTab('pool'); setPoolExpanded(true) }}
              style={{
                flex: 1,
                writingMode: 'vertical-rl',
                textOrientation: 'mixed',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#999',
                fontSize: 13,
                letterSpacing: 4,
                borderBottom: '1px solid #f0f0f0',
              }}
            >
              <UnorderedListOutlined style={{ marginBottom: 8, fontSize: 16 }} />
              因子池
            </div>
            <div
              onClick={() => { setRightPanelTab('config'); setPoolExpanded(true) }}
              style={{
                flex: 1,
                writingMode: 'vertical-rl',
                textOrientation: 'mixed',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#999',
                fontSize: 13,
                letterSpacing: 4,
              }}
            >
              <SettingOutlined style={{ marginBottom: 8, fontSize: 16 }} />
              配置
            </div>
          </div>
        )}

        {/* 展开态：Tab 切换面板 */}
        {(poolExpanded || poolPinned) && (
          <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
            <div style={{
              padding: '12px 16px',
              borderBottom: '1px solid #f0f0f0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexShrink: 0,
              flexWrap: 'wrap',
              gap: 4,
            }}>
              <Space size={0}>
                <Button
                  type={rightPanelTab === 'pool' ? 'primary' : 'text'}
                  size="small"
                  onClick={() => setRightPanelTab('pool')}
                >
                  因子池
                </Button>
                <Button
                  type={rightPanelTab === 'config' ? 'primary' : 'text'}
                  size="small"
                  icon={<SettingOutlined />}
                  onClick={() => setRightPanelTab('config')}
                >
                  配置
                </Button>
              </Space>
              <Space size={4}>
                {rightPanelTab === 'pool' && (
                  <>
                    <Button type="text" size="small" icon={<SaveOutlined />}
                      onClick={() => setSaveModalOpen(true)} title="保存到图库" />
                    <Select
                      size="small"
                      style={{ width: 24 }}
                      value={undefined}
                      placeholder={<FolderOpenOutlined />}
                      onDropdownVisibleChange={(open) => { if (open) handleLoadPools() }}
                      onChange={handleLoadPool}
                      loading={loadingPool}
                      dropdownStyle={{ minWidth: 200 }}
                      options={savedPools.map((p) => ({
                        value: p.Name,
                        label: (
                          <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                            <span>{p.Name} ({p.FactorCount} 因子)</span>
                            <Button type="link" size="small" danger
                              onClick={(e) => { e.stopPropagation(); handleDeletePool(p.Name) }}>删除</Button>
                          </Space>
                        ),
                      }))}
                      popupMatchSelectWidth={false}
                    />
                  </>
                )}
                <Button type="text" size="small"
                  style={{ color: poolPinned ? '#1677ff' : '#999' }}
                  onClick={() => setPoolPinned(!poolPinned)}
                  title={poolPinned ? '取消固定' : '固定面板'}>
                  <PushpinOutlined />
                </Button>
              </Space>
            </div>
            <div style={{ flex: 1, overflow: 'auto', padding: 12 }}>
              {rightPanelTab === 'pool' ? (
                <FactorPoolPanel compact onAddClick={() => setDiscoverOpen(true)} />
              ) : (
                <GlobalConfigPanel />
              )}
            </div>
          </div>
        )}
      </div>

      {/* 因子发现 Drawer */}
      <FactorDiscover open={discoverOpen} onClose={() => setDiscoverOpen(false)} />

      {/* 保存因子池对话框 */}
      <Modal
        title="保存因子池到图库"
        open={saveModalOpen}
        onOk={handleSavePool}
        onCancel={() => { setSaveModalOpen(false); setPoolName('') }}
        okText="保存"
        confirmLoading={saving}
        cancelText="取消"
      >
        <div style={{ marginTop: 16 }}>
          <div style={{ marginBottom: 8, fontSize: 13, color: '#666' }}>
            当前池中有 {poolItems.length} 个因子
          </div>
          <Input
            placeholder="输入池子名称"
            value={poolName}
            onChange={(e) => setPoolName(e.target.value)}
            onPressEnter={handleSavePool}
          />
        </div>
      </Modal>

      {/* 全局 AI 助手 Drawer */}
      <AiChatDrawer
        open={aiDrawerOpen}
        onClose={() => setAiDrawerOpen(false)}
      />

      {/* FAB 悬浮按钮 */}
      <Button
        type="primary"
        shape="circle"
        size="large"
        icon={<RobotOutlined />}
        onClick={() => setAiDrawerOpen((prev) => !prev)}
        title="AI 助手 (Ctrl+K)"
        style={{
          position: 'fixed',
          bottom: 24,
          right: 24,
          zIndex: 98,
          boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
        }}
      />
    </Layout>
  )
}

export default MainLayout
