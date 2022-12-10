# coding=utf-8

import time

from QSExt.KnowledgeDB.utils import genRelationArgs, readRelationData, writeRelationData

Relations = {
    "relation_listed_company2security": (["机构"], "发行", ["证券", "A股"]),
}

def updateRelation(target_dt, source_labels, relation_label, target_labels, if_exists="update"):
    Args = genRelationArgs(target_dt, config=("./关系配置.xls", "关系配置"), relation_label, source_labels, target_labels, if_exists=if_exists)
    StartT = time.perf_counter()
    writeRelationData(target_dt, *readRelationData(target_dt, Args))
    print(f"运行时间: {time.perf_counter() - StartT}")
    return 0
