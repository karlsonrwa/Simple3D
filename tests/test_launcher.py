# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, fails, check

"""The launcher's command line: one parser, a --gui mode, and what reaches the
window. Round 74, plan C6.

Until then `python -m stepbuilder --gui ...` had a parser of its own with
parse_known_args, so a flag it did not know was dropped without a word, and
the two flag lists (this one and the headless one) overlapped by hand. The
window is a stand-in here: opening the real one from a test would be a Tk
window per case, and what is checked is what the launcher HANDS it.
"""
import contextlib
import io
import re
from pathlib import Path

import stepbuilder.gui as gui_mod
from stepbuilder.__main__ import build_parser, main


class _Var:
    def __init__(self, value):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class _FakeApp:
    """What _open_window touches, and nothing else."""
    made: list = []

    def __init__(self, config_path=None):
        self.config_path = config_path
        self.theme = _Var("Dark_green")
        self.silk_color = _Var("White")
        self.silk_top = _Var(True)
        self.silk_bottom = _Var(True)
        self.silk_flat = _Var(False)
        self.step_dirs = None
        self.themed = None
        self.prefill = None
        self.looped = False
        _FakeApp.made.append(self)

    def set_step_dirs(self, dirs):
        self.step_dirs = list(dirs)

    def set_theme(self, name):
        self.themed = name
        self.theme.set(name)

    def prefill_jobs(self, **kw):
        self.prefill = kw

    def mainloop(self):
        self.looped = True


gui_mod.StepBuilderApp = _FakeApp        # _open_window imports it at call time


def launch(argv):
    _FakeApp.made.clear()
    code = main(argv)
    return code, (_FakeApp.made[-1] if _FakeApp.made else None)


def refused(argv) -> str:
    """argparse's message when the command line is refused, else ''."""
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            main(argv)
    except SystemExit as exc:
        return err.getvalue() if exc.code else ""
    return ""


print("[1] the shipped launcher's command line reaches the window whole")
# simple3d.il:634-639 passes exactly these five.
code, app = launch(["--gui", "--config", "D:/proj/simple3d_config.json",
                    "--json-dir", "D:/proj/rev/cad", "--output-dir", "D:/proj/rev/3d",
                    "--brd-name", "MyBoard", "--dated-name"])
check("the window opens and runs", code == 0 and app is not None and app.looped)
check("the settings file is the one named", app.config_path == Path("D:/proj/simple3d_config.json"))
check("the paths and the name prefill it",
      app.prefill == {"json_dir": "D:/proj/rev/cad", "json_file": None,
                      "output_dir": "D:/proj/rev/3d", "brd_name": "MyBoard", "dated_name": True},
      str(app.prefill))
check("nothing else is touched", app.step_dirs is None and app.themed is None
      and app.silk_top.get() and app.silk_bottom.get() and not app.silk_flat.get()
      and app.silk_color.get() == "White")

print("\n[2] the standalone form: no --config, a single file")
code, app = launch(["--gui", "--json-file", "D:/proj/rev/cad/board.json"])
check("the default settings file", code == 0 and app.config_path is None)
check("a single intermediate, undated",
      app.prefill == {"json_dir": None, "json_file": "D:/proj/rev/cad/board.json",
                      "output_dir": None, "brd_name": None, "dated_name": False}, str(app.prefill))

print("\n[3] the flags for driving the window by hand")
code, app = launch(["--gui", "--step-dir", "D:/lib;D:/lib2", "--step-dir", "D:/proj/lib",
                    "--color", "Black", "--silk-color", "Black", "--no-silk-bottom",
                    "--flat-silkscreen"])
check("search path: repeatable, ;-separated, in order",
      app.step_dirs == ["D:/lib", "D:/lib2", "D:/proj/lib"], str(app.step_dirs))
check("the theme goes through set_theme, swatch included", app.themed == "Black")
check("the legend ink", app.silk_color.get() == "Black")
check("one side off, the other left as the config had it",
      app.silk_top.get() and not app.silk_bottom.get())
check("flat legend", app.silk_flat.get())
code, app = launch(["--gui", "--no-silkscreen"])
check("--no-silkscreen is both sides", not app.silk_top.get() and not app.silk_bottom.get())
code, app = launch(["--gui", "--silk-color", "Black", "--no-silk-top"])
check("a flag NOT passed leaves the remembered value alone",
      app.silk_bottom.get() and app.themed is None and app.config_path is None)

print("\n[4] what the launcher gets wrong is said, not dropped")
said = refused(["--gui", "--bogus-flag", "x"])
check("an unknown flag is an error", "unrecognized arguments" in said and "--bogus-flag" in said, said)
said = refused(["--gui", "D:/lib", "D:/x.json", "D:/out"])
check("positionals with --gui are an error", "--gui takes no positional" in said, said)
said = refused(["--batch"])
check("the headless form still wants its three positionals", "required" in said, said)
said = refused(["--gui", "--board-mode", "wrong"])
check("a shared flag is checked the same way in both forms", "invalid choice" in said, said)

print("\n[5] the headless form reads as before")
a = build_parser().parse_args(["D:/lib", "D:/x.json", "D:/out", "--board-mode", "layers",
                               "--step-dir", "D:/more", "--no-full-board"])
check("positionals and flags", a.step_dir == "D:/lib" and a.json_file == "D:/x.json"
      and a.output_dir == "D:/out" and a.board_mode == "layers"
      and a.extra_step_dirs == ["D:/more"] and a.no_full_board and not a.gui)
check("--silk-color has no default at the parser: the window keeps its own, "
      "the headless build falls back to DEFAULT_SILK", a.silk_color is None)
out = io.StringIO()
try:
    with contextlib.redirect_stdout(out):
        build_parser().parse_args(["--help"])
except SystemExit:
    pass
check("--help names --gui and the window-only flags",
      "--gui" in out.getvalue() and "--config" in out.getvalue() and "--json-dir" in out.getvalue())

print("\n[6] every flag simple3d.il passes is one the parser knows")
il = (ROOT / "simple3d.il").read_text(encoding="utf-8", errors="replace")
passed = sorted({f for f in re.findall(r"--[a-z][a-z-]+", il)})
known = set(build_parser()._option_string_actions)
check("the launcher and the parser agree", passed and all(f in known for f in passed),
      f"passed {passed}, unknown {[f for f in passed if f not in known]}")

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
import sys
sys.exit(0 if not fails else 1)
