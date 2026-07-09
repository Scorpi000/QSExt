import { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, theme } from 'antd'
import {
  DatabaseOutlined,
  ExperimentOutlined,
  LineChartOutlined,
  SafetyOutlined,
  PieChartOutlined,
  FileTextOutlined,
} from '@ant-design/icons'

const { Header, Sider, Content } = Layout

const menuItems = [
  {
    key: '/data',
    icon: <DatabaseOutlined />,
    label: '数据管理',
  },
  {
    key: '/factor',
    icon: <ExperimentOutlined />,
    label: '因子工作台',
    disabled: true,
  },
  {
    key: '/backtest',
    icon: <LineChartOutlined />,
    label: '回测工作台',
    disabled: true,
  },
  {
    key: '/risk',
    icon: <SafetyOutlined />,
    label: '风险管理',
    disabled: true,
  },
  {
    key: '/portfolio',
    icon: <PieChartOutlined />,
    label: '组合优化',
    disabled: true,
  },
  {
    key: '/report',
    icon: <FileTextOutlined />,
    label: '报告中心',
    disabled: true,
  },
]

function MainLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken()

  const handleMenuClick = ({ key }: { key: string }) => {
    navigate(key)
  }

  return (
    <Layout style={{ height: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        theme="light"
        style={{
          overflow: 'auto',
          height: '100vh',
          position: 'fixed',
          left: 0,
          top: 0,
          bottom: 0,
        }}
      >
        <div
          style={{
            height: 64,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderBottom: '1px solid #f0f0f0',
          }}
        >
          <h1 style={{ margin: 0, fontSize: collapsed ? 16 : 20 }}>
            {collapsed ? 'QSW' : 'QSWeb'}
          </h1>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={handleMenuClick}
          style={{ borderRight: 0 }}
        />
      </Sider>
      <Layout style={{ marginLeft: collapsed ? 80 : 200, transition: 'all 0.2s' }}>
        <Header
          style={{
            padding: '0 24px',
            background: colorBgContainer,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid #f0f0f0',
          }}
        >
          <h2 style={{ margin: 0, fontSize: 18 }}>
            {menuItems.find((item) => item.key === location.pathname)?.label || 'QSWeb'}
          </h2>
          <div style={{ color: '#999' }}>QuantStudio Web GUI v0.1.0</div>
        </Header>
        <Content
          style={{
            margin: 24,
            padding: 24,
            background: colorBgContainer,
            borderRadius: borderRadiusLG,
            overflow: 'auto',
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}

export default MainLayout
