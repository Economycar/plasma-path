# Installing Plasma Path in Claude

This is for using the skill in the Claude desktop app or at claude.ai. You
don't need anything else installed on your computer. Everything runs on
Claude's side; you get files back in the chat.

## First-time setup (about two minutes)

1. **Download the skill file.** Click this link; it always gives you the
   newest version:

   https://github.com/Economycar/plasma-path/releases/latest/download/plasma-path.skill

   It's a small file called `plasma-path.skill`. Leave the name as it is.

2. **Turn on code execution.** In Claude, open Settings, then Capabilities,
   and make sure *Code execution* and *File creation* are on. (On a personal
   Pro or Max plan they usually are already. On a work Team plan an admin
   has to switch them on.)

3. **Upload the skill.** Open Customize, then Skills. Click the + button,
   choose *Create skill*, then *Upload a skill*, and pick the file you
   downloaded. You should see "plasma-path" in your list of skills.

4. **Optional but worth it: make a Project.** Create a Project called
   something like "Plasma table" and paste the text from
   [skill/plasma-path/references/project-instructions.md](skill/plasma-path/references/project-instructions.md)
   into its instructions, editing the line about your usual material and
   sheet size. Then every new chat in that project already knows your table.

## Using it

Start a new chat (in the project if you made one), attach a picture, and
say what you want, for example:

- "Cut this out of 14 gauge steel, about 12 inches tall."
- "Make a spray-paint stencil of this logo, 300 mm wide."
- "I want a 10 inch circle with the word WELCOME cut out, with a hole at
  the top to hang it."

Claude shows you the cleaned-up drawing, asks two or three questions
(what it's for, how big, what material), shows you a preview with the
parts labelled, and asks about anything that would fall out of the sheet.
Answer in plain words: "yes", "make the eyes solid", "bridge it at A and
C", "get rid of the bump on the right". When you're happy it gives you:

- the `.nc` file for Mach3,
- a picture of exactly what the torch will do,
- the numbers (finished size, pierces, minutes) and a short reminder of
  where to zero the machine.

You can change anything afterwards by asking: bigger, different material,
different parts, a different picture edit. Nothing is cut until you load
the file in Mach3 yourself, so it's safe to experiment.

## Getting a picture when you don't have one

Claude can't draw pictures itself (no Claude app can), but it can turn any
picture into a cut file, and it can make simple shapes and text on its own
("a 10 inch circle with WELCOME cut out"). For anything else, three
options, easiest first:

**1. Use Gemini in your Google account, then drop the picture in.** No
setup. Go to gemini.google.com (or the Gemini app), sign in with your
Google account, and ask for the picture with wording like this:

> A flat black silhouette of a bass jumping out of water, on a plain white
> background. No shading, no gradients, no outline strokes, no text. Simple,
> bold shapes, all connected into one piece, centered.

Download the result and attach it in your Plasma Path chat. Claude will
clean it up and take it from there. If you're not sure how to word it, ask
Claude in the Plasma Path chat: "write me a Gemini prompt for a silhouette
of a bass" and paste what it gives you. Tips: "silhouette", "black on
white", "no shading" and "connected into one piece" are what make a picture
easy to cut. If the result has thin whiskers or floating dots, ask Gemini
for "thicker, simpler shapes" or let Claude remove them.

**2. Generate inside Claude with the Hugging Face connector.** This works
in the same chat, but takes a one-time setup and a paid Claude plan (Pro or
Max), and the image models are not Google's:

1. Make a free account at huggingface.co.
2. In Claude: Settings, then Connectors, then *Add custom connector*. For
   the URL enter `https://huggingface.co/mcp?login` and sign in when asked.
3. On huggingface.co/settings/mcp, add an image tool such as
   *mcp-tools/FLUX.1-Krea-dev* or *mcp-tools/qwen-image*.
4. In a Plasma Path chat, say "generate a black silhouette of a bass with
   the Hugging Face image tool, then make it a 12 inch cut file". Claude
   generates, then converts. Your Hugging Face account comes with free
   credits for this.

**3. Not recommended: a Gemini API key with a local server.** It is
possible to wire Google's own image model (Nano Banana) into Claude through
an API key from Google AI Studio and a small program installed on your
computer. That is the kind of thing that breaks on the next app update,
which is exactly what this skill was built to avoid. Ask whoever maintains
the skill if you really want it.

Whichever way the picture arrives, everything after that is the same
conversation.

## Updating to a new version

1. In Claude, open Customize, then Skills, and **remove the old
   plasma-path entry** (uploading a second one with the same name can leave
   Claude picking either).
2. Click the same download link as above and upload the new file, the same
   way as the first time.
3. Start a new chat and ask "what version of plasma-path is this?". Claude
   will tell you, and what's new is listed in
   [skill/plasma-path/CHANGELOG.md](skill/plasma-path/CHANGELOG.md).

Old chats keep working as they were; new chats use the new version.

## If something's off

- **Claude doesn't use the skill.** Mention the plasma table or cutting in
  your message ("...for my CrossFire"), and check that code execution is on
  in Settings > Capabilities. You can also say "use the plasma-path skill".
- **It says a package is missing or can't install something.** Copy the
  exact wording and send it to whoever maintains the skill; it means
  Claude's environment changed.
- **The cleaned-up drawing lost something or kept junk.** Just say so:
  "the whiskers are missing", "drop the writing in the corner". Claude can
  edit the picture however you describe.
- **The part came out slightly big or small on the table.** Tell Claude
  the amount. That's the kerf setting and it will regenerate the file.
- **The pierce pause seems too short in Mach3.** Ask Claude to regenerate
  "with the dwell in milliseconds" (Mach3 has a setting for this).

## Which version do I have?

Ask Claude in any chat. The version is also written in the second line of
every `.nc` file it makes, so a file on the Mach3 computer can be traced
back to the version that made it.
