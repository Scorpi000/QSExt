import sys
sys.path.insert(0, r'D:\HST\QSExt')
from QSExt.QSRegistry.QSGraphDB import QSGraphDB

gdb = QSGraphDB()
gdb.connect()

# 查询节点统计
print('=== 节点统计 ===')
labels = ['因子', '报告', '因子表', '算子', '回测']
for label in labels:
    query = "MATCH (n) WHERE $label IN labels(n) RETURN count(n) AS cnt"
    results = gdb._runCypher(query, {"label": label})
    print(f'{label}: {results[0]["cnt"]}')

# 查询关系统计
print()
print('=== 关系统计 ===')
results = gdb._runCypher('MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS cnt')
for r in results:
    print(f'{r["t"]}: {r["cnt"]}')

# 查询因子节点
print()
print('=== 因子节点示例 ===')
results = gdb._runCypher('MATCH (f) WHERE "因子" IN labels(f) RETURN f.Name AS name, f.QSID AS qsid LIMIT 5')
for r in results:
    qsid = r.get("qsid", "?") or "?"
    print(f'  {r.get("name", "?")}  QSID={qsid[:20]}')

# 查询报告-因子关系
print()
print('=== 报告-因子关联 ===')
results = gdb._runCypher(
    'MATCH (f)-[rel]->(r) '
    'WHERE "因子" IN labels(f) AND "报告" IN labels(r) '
    'RETURN f.Name AS factor, r.Name AS report, r.ReportID AS rid LIMIT 5'
)
for r in results:
    print(f'  {r.get("factor", "?")} -> {r.get("report", "?")}')
if not results:
    print('  (无关联)')

# 查询报告节点
print()
print('=== 报告节点 ===')
results = gdb._runCypher(
    'MATCH (r) WHERE "报告" IN labels(r) '
    'RETURN r.Name AS name, r.ReportID AS rid, r.FactorNames AS fns LIMIT 5'
)
for r in results:
    print(f'  {r.get("name", "?")}  FactorNames={r.get("fns", "?")}')
if not results:
    print('  (无)')
