"""图运行上下文在并行切分时隔离主进程的活动资源。"""
from QuantStudio.Factor.Factor import FactorContext


class GraphContext(FactorContext):
    """来源在准备阶段冻结数据，子进程只接收数据与计算节点。"""

    def split(self, n, **kwargs):
        """移除连接解析器及应用事件闭包，保留已准备的数据。"""
        return [self.model_copy(update={"Resources": {}, "EventHandler": None}) for _ in range(n)]
