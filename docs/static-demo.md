# 🌐 Static demo on GitHub Pages

The project page and the recorded tour of all 17 scenes need no API, GPU or Unity: they read only the files in `web/public/` (tour videos, decision logs, thumbnails, `results.json`). `npm run build:static` builds just that, and [`.github/workflows/pages.yml`](../.github/workflows/pages.yml) can publish it to GitHub Pages.

> [!IMPORTANT]
> **It is off.** The workflow only runs when someone starts it by hand, and nothing is published until then. A Pages site is public even when the repository is private, and Pages for a private repository needs a paid GitHub plan.

## What is in it

| Works | Does not work (needs the local API) |
|---|---|
| Project page, measured results, camera angles | **Open the lab**: live lane, decisions, models, benchmark and training tabs |
| **Watch the 17 scenes**: every recorded tour run, with its cart and decisions | Replaying recorded frames through the models, the WebGL scene |

The static build skips the API connection entirely, so there are no failing requests in the browser console. The site is about 90 MB, all of it files already in `web/public/`; nothing new is committed or downloaded.

## Switch it on

1. On GitHub, open **Settings → Pages** for the repository and set **Build and deployment → Source** to **GitHub Actions**.
2. Open **Actions → Static demo (GitHub Pages) → Run workflow** on `main`.
3. When the run finishes, the site is at `https://dangermos.github.io/ProPass/`. The URL is also shown on the run's **deploy** job.

Run the workflow again after the tour or results change. To take the site down, use **Settings → Pages → Unpublish site** (or set the source back to none).

## Try it locally first

```bash
cd web
npm run build:static -- --base=/ProPass/   # the same build the workflow makes
mkdir -p /tmp/pages && ln -sfn "$PWD/dist" /tmp/pages/ProPass
python3 -m http.server 8765 --directory /tmp/pages   # open http://127.0.0.1:8765/ProPass/
```

Static files are loaded through `asset()` in [`web/src/assets.ts`](../web/src/assets.ts), which prefixes Vite's base path: `/` for `npm run dev` and the normal build, `/ProPass/` on Pages.
