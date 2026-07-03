# QSRegistry — Cypher 查询模式

> 返回 [总览](QSGraphDB设计.md)

## 存储操作

**幂等 upsert 因子节点：**
```cypher
MERGE (f:`因子` {QSID: $qsid})
ON CREATE SET f += $props, f.CreatedAt = datetime()
ON MATCH SET f += $props, f.UpdatedAt = datetime()
```

**存储算子并建立关系：**
```cypher
MERGE (o:`算子` {QSID: $op_qsid})
ON CREATE SET o += $op_props, o.CreatedAt = datetime()
ON MATCH SET o += $op_props, o.UpdatedAt = datetime()
WITH o
MATCH (f:`因子` {QSID: $factor_qsid})
MERGE (f)-[:`使用算子`]->(o)
```

**创建依赖关系：**
```cypher
MATCH (source:`因子` {QSID: $source_qsid})
MATCH (target:`因子` {QSID: $target_qsid})
MERGE (source)-[r:`依赖`]->(target)
SET r.order = $order
```

**创建标签：**
```cypher
MERGE (t:`标签` {Name: $tag_name})
WITH t
MATCH (f:`因子` {QSID: $factor_qsid})
MERGE (f)-[:`打标签`]->(t)
```

## 检索查询

**按名称模糊搜索：**
```cypher
MATCH (f:`因子`)
WHERE f.Name CONTAINS $name
RETURN f ORDER BY f.Name LIMIT $limit
```

**按算子类型搜索：**
```cypher
MATCH (f:`因子`)
WHERE f.OperatorType = $op_type
RETURN f ORDER BY f.Name LIMIT $limit
```

**按标签搜索：**
```cypher
MATCH (f:`因子`)-[:`打标签`]->(t:`标签` {Name: $tag_name})
RETURN f ORDER BY f.Name LIMIT $limit
```

**多条件组合搜索：**
```cypher
MATCH (f:`因子`)
WHERE ($name IS NULL OR f.Name CONTAINS $name)
  AND ($op_type IS NULL OR f.OperatorType = $op_type)
  AND ($op_name IS NULL OR f.OperatorName = $op_name)
  AND ($factor_class IS NULL OR f.FactorClass = $factor_class)
OPTIONAL MATCH (f)-[:`打标签`]->(t:`标签`)
WITH f, collect(t.Name) AS tags
WHERE $tag IS NULL OR $tag IN tags
RETURN f, tags ORDER BY f.Name LIMIT $limit
```

## 图遍历查询

**获取完整依赖 DAG（向下）：**
```cypher
MATCH path = (root:`因子` {QSID: $qsid})-[:`依赖`*]->(leaf:`因子`)
UNWIND nodes(path) AS n
WITH DISTINCT n
RETURN n
```

**获取有序直接描述子：**
```cypher
MATCH (f:`因子` {QSID: $qsid})-[r:`依赖`]->(d:`因子`)
RETURN d ORDER BY r.order
```

**获取所有下游依赖（传递闭包）：**
```cypher
MATCH (dependent:`因子`)-[:`依赖`*]->(target:`因子` {QSID: $qsid})
RETURN DISTINCT dependent
```

## 分析查询

**影响范围分析：**
```cypher
MATCH (impacted:`因子`)-[:`依赖`*1..]->(changed:`因子` {QSID: $qsid})
RETURN impacted,
       length(shortestPath((impacted)-[:`依赖`*]->(changed))) AS depth
ORDER BY depth
```

**查找相似因子：**
```cypher
MATCH (f:`因子` {QSID: $qsid})-[:`使用算子`]->(o:`算子`)
MATCH (other:`因子`)-[:`使用算子`]->(o2:`算子`)
WHERE o2.OperatorType = o.OperatorType
  AND o2.Name = o.Name
  AND other.QSID <> $qsid
RETURN other, o2 LIMIT $limit
```

**查找孤立因子：**
```cypher
MATCH (f:`因子`)
WHERE NOT (f)<-[:`依赖`]-()
  AND NOT (f)-[:`属于因子表`]->(:`因子表`)
RETURN f
```

## 向量检索查询

**基于向量索引的近似最近邻搜索：**
```cypher
CALL db.index.vector.queryNodes('factor_embedding', $limit, $queryEmbedding)
YIELD node AS f, score
RETURN f {.Name, .QSID, .FactorClass, .OperatorType, .OperatorName, .DataType}, score
ORDER BY score DESC
```

余弦相似度得分范围 `[0, 1]`，1 表示最相似。Neo4j 5.x 原生支持，无需 APOC 插件。

## 回测查询

**存储回测节点（幂等 upsert）：**
```cypher
MERGE (b:`回测` {QSID: $qsid})
ON CREATE SET b += $props, b.CreatedAt = $now
ON MATCH SET b += $props
```

