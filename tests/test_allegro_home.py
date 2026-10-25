# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, fails, check

"""tools/skill_export.py (and tools/run_probe.py, which takes its rule) runs
Allegro with a HOME of its own and an environment that leads nowhere into
D:\\Projects\\OrCAD (round 100). The owner's HOME is that folder, closed to these
tools altogether since 11.10.2026, and with it every -nograph session loaded
the owner's allegro.ilinit - the installed tools before this tree's code - and
wrote his pcbenv. No Allegro is started here: the rules are plain functions.
"""
import os, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(ROOT / "tools"))
import skill_export as se  # noqa: E402


print("\n[1] which paths are the closed folder - judged by the spelling alone")
# Path.resolve() would open the folder to find out, and that is touching it.
for path, expected in [(r"D:\Projects\OrCAD", True), (r"d:\projects\orcad\pcbenv", True),
                       ("D:/Projects/OrCAD/bin", True), ("/d/Projects/OrCAD/bin", True),
                       (r"D:\Projects\OrCADx", False), (r"D:\Projects\OrCA", False),
                       (r"D:\Projects\AI\Claude\Simple3D\build\allegro-home", False), ("", False)]:
    got = se.off_limits(path)
    check(f"{path!r} {'is' if expected else 'is not'} it", got == expected, f"got {got}")


def refusal(explicit):
    """The message allegro_home exits with, or "" when it takes the folder."""
    try:
        se.allegro_home(explicit)
    except SystemExit as exc:
        return str(exc)
    return ""


print("\n[2] the HOME Allegro is given")
said = refusal(r"D:\Projects\OrCAD\pcbenv\..")
check("a HOME in the closed folder is refused, however it is spelled", said.startswith("refused"), said)
with tempfile.TemporaryDirectory(dir=ROOT / "build") as tmp:
    said = refusal(tmp)
    check("a HOME without the licence lines is refused before Allegro is started",
          "no licence lines" in said, said)
    (Path(tmp) / "pcbenv").mkdir()
    (Path(tmp) / "pcbenv" / "allegro.ini").write_text(
        '[allegro]\noption_licenses = "a"\nbase_license = b\n', encoding="utf-8")
    said = refusal(tmp)
    check("one whose allegro.ini names the licences is taken", said == "", said)
check("and by default it is build/allegro-home", se.HOME == ROOT / "build" / "allegro-home", se.HOME)

print("\n[3] the environment Allegro is given")
home = Path(r"D:\a home of its own")
user = {"HOME": r"D:\Projects\OrCAD", "MAGICK_HOME": r"D:\Projects\OrCAD\ImageMagick",
        "POTRACE_PATH": "d:/projects/orcad/potrace",
        "PATH": os.pathsep.join([r"C:\Windows\system32", "/d/Projects/OrCAD/bin",
                                 r"D:\Cadence\SPB_25.1\tools\bin", r"D:\Projects\OrCAD\Scripts"]),
        "CDS_LIC_FILE": "5280@licence-host", "TEMP": r"D:\tmp"}
env = se.allegro_env(home, user)
check("HOME is its own", env.get("HOME") == str(home), env.get("HOME"))
check("a variable that leads into the closed folder is dropped",
      "MAGICK_HOME" not in env and "POTRACE_PATH" not in env, sorted(env))
check("PATH keeps every entry but the closed folder's",
      env.get("PATH", "").split(os.pathsep) == [r"C:\Windows\system32", r"D:\Cadence\SPB_25.1\tools\bin"],
      env.get("PATH"))
check("and every other variable is kept as it was",
      env.get("CDS_LIC_FILE") == "5280@licence-host" and env.get("TEMP") == r"D:\tmp", env)
check("this process's own environment is left alone", os.environ.get("HOME") != str(home))

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
