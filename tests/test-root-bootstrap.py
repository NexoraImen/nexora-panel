"""Offline onboarding creates one owner only in a genuinely empty database."""
import ast
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import unittest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT / 'backend/app.py').read_text(encoding='utf-8'))


class RootBootstrap(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'bot.db'
        with closing(self.connection()) as con:
            con.execute('CREATE TABLE tenants (id INTEGER PRIMARY KEY, name TEXT, '
                        'parent_id INTEGER, is_active INTEGER, credit INTEGER)')
        self.ns = dict(_ensure_bot_db=lambda: (True, None), _bot_rw=self.connection,
                       HTTPException=HTTPException)
        node = next(n for n in TREE.body if isinstance(n, ast.FunctionDef)
                    and n.name == '_root_tenant_row')
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'root-bootstrap', 'exec'), self.ns)

    def connection(self):
        con = sqlite3.connect(self.db, timeout=10, isolation_level=None)
        con.row_factory = sqlite3.Row
        return con

    def test_concurrent_empty_install_has_one_owner(self):
        with ThreadPoolExecutor(max_workers=5) as workers:
            rows = list(workers.map(lambda _: self.ns['_root_tenant_row'](), range(5)))
        self.assertEqual({r['id'] for r in rows}, {1})
        self.assertEqual(rows[0]['credit'], -1)
        with closing(self.connection()) as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM tenants').fetchone()[0], 1)

    def test_existing_owner_with_larger_id_is_selected(self):
        with closing(self.connection()) as con:
            con.execute("INSERT INTO tenants VALUES (1,'reseller',9,1,20)")
            con.execute("INSERT INTO tenants VALUES (9,'owner',NULL,1,-1)")
        self.assertEqual(self.ns['_root_tenant_row']()['id'], 9)

    def test_orphaned_resellers_are_not_reassigned(self):
        with closing(self.connection()) as con:
            con.execute("INSERT INTO tenants VALUES (1,'reseller',9,1,20)")
        with self.assertRaises(HTTPException) as error:
            self.ns['_root_tenant_row']()
        self.assertEqual(error.exception.status_code, 409)
        with closing(self.connection()) as con:
            self.assertEqual(tuple(con.execute('SELECT id,parent_id,credit FROM tenants').fetchone()),
                             (1, 9, 20))


if __name__ == '__main__':
    unittest.main()
