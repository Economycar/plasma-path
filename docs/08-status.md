# 08. Status and handoff

Newest entry first. Read this and `07-decisions.md` before resuming.

## 2026-09-25

**State.** Skill at 1.2.4, released on GitHub
(https://github.com/Economycar/plasma-path/releases, latest link stable).
Repo public, clean, on `master`, tags `skill-v1.1.0` through
`skill-v1.2.4`. The friend has not been given the link yet; the user has
tested the skill on his own claude.ai account and it works. Documentation
for the friend: `INSTALL.md` (setup, update, troubleshooting, how to get a
picture) and `GUIDE.md` (capability tour with previews).

**Verified this phase, and how.**
- Pipeline regression: `images/fish.png` through all three modes in a venv
  limited to numpy, scipy and Pillow, compared against `samples/gcode/`
  with `scripts/compare_nc.py`; the silhouette also matched the program
  that was cut on metal on 2026-09-21 before that file was removed from
  the repo (size within 0.015 in).
- Skill evals (subagents, with and without the skill): four prompts
  30/30 assertions with the skill; a fifth (flower photo with a stem
  merged into a petal, then "remove the bump completely") passed after the
  1.2.0 rewrite. Results in `skill/plasma-path-workspace/` (git-ignored).
- Plugin marketplace: installed from GitHub into Claude Code on this
  machine, resolved to the tagged version, then removed.
- Packaged skill validated with skill-creator's validator on every release.

**Next step.** Send the friend `INSTALL.md`; watch the first real
conversation and note where the questions confuse him. Then ask which
material the 2026-09-21 cut was and mark that cut-chart row.

**Watch.**
- claude.ai is merging chat and Cowork during late September 2026; menu
  names in `INSTALL.md` (Customize > Skills, Settings > Capabilities) may
  move. Re-check after the rollout lands.
- Re-upload behaviour in claude.ai: whether uploading a skill with the
  same name replaces or duplicates. `INSTALL.md` says remove first; drop
  that step if a replace is confirmed.
- Evals were last run on 1.2.0/1.2.1; 1.2.2 to 1.2.4 changed text and
  `make` only. Re-run before any geometry change.

**Open work** is in `04-backlog.md` under "Skill".
