# Deploying

GUESS is a static site: HTML, JavaScript, CSS and (optionally) the Pyodide
runtime. Any web server, object store or static host can serve it, from the
root or any sub-path (all URLs are relative).

## Make a bundle

```sh
cd web
npm install
npm run bundle                 # Pyodide from the jsDelivr CDN (≈ 0.5 MB bundle)
npm run bundle -- --offline    # Pyodide included (≈ 18 MB; no CDN at run time)
npm run bundle -- --out /tmp/x # choose the output folder (default web/bundle)
```

Each run produces, under `web/bundle/`:

```
guess-web-<version>[-offline]/          ← upload the contents of this folder
  index.html, assets/, coi-serviceworker.js, examples/
  manuals/                              the manual (index, HTML, PDF, EPUB, Word): Help → Manual
  pyodide/                              (offline bundles only)
  .htaccess, _headers                   Apache / Netlify / Cloudflare Pages headers
  nginx.conf.example, Caddyfile.example server config templates
  VERSION.txt
guess-web-<version>[-offline].zip       the same folder, zipped
guess-web-<version>[-offline].tar.gz
```

The online bundle downloads Pyodide, numpy and networkx (~25 MB, cached by the
browser) from `cdn.jsdelivr.net` on first use. Use `--offline` for intranets,
air-gapped machines, or to avoid depending on the CDN; offline downloads are
cached in `web/.pyodide-cache/`.

The manual comes from `docs/manual/build/`. The bundle builds it first if it
is missing (pandoc 3 and XeLaTeX); without it the site works but Help → Manual
has nothing to open.

`npm run build` alone writes the site to `web/dist/` (with `manuals/` if the
manual has been built) without the server files or archives. This is what CI
publishes to GitHub Pages; the deploy job builds the manual first.

## Put it on a server

Copy the folder's contents to the document root (or a sub-directory), e.g.

```sh
scp -r web/bundle/guess-web-0.1.0/. user@host:/var/www/guess/
# or unpack the archive on the server
unzip guess-web-0.1.0.zip && rsync -a guess-web-0.1.0/ /var/www/guess/
```

### Headers (recommended)

To interrupt running Python (Stop button, Esc) the page must be
*cross-origin isolated*, which needs two response headers:

```
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

- **Apache**: the bundled `.htaccess` sets them (needs `mod_headers` and
  `AllowOverride FileInfo` or `All`). It also sets the `.wasm`/`.mjs` MIME types.
- **nginx**: see `nginx.conf.example`.
- **Caddy**: see `Caddyfile.example`.
- **Netlify / Cloudflare Pages**: the bundled `_headers` file is picked up automatically.
- **GitHub Pages, S3, plain file servers** can't set headers. That's fine:
  `coi-serviceworker.js` installs a service worker that adds them, after one
  automatic reload on the first visit. (Service workers need HTTPS or
  `localhost`.)

Without isolation everything still works except interrupting Python (the
Stop button is disabled and Esc explains why).

### MIME types

The server must send `application/wasm` for `.wasm` and a JavaScript type for
`.mjs` (offline bundles). Most servers already do; the templates set them.

### Caching

`assets/` file names contain content hashes and `pyodide/` files are
versioned, so both can be cached for a long time. Don't cache `index.html`
aggressively, so new releases are picked up.

## Check a deployment

Open the site and wait for "loaded 402 nodes" in the console, then run
`graphStats()`. In DevTools' console, `crossOriginIsolated` should be `true`
(after the one-time reload when relying on the service worker). For a quick
local test of a bundle:

```sh
cd web/bundle && python3 -m http.server 8000
# open http://localhost:8000/guess-web-0.1.0/
```

## Opening data and apps by URL

- `?load=<url>` opens a graph (`.gdf`, `.gexf`, `.graphml`, `.net`, `.dl`,
  `.csv`), a session (`.guess`) or runs a `.py` script on startup. The URL may
  be relative to the site (put files next to `index.html`) or on another
  server that allows CORS.
- `&app=1` hides the console and editing tools, for published "apps": build
  one with `exportApp("app.guess", "ui.py")` and link to
  `index.html?load=app.guess&app=1` (example: `examples/demo.guess`).

## GitHub Pages (CI)

`.github/workflows/ci.yml` runs the Python and browser tests on every push.
Publishing to GitHub Pages is off by default. To turn it on, set Pages'
source to "GitHub Actions" in the repository settings and add a repository
variable `DEPLOY_PAGES` = `true` (Settings → Secrets and variables → Actions →
Variables). Pushes to `main` then build the manual and `web/dist` and publish
them with `actions/deploy-pages`.

## Privacy and security notes

All computation happens in the visitor's browser; graphs and code are never
uploaded. Autosave uses the browser's IndexedDB for that site. Gython is full
Python running in the browser sandbox, so users can only affect their own page.
Loading third-party URLs with `?load=` fetches them from the visitor's browser.
