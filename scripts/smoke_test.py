"""Run the full pipeline headless in all three cut modes and print the numbers.

    .venv/bin/python scripts/smoke_test.py [image] [--write DIR]

With --write, the G-code for each mode is written to DIR/<mode>.nc.
Use this after changing app/pipeline.py to check nothing broke.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import server as S  # noqa: E402

argv = sys.argv[1:]
write = None
if "--write" in argv:
    k = argv.index("--write")
    write = argv[k + 1]
    del argv[k:k + 2]
src = argv[0] if argv else "images/snoopy1.webp"

ok = True
for mode in ("silhouette", "lineart", "stencil"):
    r = S.run(S.params_from({"source": src, "mode": mode, "name": mode}))
    i = r["toolpath"]["info"]
    print(f"{mode:11s} {r['ms']:4d} ms  pieces={r['design']['pieces']} bridges={len(r['design']['bridges'])} "
          f"rings={len(i['rings'])} pierces={i['pierces']} segs={i['segments']} "
          f"cut={i['cut_length']:.1f} size={i['size'][0]:.2f}x{i['size'][1]:.2f} "
          f"est={r['toolpath']['est_minutes']:.1f}min warnings={i['warnings']}")
    ok &= r["design"]["pieces"] == 1 and not i["warnings"]
    if write:
        os.makedirs(write, exist_ok=True)
        open(os.path.join(write, f"{mode}.nc"), "w").write(r["gcode"])
print("OK" if ok else "CHECK WARNINGS")
