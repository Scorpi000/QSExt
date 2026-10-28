"""启动独立远程因子库服务。

实现逻辑：读取指定 settings.py 中的 FACTOR_DATABASES 与 FACTOR_SERVICE，
创建单 HTTP worker 应用，每个真实资源由专用线程顺序访问；计算图留在客户端。

使用方法：先设置配置引用的服务令牌与数据根目录环境变量，再执行
``python scripts/run_factor_service.py --settings path/to/settings.py``。
生产环境由反向代理提供 HTTPS，不使用 Uvicorn 多 worker 或热重载。
"""

import argparse


def main():
    """解析配置并启动单进程 HTTP 服务。"""
    parser = argparse.ArgumentParser(description="启动 QuantStudio 远程因子库服务")
    parser.add_argument("--settings", required=True, help="服务 settings.py 路径")
    options = parser.parse_args()
    import uvicorn
    from QSExt.FactorService.config import load_settings
    from QSExt.FactorService.server import create_app

    definitions, config = load_settings(options.settings)
    uvicorn.run(create_app(definitions, config), host=config.Host, port=config.Port, workers=1)


if __name__ == "__main__":
    main()
