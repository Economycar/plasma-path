# Plasma Path skill

A Claude skill that turns a picture, or a description like "a 10 inch circle
with XYZ cut out", into a Mach3 program for a Langmuir CrossFire plasma
table, through a conversation with previews. It is meant for someone who
has Claude but no CAD.

```
skill/
  plasma-path/           the skill itself (this folder is what gets zipped)
    SKILL.md             instructions Claude follows; carries the version
    CHANGELOG.md         what changed in each version
    scripts/pp.py        the whole pipeline (numpy, scipy, Pillow only)
    scripts/vendor/      pure-Python potrace (GPLv2+) and Liberation fonts (OFL)
    references/          cut chart, cleanup recipes, Mach3 hand-over, Project text
    evals/               test prompts and images (not packaged)
  dist/                  numbered packages, one per release
  release.sh             checks versions agree and builds dist/plasma-path-<ver>.skill
  plasma-path-workspace/ eval runs and grading (ignored by git)
```

Nothing is installed at run time and nothing lives on the user's computer:
the three libraries the script needs are preinstalled in claude.ai's
sandbox and everything else is vendored inside the zip.

## Versions

The version lives in three places that must agree: `SKILL.md`
(`metadata.version`), `scripts/pp.py` (`__version__`) and `CHANGELOG.md`.
`release.sh` refuses to package if they differ. Every `.nc` file the skill
writes has the version in its second comment line, so a part on the table
can be traced to the version that made it. In a conversation, "what version
of plasma-path is this?" makes Claude run `pp.py version` and answer.

Numbering: MINOR goes up for new capability (a command, an option), PATCH
for fixes and wording, MAJOR only if G-code output or the conversation
changes in a way that makes old habits wrong.

Git tags mirror the packages: `skill-v1.1.0` is the commit that produced
`dist/plasma-path-1.1.0.skill`.

## Install (first time, for anyone)

1. Send `dist/plasma-path-<ver>.skill`. It is a zip with a different
   extension; the upload dialog accepts it as is.
2. In claude.ai or the Claude desktop app, with code execution and file
   creation on (Settings > Capabilities): Customize > Skills > + > Create
   skill > Upload a skill.
3. Recommended: a Project whose instructions come from
   `plasma-path/references/project-instructions.md`, edited for the usual
   material and sheet size. Dropping a picture into that project is then the
   whole workflow.

Personal Pro and Max plans have code execution on by default. On a Team or
Enterprise plan an admin has to enable it.

## Update (sending a new version)

On this side:

1. Make the change under `plasma-path/`.
2. Bump the version in `scripts/pp.py`, `SKILL.md` and add a `CHANGELOG.md`
   entry dated today.
3. `skill/release.sh`, then commit and tag as it prints:
   `git add -A && git commit -m "skill 1.2.0" && git tag skill-v1.2.0`.
4. Send `dist/plasma-path-<ver>.skill` with the changelog entry as the
   message.

On the receiving side: open Customize > Skills, remove the old plasma-path
entry, then upload the new file. Uploading without removing may leave two
skills with the same name, and Claude could pick either. After uploading,
ask Claude in a new chat what version it has; it should name the new one.

Job folders from earlier conversations are unaffected by updates; a new
conversation uses the new version.

## Run it by hand

```bash
python3 skill/plasma-path/scripts/pp.py version
python3 skill/plasma-path/scripts/pp.py clean images/snoopy1.webp --job /tmp/job --bottom 0.05
python3 skill/plasma-path/scripts/pp.py design --job /tmp/job --mode silhouette --height 12
python3 skill/plasma-path/scripts/pp.py gcode  --job /tmp/job --name snoopy
python3 scripts/compare_nc.py /tmp/job/snoopy.nc samples/gcode/silhouette.nc /tmp/overlay.png
```

The last line overlays the new program on the one cut on 2026-09-21 and
prints the deviation. Run it after any change to the geometry or the post;
it should stay within a few hundredths of an inch apart from lead-ins.

## Evals

`plasma-path/evals/evals.json` holds the test prompts and their assertions;
images are in `plasma-path/evals/files/`. Runs and grading live in
`plasma-path-workspace/` (see `iteration-1/review.html` for the first
round: with the skill 30/30 assertions across four prompts).