**建立回测 → 因子依赖关系：**
```cypher
UNWIND $factor_qsids AS f_qsid
MATCH (b:`回测` {QSID: $bt_qsid})
MATCH (f:`因子` {QSID: f_qsid})
MERGE (b)-[:`依赖`]->(f)
```

**建立回测 → 回测结果关系：**
```cypher
MERGE (r:`回测结果` {ResultID: $result_id})
ON CREATE SET r += $props, r.CreatedAt = $now
ON MATCH SET r += $props
WITH r
MATCH (b:`回测` {QSID: $bt_qsid})
MERGE (b)-[:`产生结果`]->(r)
```

**按名称搜索回测：**
```cypher
MATCH (b:`回测`)
WHERE b.Name CONTAINS $name
RETURN b ORDER BY b.Name LIMIT $limit
```

**按类别搜索回测：**
```cypher
MATCH (b:`回测`)
WHERE b.BacktestCategory = $category
RETURN b ORDER BY b.Name LIMIT $limit
```

**查找使用了某个因子的所有回测（核心查询）：**
```cypher
MATCH (b:`回测`)-[:`依赖`]->(f:`因子` {QSID: $factor_qsid})
RETURN DISTINCT b ORDER BY b.Name
```

**获取回测的所有结果：**
```cypher
MATCH (b:`回测` {QSID: $bt_qsid})-[:`产生结果`]->(r:`回测结果`)
RETURN r ORDER BY r.Key
```

**获取回测的依赖子图：**
```cypher
MATCH (b:`回测` {QSID: $qsid})-[:`依赖`]->(n)
WHERE n:`因子` OR n:`回测`
RETURN b, n
```

**反向追溯：因子被哪些回测使用：**
```cypher
MATCH (b:`回测`)-[:`依赖`]->(f:`因子` {QSID: $factor_qsid})
RETURN b ORDER BY b.Name
```

## 因子存储器查询

**存储因子存储器（幂等 upsert）：**
```cypher
MERGE (s:`因子存储器` {QSID: $qsid})
ON CREATE SET s += $props, s.CreatedAt = $now
ON MATCH SET s += $props
```

**建立存储器 → 因子依赖关系：**
```cypher
UNWIND $rels AS rel
MATCH (s:`因子存储器` {QSID: $storer_qsid})
MATCH (f:`因子` {QSID: rel.factor_qsid})
MERGE (s)-[:`依赖`]->(f)
```

**建立存储器 → 目标因子表关系（仅在因子表已注册时）：**
```cypher
MATCH (t:`因子表`)-[:`属于因子库`]->(d:`因子库` {Name: $fdb_name})
WHERE t.Name = $table_name
WITH t
MATCH (s:`因子存储器` {QSID: $storer_qsid})
MERGE (s)-[:`写入因子表`]->(t)
```

**建立因子 → 目标因子表关系（标记因子已被存入该表）：**
```cypher
UNWIND $rels AS rel
MATCH (f:`因子` {QSID: rel.factor_qsid})
MATCH (t:`因子表` {QSID: $ft_qsid})
MERGE (f)-[:`存入因子表`]->(t)
```

**按目标因子表搜索存储器：**
```cypher
MATCH (s:`因子存储器`)
WHERE s.TargetTable CONTAINS $table_name
RETURN s ORDER BY s.Name LIMIT $limit
```

**按目标因子库搜索存储器：**
```cypher
MATCH (s:`因子存储器`)
WHERE s.TargetFDBName CONTAINS $fdb_name
RETURN s ORDER BY s.Name LIMIT $limit
```

**查找依赖某个因子的所有存储器：**
```cypher
MATCH (s:`因子存储器`)-[:`依赖`]->(f:`因子` {QSID: $factor_qsid})
RETURN DISTINCT s ORDER BY s.Name
```

**查找写入同一目标表的所有存储器：**
```cypher
MATCH (s:`因子存储器` {TargetFDBName: $fdb_name, TargetTable: $table_name})
MATCH (s)-[:`依赖`]->(f:`因子`)
RETURN s, collect(f.Name) AS factors
```

**查找已存入某因子表的所有因子（通过 FactorStorer 建立的 `存入因子表` 关系）：**
```cypher
MATCH (f:`因子`)-[:`存入因子表`]->(t:`因子表`)-[:`属于因子库`]->(d:`因子库` {Name: $fdb_name})
WHERE t.Name = $table_name
RETURN f.Name, f.QSID, t.Name, d.Name
ORDER BY f.Name
```

**查找因子被哪些存储器持久化到了哪些表：**
```cypher
MATCH (s:`因子存储器`)-[:`依赖`]->(f:`因子` {QSID: $factor_qsid})
OPTIONAL MATCH (s)-[:`写入因子表`]->(t:`因子表`)
RETURN s.Name, s.TargetFDBName, t.Name
```
