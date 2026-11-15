import unittest

from QSExt.RuntimeConfig.config import RuntimeSettings


class FakeDB:
    def __init__(self, name="FakeDB"):
        self.Name = name
        self.connect_count = 0
        self.disconnect_count = 0

    def connect(self):
        self.connect_count += 1
        return self

    def disconnect(self):
        self.disconnect_count += 1


class RuntimeConfigInstanceTests(unittest.TestCase):
    def test_instance_definition_preserves_identity_role_and_lifecycle(self):
        db = FakeDB()
        settings = RuntimeSettings.from_dict({
            "factor_databases": [{
                "name": "WrappedDB",
                "instance": db,
                "role": "source",
            }],
        })

        pool = settings.to_db_pool()
        pool.create_all()
        self.assertIs(pool["WrappedDB"], db)
        self.assertEqual(pool.source_names, ["WrappedDB"])

        pool.connect_all()
        pool.disconnect_all()
        self.assertEqual(db.connect_count, 1)
        self.assertEqual(db.disconnect_count, 1)

    def test_bare_instance_uses_its_name_and_defaults_to_source(self):
        db = FakeDB(name="DirectDB")
        settings = RuntimeSettings.from_dict({"factor_databases": [db]})
        pool = settings.to_db_pool()
        pool.create_all()

        self.assertIs(pool["DirectDB"], db)
        self.assertEqual(pool.source_names, ["DirectDB"])

    def test_instance_is_mutually_exclusive_with_constructor_config(self):
        db = FakeDB()
        settings = RuntimeSettings.from_dict({
            "factor_databases": [{
                "name": "InvalidDB",
                "class": "JYDB",
                "instance": db,
            }],
        })

        with self.assertRaisesRegex(ValueError, "instance.*class"):
            settings.to_db_pool().create_all()


if __name__ == "__main__":
    unittest.main()
