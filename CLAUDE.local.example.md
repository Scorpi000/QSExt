# 约定

* 生成文档、注释、skill等时使用中文
* 各个模块的文档放置在 docs 目录下
* Python 文档字符串使用 Google 风格
* 测试脚本放到项目的 tests 目录下，功能性脚本放到项目的 scripts 目录下
* 编写功能脚本时，一定要将脚本的实现逻辑和使用方法以模块文档字符串的形式写到脚本的开始位置
* 本项目是 QuantStudio 项目的扩展项目，要基于其基本框架实现相关功能。

# 运行环境

* Python：使用 conda 的 QS312 环境，位置是：D:\miniforge\envs\QS312
* QuantStudio: 项目地址：D:\Project\QuantStudio

# 数据库

## 聚源数据库

* 数据库类型：postgresql
* 数据库：JYDB
* 数据库的连接信息可以在文件 "~/QuantStudioConfig/JYDBConfig.json" 中
* 数据库内容：股票、基金等证券的基本信息、行情、财务等金融数据
* 表的说明信息使用相关工具检索

## 图数据库

* 数据库类型：neo4j
* 数据库：neo4j
* 数据库的连接信息可以在文件 "~/QuantStudioConfig/Neo4jDBConfig.json" 中
* 数据库内容：用于存储因子、算子等信息