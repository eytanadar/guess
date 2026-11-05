# Demo video

A narrated screen recording of GUESS (at most 5 minutes) that you can rebuild
whenever the app changes.

```
demo/PROMPT.md        what the video should say and show, in what voice; the action vocabulary
demo/write-script.mjs Claude turns PROMPT.md + docs + the CHI paper into script.json
demo/script.json      scenes: narration + the actions that drive the app
demo/make-demo.mjs    narration (ElevenLabs) → recording (Playwright) → MP4 (ffmpeg)
demo/out/             guess-demo.mp4, guess-demo.srt (captions), timing.json
demo/.cache/          narration clips, cached by text and voice (unchanged scenes cost nothing)
```

## Requirements

- `.env` at the repository root containing `ELEVENLABS_API=...` (narration)
  and, for step 1, `ANTHROPIC_API_KEY=...`.
- ffmpeg on the PATH (`brew install ffmpeg`), and Playwright's recorder:
  `npx playwright install ffmpeg` (once).
- Chrome, used by Playwright as for the tests.

## Rebuilding after you add features

```sh
cd web
npm run demo:script        # 1. Claude rewrites demo/script.json (old one kept as script.prev.json)
npm run demo -- --dry-run  # 2. check the actions work and the pacing (silent, no narration cost)
npm run demo               # 3. the real thing → demo/out/guess-demo.mp4
```

- **Steering a version:** `npm run demo:script -- --notes "feature the timeline
  and presentation mode; skip the data table"`.
- **Editing by hand:** `script.json` is plain JSON, and editing it directly
  works well. Each scene is `{ id, narration, actions, pause? }`; the verbs
  are listed in `PROMPT.md`. Only changed narration is sent to ElevenLabs
  again.
- **Using Claude Code instead of step 1:** ask "follow web/demo/PROMPT.md to
  update web/demo/script.json", then run steps 2–3.
- **Voice:** set `"voice"` in `script.json`, or pass `--voice <id>` or set
  `ELEVENLABS_VOICE`. The default is a stock ElevenLabs voice.
- **Length:** the run stops if the narration is over 5 minutes
  (`--max-seconds 300`; `--force` to override). The finished length is
  printed and written to `out/timing.json`.
- **When an action fails:** the run stops and saves
  `out/failed-<scene>.png`, showing the screen at that moment. Fix the action
  (usually a selector or a menu item) and run again.

## How it works

1. Each scene's narration becomes an MP3, and its length sets the scene's
   minimum duration.
2. A fresh browser runs the app from a private dev server (port 5321). A
   visible cursor and the title and caption overlays are injected, and each
   scene's actions run while the scene's narration time elapses. Scene start
   times are noted.
3. ffmpeg trims the loading time and places each clip at its scene's start
   (`adelay` + `amix`). It encodes H.264/AAC at 1600×900 and writes an SRT
   caption file from the narration.

The recorder reads node positions through `window.__guess`, which the app
exposes only in the dev server.
