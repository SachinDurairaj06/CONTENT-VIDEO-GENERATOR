"""Redirect all output to a file for full inspection."""
import sys, io

# Redirect stdout and stderr to a log file
log_file = open('tmp_pipeline_full.log', 'w', encoding='utf-8', errors='replace')
orig_stdout, orig_stderr = sys.stdout, sys.stderr
sys.stdout = io.TextIOWrapper(log_file.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr = sys.stdout

try:
    # Import and run pipeline
    import importlib.util, os
    spec = importlib.util.spec_from_file_location("pipeline", "run_pipeline_v2.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()
except Exception as e:
    print(f"\nFATAL: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
finally:
    sys.stdout = orig_stdout
    sys.stderr = orig_stderr
    log_file.close()
    print("Log written to tmp_pipeline_full.log")
