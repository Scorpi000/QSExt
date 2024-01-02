# -*- coding: utf-8 -*-
"""因子图谱"""
from QSExt.Tools.Neo4jFun import writeFactorTable, checkFactorTableExistence, deleteFactorTable, deleteFactor, writeRelation2FDB, readFactorID

# 写入因子图谱
def writeFactorGraph(ndb, context, author_label="`人物`"):
    DependentSource = context.getDependentSource()

    with ndb.session() as Session:
        # 写入因子
        CypherStr, IDVar, Parameters = [], {}, {}
        for i, iSource in enumerate(DependentSource.keys()):
            iModule, iFT, iContext = DependentSource[iSource]
            iFTID = checkFactorTableExistence(iFT, tx=Session)
            if not iFTID:
                iCypherStr, iParameters = writeFactorTable(iFT, tx=None, var=f"ft{i}", id_var=IDVar)
            elif len(iFTID) > 1:
                raise Exception(f"因子表 {iFT.Name} 不唯一: {iFTID}")
            else:  # 先删除再创建
                iFTID = iFTID[0]
                FactorIDs = readFactorID(iFT, iFTID, tx=Session)
                deleteFactorTable(iFTID, tx=Session)
                deleteFactor(list(FactorIDs.values()), del_descriptors=True, tx=Session)
                iCypherStr, iParameters = writeFactorTable(iFT, tx=None, var=f"ft{i}", id_var=IDVar)
            CypherStr.append(iCypherStr)
            Parameters.update(iParameters)
        CypherStr = "\n".join(CypherStr)
        CypherStr += "\n RETURN " + ", ".join(f"id(ft{i})" for i in range(len(DependentSource)))
        FTIDs = Session.run(CypherStr, parameters=Parameters).values()[0]
        # 写入因子和自定义因子表的关系
        for i, iSource in enumerate(DependentSource.keys()):
            iModule, iFT, iContext = DependentSource[iSource]
            FactorIDs = readFactorID(iFT, FTIDs[i], tx=Session)
            Factors = [iFT.getFactor(iFactorName) for iFactorName in iFT.FactorNames]
            CypherStr, Parameters = writeRelation2FDB(Factors, FactorIDs, ndb, iFT.Name, specific_target={}, if_exists="update", tx=None)
            Session.run(CypherStr, parameters=Parameters)
        # 写入定义归属
        Authors = set()
        for i, iSource in enumerate(DependentSource.keys()):
            iModule, iFT, iContext = DependentSource[iSource]
            Authors.add(iContext.Author)
        for iAuthor in sorted(Authors):
            CypherStr = f"""
                    MATCH (n:!`参数集` WHERE n.Author='{iAuthor}')
                    MERGE (p:{author_label} {{`Name`: '{iAuthor}'}})
                    MERGE (p) - [:`定义`] -> (n)
                """
            Session.run(CypherStr, parameters={})
