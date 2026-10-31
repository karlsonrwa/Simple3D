# Record: the pre-flight check against the interpreter the window runs (31.10.2026, round 114)

Evidence for R2-2 of the 23.10.2026 review, open in both rounds: `s3dPreflight` checked `S3D_Python` (python.exe) while `s3dLaunch` started the window with `S3D_PythonW` (pythonw.exe), so with `python` pinned and a bare `pythonw` that PATH resolves to another install, the check passed and the window died with nothing said. The reviewer asked for "a run where python has OCP and pythonw does not, and the check reports the failure; or the check verifies the same executable that is launched". Since round 114 both procedures take the interpreter from one rule, `s3dWindowPython` (`pythonw`, or `python` when `pythonw` is `""`), and this file is the run.

Made on the owner's machine with Allegro X Venture 25.1 (`allegro -nograph`, `tools/run_probe.py`, HOME `build/allegro-home`, a copy of `input/circle-A0.brd`), on 31.10.2026 between 16:38 and 16:41. Two Pythons of this machine: `C:/Python314` (3.14.7, cadquery-ocp 7.9.3 in its user site, tkinter) and `%LOCALAPPDATA%/Programs/Python/Python311` (3.11.4, no OCP).

## How to repeat

    set S3D_PROBE_TREE=<a whole checkout: its simple3d.il, exporter, config and stepbuilder>
    set S3D_PROBE_OUT=<an empty folder>
    set S3D_PROBE_CASES=label|<python>|<pythonw>;label|<python>|<pythonw>;...
    python tools/run_probe.py tools/probes/probe_preflight.il s3dProbePreflight input/circle-A0.brd

`s3dProbePreflight` loads the tree's `simple3d.il`, sets `S3D_ScriptDir` to the tree and Allegro's `noconfirm` (the failure's dialog then returns at once), and for each case sets `S3D_Python` and `S3D_PythonW` and calls `s3dPreflight` itself. `s3dLaunch` is never called, so no window opens.

`allegro.exe` is a GUI program (PE subsystem 2) and has no console to lend the `cmd` its `system()` starts, so a check's `cmd` may get a console window of its own. These runs were started through `build/fix-2026-10-31/r114/on_desktop.py`, which runs the command on the desktop "Simple3D-tests" the GUI suites use (`CreateProcessW` with `lpDesktop`); a child process lands on its parent's desktop unless told otherwise, so Allegro and its `cmd` ran there. The owner's desktop was not watched during the runs; BaroSim's `tools/desktop_run.py --wait` does both and would have been the better tool.

**Correction (round 115, the same day).** A desktop of its own does not keep a console off the owner's screen on this machine: its default terminal, Windows Terminal, takes every new console and opens its window on the user's desktop (`docs/records/export-folder-2026-10-31.md`, "The owner's screen"). These runs started `cmd /c python tools/run_probe.py ...`, and the real check started a `cmd` four times in each, so they most likely showed Terminal windows on the owner's screen. `desktop_run.py` watches only the program's own windows and would not have seen a Terminal window either: it belongs to WindowsTerminal.exe.

## The cases, and what `s3dPreflight` returned

| case | python | pythonw | round 113's code (`58d46f2`) | round 114's |
|---|---|---|---|---|
| good | 3.14 | 3.14 | t | t |
| the reviewer's | 3.14, with OCP | 3.11, without | **t** - the window would have died silently | **nil**, naming 3.11's pythonw |
| the reverse | 3.11, without | 3.14, with | **nil** - a window that would have opened was stopped | t |
| pythonw `""` | 3.14 | (empty) | t | t (the window's interpreter is python) |

Round 114's report for the reviewer's case, as the Allegro console carries it (the paths of this machine):

    ===== Simple 3D: the JSON was written, but Python did not start =====
    ...
    Python (C:/Users/Karlson/AppData/Local/Programs/Python/Python311/pythonw.exe) failed this check:
        import stepbuilder.core, tkinter
    It is the interpreter the 3D window runs under ("pythonw",
    or "python" when pythonw is set to "").

    The interpreter that ran was:
        S3D_PY C:\Users\Karlson\AppData\Local\Programs\Python\Python311\pythonw.exe 3.11.4

    It reported:
    S3D_PY C:\Users\Karlson\AppData\Local\Programs\Python\Python311\pythonw.exe 3.11.4
    Traceback (most recent call last):
      File "<string>", line 1, in <module>
      File "D:\Projects\AI\Claude\Simple3D\stepbuilder\core.py", line 15, in <module>
        from OCP.Quantity import Quantity_Color, Quantity_TypeOfColor
    ModuleNotFoundError: No module named 'OCP'

So pythonw's output reaches the check's log through Allegro's own `system()` as well, traceback included. Before Allegro, the same command shape was measured from a console process (`build/fix-2026-10-31/r114/pyw_redirect.py`): python and pythonw of 3.11, 3.12 and 3.14, behind one and two `cmd` layers, every sentinel and every traceback in the log.

## What the suite holds

`tests/test_launch_cmd.py` builds both command lines from `window_python`, the copy of `s3dWindowPython`, and [7] holds `simple3d.il` to it: the rule's one expression, and each of `s3dPreflight` and `s3dLaunch` taking its interpreter from it and from nowhere else. Its behavioural half plays the reviewer's case with a stand-in module that imports under python and refuses under pythonw: checked with python the stand-in install passes, checked with the window's interpreter it fails and the log names pythonw. The mutation table has a row for each of the three ways back.
