# The GUESS manual

`MANUAL.md` is the user manual: the 2006 GUESS manual's structure (features,
tutorial, data formats, queries, layouts, analysis, modifying graphs, output,
subgraphs, states, legends and hulls, extending the interface) brought up to
date for the web version, plus chapters on direct manipulation, the console
and undo, and sharing/deploying.

## Building

```sh
python3 docs/manual/build.py              # PDF, HTML, EPUB, Word and index.html into docs/manual/build/
python3 docs/manual/build.py pdf html     # just these
```

Needs [pandoc](https://pandoc.org) 3 and, for the PDF, XeLaTeX (MacTeX or
TeX Live). The build adds two generated appendices so they can't go stale:
the colour table (from `py/guess/colors.py`) and the command reference
(from `docs/API.md`; regenerate that with `py/tools/gen_api_docs.py`).
The deploy scripts (`npm run build`, `npm run bundle`, CI's GitHub Pages job)
copy the index and the four formats to `manuals/` on the site, which
*Help → Manual* opens (`web/scripts/copy-manuals.mjs`).
Any other pandoc output works from the assembled file,
`docs/manual/build/GUESS-manual.md`.

## Keeping it correct

- **Examples.** Every ```` ```python ```` block is run against GUESS, chapter by
  chapter, on the sample graph (`py/tests/test_manual_doc.py`, or
  `cd py && .venv/bin/python ../docs/manual/tools/check_examples.py`). Mark
  a block ```` ```{.python .norun} ```` if it can't run there (network, files).
- **Figures.** `img/*.png` come from `cd web && npm run manual-shots`
  (`web/demo/manual-shots.mjs`; `npm run manual-shots -- hive fa2` redoes
  some). The gesture pictures in chapter 13 are the in-app ones from
  `web/public/help` (`npm run help-shots`).
