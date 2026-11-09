# Prompt: write the GUESS demo video script

You are writing the script for a narrated screen-recording demo of GUESS for
the web. The output is `web/demo/script.json`, which `npm run demo` turns into
a video: each scene's `narration` is spoken by a text-to-speech voice while
the scene's `actions` drive the real app in a browser.

## Goals

- **Length:** at most 5 minutes in total, with about 2.5 spoken words a second
  (around 600–700 words of narration at most). Shorter is fine; 3–4 minutes
  is ideal.
- **Coverage:** show what GUESS is for and what makes it distinctive, not
  every feature.
  - Gython's graph operators.
  - Output linked to the graph.
  - Layouts and analysis.
  - Interface features that write code: panels, menus, dragging with meaning.
  - Help and search.
  - Sharing.
  - Feature some of what is newest (see "Recent changes" below) without
    turning the video into a changelog.
- **Story:** start from the motivation (why a language-driven graph tool),
  build from simple to powerful, and end with what people can do with their
  results.

## Voice and style

Write as the author of the CHI 2006 GUESS paper (excerpts below) speaking:
- First person plural ("we"), plain and direct, modest rather than
  promotional.
- Motivation before mechanism; concrete examples ("find every edge with a
  frequency over one hundred") rather than adjectives.
- Short spoken sentences, no marketing superlatives, no exclamation marks.
- Spell numbers and symbols the way they should be spoken: say "department
  three", not "dept3"; "colour it red", not "`.color = red`". British or
  American spelling is fine, but be consistent.

Each scene's narration should be 1–4 sentences, and its actions must fit in
roughly the time the narration takes. Narrate what the viewer sees as it
happens.

## The sample graph and what's safe to run

The app opens with the sample graph: 402 people (`v1` … `v402`), each with a
`dept` field (`dept`, `dept1` … `dept20`) and `jobfun`. Edges have `freq`
(email frequency) and `hierarchy`.

Only use commands that appear in the API reference below. Prefer short,
readable one-liners, because single-line `run` code is typed visibly on
screen. Avoid commands that print huge outputs: write
`cl = louvainClusters()`, not a bare `louvainClusters()`. After a layout that
flings isolated nodes away, use `center(giantComponent())`.

## Output format

Return only a JSON object, with no commentary, of the form:

```json
{
  "title": "GUESS for the web",
  "output": "guess-demo.mp4",
  "voice": "<keep the existing value>",
  "ttsModel": "<keep the existing value>",
  "pronounce": "<keep the existing value: spoken spellings, e.g. Gython → Guython>",
  "theme": "light",
  "setup": [ { "title": "GUESS", "subtitle": "…" } ],
  "scenes": [
    { "id": "short-kebab-id", "narration": "…", "actions": [ … ], "pause": 600 }
  ]
}
```

Each action is an object with exactly one of these verbs (plus the optional
modifiers shown):

| action | does |
|---|---|
| `{"run": "code"}` | types the code into the console and runs it (multi-line code is pasted); waits until it finishes |
| `{"wait": ms}` | pause |
| `{"title": "text", "subtitle": "text"}` / `{"title": ""}` | full-screen title card on / off |
| `{"caption": "text"}` / `{"caption": ""}` | a caption strip at the bottom on / off |
| `{"menu": ["View", "#btn-table"]}` | opens a menu and chooses an item (by element id or visible name); add `"close": true` to only point at it and close the menu |
| `{"click": "css selector"}` | moves the cursor there and clicks |
| `{"select": ["css selector", "value"]}` | chooses an option in a `<select>` |
| `{"fill": ["css selector", "text"]}` | clicks a text box and types into it |
| `{"key": "ControlOrMeta+k"}` | presses a key or shortcut (`F1`, `Escape`, `Enter`, …) |
| `{"typeKeys": "text"}` | types into whatever has focus (e.g. the search palette) |
| `{"hoverNode": "v128"}` | moves the cursor onto a node (shows its tooltip, highlights it) |
| `{"hoverOutput": "v4"}` | moves the cursor onto linked console output containing that text |
| `{"hoverText": ["css selector", "text"]}` | moves the cursor onto the last element matching selector and text |
| `{"dragNode": ["v1", "v14"], "alt": true}` | drags a node onto another (`alt`: draws a new edge) |
| `{"dragIntoGroup": "v128"}` | drags a node into the largest group of a different colour (after `colorize(field)`, this changes its field) |
| `{"zoom": 1}` / `{"zoom": -1}` | zooms in / out at the centre |

Useful selectors and menu items:
- Menus (title → items):
  - View: `#btn-table`, `#btn-style`, `#btn-filter`, `#btn-vars`, `#btn-timeline`, `#btn-present`, `#curved`.
  - Edit: `#undo`, `#redo`.
  - File: `#share-link`, `#export-notebook`, `#export-report`.
  - Help: `#btn-help`, `#btn-palette`.
- Filter panel: `#side-filter select` (values such as `s:kcore`,
  `n:dept`, `e:freq`), the add button `#side-filter .pf-form button`, and
  "Show all" `#side-filter .pf-actions button`.
- Style panel: `#side-style select` (in order: target, property, field), and
  `#side-style .pf-apply`.
- Help search box: `.help-search`. Chart slices: `.chart path.mark`.

Close panels you open (choose the same menu item again) so the screen stays
uncluttered.
