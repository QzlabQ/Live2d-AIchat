import os
import subprocess
import sys
from pathlib import Path

root = Path.cwd()
log_path = root / 'logs' / 'eval_rag_bge_20260707_fixed_full.txt'
env = os.environ.copy()
env['PYTHONIOENCODING'] = 'utf-8'
cmd = [sys.executable, '-m', 'scripts.evaluate_rag', '--dataset', str(root / 'evals' / 'phase2_rag_eval.50.jsonl'), '--target', '0']
proc = subprocess.run(cmd, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
log_path.write_text(proc.stdout, encoding='utf-8')
print('returncode =', proc.returncode)
print('log_path =', log_path)
print('last_lines =')
for line in proc.stdout.splitlines()[-12:]:
    print(line)