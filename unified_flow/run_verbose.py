"""Full verbose pipeline run with no output truncation."""
import subprocess, sys
result = subprocess.run(
    ['python', 'run_pipeline_v2.py'],
    capture_output=True,
    text=True,
    encoding='utf-8',
    errors='replace'
)
print("=== STDOUT ===")
print(result.stdout)
print("=== STDERR ===")
print(result.stderr)
print("=== EXIT CODE:", result.returncode)
