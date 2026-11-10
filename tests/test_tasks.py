"""Run the shipped task commands through a real shell, with disposable arguments."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]


@unittest.skipIf(os.name == "nt", "Project tasks target POSIX shells (including WSL)")
class ZedTaskIntegration(unittest.TestCase):
    def test_tasks_pass_paths_literally_and_do_not_execute_filename_contents(self):
        tasks = json.loads((PROJECT / ".zed/tasks.json").read_text())
        with tempfile.TemporaryDirectory(prefix="green tasks '") as folder:
            root = Path(folder)
            scripts = root / "scripts"
            scripts.mkdir()
            # Stand in for the helper so every task exits without opening a GUI.
            (scripts / "greenlatex.py").write_text("import json,sys; print(json.dumps(sys.argv[1:]))")
            source = root / "resume ' $(touch sentinel).tex"
            source.write_text("test")
            for task in tasks:
                with self.subTest(task=task["label"]):
                    env = dict(os.environ)
                    # Remote task terminals need not inherit custom task env.
                    # Zed resolves its built-in placeholders in args/cwd before
                    # spawning the shell; test that path rather than exporting
                    # values that were missing in the real WSL task failure.
                    for key in list(env):
                        if key.startswith(("GREEN_LATEX_", "ZED_")):
                            del env[key]
                    self.assertFalse(task.get("env"), "Tasks must pass paths as arguments")
                    arguments = [value.replace("$ZED_WORKTREE_ROOT", str(root)).replace("$ZED_FILE", str(source))
                                 for value in task["args"]]
                    command_line = shlex.join([task["command"], *arguments])
                    result = subprocess.run(command_line, shell=True, cwd=root, env=env,
                                            capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    arguments = json.loads(result.stdout)
                    command = "preview" if "preview" in task["label"] else "build" if "Build" in task["label"] else "doctor"
                    expected = [command] if command == "doctor" else [command, str(source)]
                    self.assertEqual(arguments, expected)
                    self.assertFalse((root / "sentinel").exists())


if __name__ == "__main__":
    unittest.main()
