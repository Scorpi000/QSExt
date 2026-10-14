"""运行作用域资源解析；语义描述与活动句柄分离。"""
from typing import Protocol

from .Protocol import ResourceDescriptor

RESOURCE_RESOLVER_KEY = "qsext.graph.resource_resolver"


class ResourceResolver(Protocol):
    """由应用层实现的资源服务，不负责权限和任务管理。"""

    def resolve(self, resource: ResourceDescriptor):
        """在执行阶段返回资源句柄或数据。"""
        ...


class ResourceCatalog:
    """仅包含语义描述的内存目录，读取目录不会解析连接。"""

    def __init__(self, resources=()):
        self._resources = {item.id: item.model_copy(deep=True) for item in resources}

    def describe(self, id_):
        """返回语义描述副本；未知资源不隐式创建。"""
        return self._resources[id_].model_copy(deep=True)


class MappingResourceResolver:
    """复用由调用方准备的句柄，不管理其连接生命周期。"""

    def __init__(self, handles):
        self.handles = dict(handles)

    def resolve(self, resource):
        """通过逻辑资源名称获取已准备句柄。"""
        return self.handles[resource.id]


class DBPoolResourceResolver:
    """复用 RuntimeConfig.DBPool；只连接所需资源，不创建连接池。"""

    def __init__(self, pool, names):
        self.pool, self.names = pool, dict(names)

    def resolve(self, resource):
        """在执行准备阶段按显式映射连接因子库。"""
        return self.pool.connect_one(self.names[resource.id])


class RegistryResourceResolver:
    """复用 QSRegistry 读取已登记资源；数据库由调用方连接。"""

    def __init__(self, registry, qsids):
        self.registry, self.qsids = registry, dict(qsids)

    def resolve(self, resource):
        """将公开资源名称映射为受信任的注册中心 ID。"""
        qsid = self.qsids[resource.id]
        if resource.kind == "registered_factor":
            return self.registry.reconstructFactor(qsid)
        if resource.kind == "factor_database":
            return self.registry.reconstructFactorDB(qsid)
        raise ValueError(f"注册中心不支持该资源类别: {resource.kind}")


def resolve_resource(context, resource):
    """从当前运行上下文取得注入的服务，不使用全局连接。"""
    resolver = context.Resources.get(RESOURCE_RESOLVER_KEY)
    if resolver is None:
        raise ValueError("运行上下文尚未注入图资源解析器")
    return resolver.resolve(resource)
