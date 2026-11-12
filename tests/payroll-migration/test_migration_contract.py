"""Pure tooling checks only. Does not replace browser acceptance."""
import ast, importlib.util, unittest
from pathlib import Path
P=Path(__file__).with_name('migration_runner.py')
spec=importlib.util.spec_from_file_location('migration',P);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Contract(unittest.TestCase):
 def test_unique_cases(self):
  self.assertEqual(len(m.CASES),7);self.assertEqual(len({n for n,_ in m.CASES}),7)
 def test_stable_digest(self):
  self.assertEqual(m.digest({'a':1,'b':2}),m.digest({'b':2,'a':1}));self.assertNotEqual(m.digest({'a':1}),m.digest({'a':2}))
 def test_synthetic_payload(self):
  p=m.payload({'name':'虛構甲'});self.assertEqual(p['mimeType'],'application/json');self.assertIn('虛構甲',p['buffer'].decode())
 def test_isolation_contract(self):
  s=P.read_text();ast.parse(s);self.assertIn('chromium_sandbox=True',s);self.assertIn('Server(app,None',s);self.assertIn('substitute=False',s);self.assertNotIn('chromium_sandbox=False',s)
 def test_no_sdk_or_mutation(self):
  tree=ast.parse(P.read_text());calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call)]
  self.assertFalse(any(isinstance(n.func,ast.Name) and n.func.id in ('preflight','Emulators') for n in calls))
  self.assertFalse(any(isinstance(n.func,ast.Attribute) and n.func.attr=='write_bytes' for n in calls))
if __name__=='__main__':unittest.main()
