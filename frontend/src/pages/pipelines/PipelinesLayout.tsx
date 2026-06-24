import { NavLink, Outlet, useLocation} from 'react-router-dom'

export default function PipelinesLayout() {
  const location = useLocation()

  // Builder 页面使用全屏布局，不显示标题
  const isBuilder = /^\/pipelines\/(?!connections|datasets|transforms|curated$)[a-f0-9-]+$/i.test(location.pathname)

  if (isBuilder) {
    return <Outlet />
  }

  const navItems = [
    { to: '/pipelines', label: 'Pipeline 列表', end: true },
    { to: '/pipelines/connections', label: '连接器' },
    { to: '/pipelines/datasets', label: '数据集' },
    { to: '/pipelines/transforms', label: 'Transforms' },
    { to: '/pipelines/curated', label: 'Curated 数据集' },
  ]

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold mb-3">数据管道</h1>
        <div className="flex flex-wrap gap-2">
          {navItems.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `px-3 py-1.5 rounded-lg border text-sm transition-colors ${isActive
                  ? 'bg-black text-white border-black'
                  : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300 hover:text-black'}`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </div>
      </div>
      <Outlet />
    </div>
  )
}
