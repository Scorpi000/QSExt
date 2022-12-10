# coding=utf-8

import time

from QSExt.KnowledgeDB.utils import genEntityArgs, readEntityData, writeEntityData

Entities = {
    # 事件
    "entity_event_ashare_placement": "事件-配股",
    # 证券
    "entity_security_ashare_info": "A股",
    # 机构
    "entity_institution_listed_company": "上市公司",
    
}

def updateEntity(target_dt, entity_label, if_exists="update"):
    Args = genEntityArgs(target_dt, config=("./实体配置.xls", entity_label), if_exists=if_exists)
    StartT = time.perf_counter()
    writeEntityData(target_dt, *readEntityData(target_dt, Args))
    print(f"运行时间: {time.perf_counter() - StartT}")
    return 0
