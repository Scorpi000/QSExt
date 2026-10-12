"""Regression checks for graph schema migration."""

from unittest.mock import MagicMock
import datetime as dt
from functools import partial

import numpy as np
import pytest

from QuantStudio.Factor.FactorOperator import RollingApply
from QSExt.QSRegistry.QSGraphDB import QSGraphDB


def test_schema_removes_legacy_name_constraint_after_qsid_constraint():
    graph = MagicMock()
    session = graph.session.return_value.__enter__.return_value
    QSGraphDB._initSchema(graph)
    statements = [call.args[0] for call in session.run.call_args_list]
    qsid_statement = next(s for s in statements if "CONSTRAINT fdb_qsid" in s)
    drop_statement = "DROP CONSTRAINT fdb_name IF EXISTS"
    assert statements.index(qsid_statement) < statements.index(drop_statement)
    graph._initVectorIndex.assert_called_once()


def test_schema_keeps_legacy_constraint_when_qsid_creation_fails():
    graph = MagicMock()
    session = graph.session.return_value.__enter__.return_value

    def run(statement):
        if "CONSTRAINT fdb_qsid" in statement:
            raise RuntimeError("duplicate QSID")

    session.run.side_effect = run
    with pytest.raises(RuntimeError, match="duplicate QSID"):
        QSGraphDB._initSchema(graph)
    assert all("DROP CONSTRAINT" not in call.args[0]
               for call in session.run.call_args_list)
    graph._initVectorIndex.assert_not_called()


@pytest.mark.parametrize("func", [np.nanmean, partial(np.nanquantile, q=0.5)])
def test_operator_callable_roundtrip(func):
    op = RollingApply(func=func, window=3)
    props = QSGraphDB._serializeOperatorNode(MagicMock(), op, dt.datetime.now().isoformat())
    graph = MagicMock()
    graph._runCypher.return_value = [{"o": props}]
    restored = QSGraphDB.reconstructOperator(graph, op.QSID)
    assert restored.QSID == op.QSID
    assert restored._QSArgs.ModelArgs["func"](np.array([1., 2., 3.])) == 2.


def test_script_dependencies_store_names_for_aliased_entries():
    graph = MagicMock()
    graph._findScriptByTargetTable.return_value = {"QSID": "dependency"}
    QSGraphDB._createScriptDeps(graph, "source", {
        "FactorDeps": {"prices": ["open", {"Name": "close", "Alias": "adj_close"}]}
    })
    assert graph._runCypher.call_args.args[1]["factor_names"] == ["open", "close"]
