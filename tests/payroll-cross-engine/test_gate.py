#!/usr/bin/env python3
"""Pure predicate tests. No browser, network or subprocess is started."""
import importlib.util
from pathlib import Path
import unittest
P=Path(__file__).with_name('cross_engine_runner.py')
spec=importlib.util.spec_from_file_location('cross_engine',P);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def proc(pid,ppid,argv,**kw):
 d={'pid':pid,'ppid':ppid,'name':'test','argv':argv,'uid':[1001]*4,'seccomp':'2','seccompFilters':'2','noNewPrivs':'1','nspid':[pid,7]};d.update(kw);return d
class GateTests(unittest.TestCase):
 def records(self,engine='firefox'):
  return [proc(10,1,['python3','cross_engine_runner'],seccompFilters='1',nspid=[10]),proc(20,10,['node','driver'],seccompFilters='1'),proc(30,20,['firefox'],seccompFilters='1'),proc(40,30,['/usr/firefox','-contentproc'] if engine=='firefox' else ['/opt/WebKitWebProcess'])]
 def test_firefox_pass(self):self.assertEqual(m.gate_records(self.records(),10,'firefox',1001)['status'],'PASS')
 def test_webkit_pass(self):self.assertEqual(m.gate_records(self.records('webkit'),10,'webkit',1001)['status'],'PASS')
 def test_wrong_engine_blocked(self):self.assertEqual(m.gate_records(self.records(),10,'webkit',1001)['status'],'BLOCKED')
 def test_unrelated_process_not_evidence(self):
  r=[proc(40,99,['firefox','-contentproc'])];self.assertEqual(m.gate_records(r,10,'firefox',1001)['status'],'BLOCKED')
 def test_missing_content_blocked(self):self.assertEqual(m.gate_records([],10,'firefox',1001)['status'],'BLOCKED')
 def test_each_criterion_blocks(self):
  for kw in ({'uid':[0]*4},{'uid':[1002]*4},{'seccomp':'0'},{'seccomp':None},{'seccompFilters':None},{'seccompFilters':'1'},{'noNewPrivs':'0'},{'nspid':[40]},{'nspid':[]}):
   with self.subTest(kw=kw):
    r=self.records();r[-1].update(kw);self.assertEqual(m.gate_records(r,10,'firefox',1001)['status'],'BLOCKED')
 def test_one_bad_content_blocks_all(self):
  r=self.records()+[proc(41,30,['firefox','-contentproc'],seccomp='0')];self.assertEqual(m.gate_records(r,10,'firefox',1001)['status'],'BLOCKED')
 def test_inherited_pid_namespace_blocks(self):
  r=self.records();r[0]['nspid']=[10,1];self.assertEqual(m.gate_records(r,10,'firefox',1001)['status'],'BLOCKED')
 def test_inherited_parent_filter_blocks(self):
  r=self.records();r[2]['seccompFilters']='2';self.assertEqual(m.gate_records(r,10,'firefox',1001)['status'],'BLOCKED')
 def test_disabled_arg_in_browser_parent_blocks(self):
  r=self.records();r[2]['argv']+=['--no-sandbox'];self.assertEqual(m.gate_records(r,10,'firefox',1001)['status'],'BLOCKED')
 def test_disabled_arg_value_blocks(self):
  r=self.records();r[-1]['argv']+=['--disable-seccomp-filter-sandbox=true'];self.assertEqual(m.gate_records(r,10,'firefox',1001)['status'],'BLOCKED')
 def test_unreadable_descendant_blocks(self):
  r=self.records()+[proc(41,30,[],inspectionError='cmdline unreadable')];self.assertEqual(m.gate_records(r,10,'firefox',1001)['status'],'BLOCKED')
 def test_arg_substring_does_not_match(self):self.assertEqual(m.forbidden_arguments(proc(1,0,['--title=--no-sandbox'])),[])
 def test_argv_formats(self):
  self.assertEqual(m.split_cmdline(b'/usr/firefox\x00-contentproc\x00'),['/usr/firefox','-contentproc'])
  self.assertEqual(m.split_cmdline(b'/usr/firefox -contentproc\x00'),['/usr/firefox','-contentproc'])
 def test_status_fields(self):self.assertEqual(m.parse_status('Name:\tfoo\nNSpid:\t100 2\n')['NSpid'],'100 2')
 def test_root_and_environment_block(self):
  self.assertTrue(m.check_environment({},0));self.assertFalse(m.check_environment({},1001))
  for key in m.DISABLED_ENV:self.assertTrue(m.check_environment({key:'0'},1001))
 def test_descendant_closure_and_cycle(self):
  r=[proc(40,30,[]),proc(30,20,[]),proc(20,10,[]),proc(99,99,[])];self.assertEqual(m.descendant_ids(r,10),{20,30,40})
 def test_no_disable_launch_flags(self):
  s=P.read_text();self.assertIn('launch(headless=True)',s);self.assertNotIn('chromium_sandbox=False',s)
if __name__=='__main__':unittest.main()
