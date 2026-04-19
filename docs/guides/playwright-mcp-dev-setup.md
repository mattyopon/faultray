# Playwright MCP — sudo-less developer setup

> **Audience:** FaultRay maintainers using Claude Code / CC in a WSL2 or
> otherwise-unprivileged environment who need the Playwright MCP server
> for browser-based validation (Phase 0 / Phase 1 of the dashboard work).
>
> This guide exists because the 2026-04-17 Phase 0 baseline validation
> hit a wall: the default Playwright MCP configuration expects Chrome
> at `/opt/google/chrome/chrome` which requires `sudo` to install, and
> our dev environment doesn't grant sudo.

## Symptom

After configuring `@playwright/mcp` in your Claude Code / MCP client
(e.g. via `.mcp.json` with `"command": "npx", "args": ["@playwright/mcp@latest"]`),
any `browser_navigate` / `browser_snapshot` call fails with:

```
Error: server: Chromium distribution 'chrome' is not found at
  /opt/google/chrome/chrome
Run "npx playwright install chrome"
```

`npx playwright install chrome` fails because it tries to run `apt-get`
through sudo:

```
Switching to root user to install dependencies...
sudo: a password is required
Failed to install browsers
```

## Workaround — reuse Chrome for Testing that `@playwright/test` ships

Playwright's Node package (`@playwright/test`) bundles its own
**Chrome for Testing** build under `~/.cache/ms-playwright/`.
That binary works standalone; the only reason the MCP can't find it
is that the MCP's default browser channel is `chrome`, which resolves
to the system Chrome path.

### Step 1 — install the Playwright Node package (no sudo)

```bash
cd <any-project-with-node>
npm install --save-dev @playwright/test
npx playwright install chromium
```

This pulls Chrome for Testing into `~/.cache/ms-playwright/chromium-<rev>/chrome-linux64/chrome`.
Verify:

```bash
ls ~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome
# /home/<user>/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome
```

### Step 2 — point the MCP at that binary with `--executable-path`

The MCP server accepts `--executable-path <path>` to override the
browser binary.  Edit your MCP config (wherever your client reads
`.mcp.json`) to include the flag:

```json
{
  "playwright": {
    "command": "npx",
    "args": [
      "@playwright/mcp@latest",
      "--executable-path",
      "/home/<user>/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome"
    ]
  }
}
```

Substitute the actual chromium revision directory (`chromium-1208`
was the revision at the time this guide was written; it changes with
each `@playwright/test` bump).

**Restart the MCP server** (in Claude Code: `/mcp reload` or restart
the CLI) after editing.

## Fallback — direct Playwright script

If you can't modify the MCP config (e.g. on a managed harness), run a
tiny Node script that drives Playwright directly, bypassing the MCP:

```js
// capture-with-chromium.js
const { chromium } = require('playwright');

const EXECUTABLE = '/home/user/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome';

(async () => {
  const browser = await chromium.launch({
    executablePath: EXECUTABLE,
    headless: true,
  });
  const page = await browser.newPage();
  await page.goto('http://localhost:3000/whatif');
  await page.screenshot({ path: 'whatif.png' });
  await browser.close();
})();
```

Run with `node capture-with-chromium.js`.  This is the path we used
during Phase 0 Task 6 when the MCP was unreachable.

## Why this isn't "fixed upstream"

The `@playwright/mcp` package defaults to the `chrome` channel because
that's what most users want (system Chrome integrates with their
existing profile / extensions).  Adding an automatic fallback to the
bundled Chrome for Testing would be a reasonable upstream PR but
hasn't been proposed yet.

## Related

- Phase 0 validation report — Phase 1 candidate #12
  (`docs/phase0-validation-report.md`)
- Issue #75 — "docs: Playwright MCP sudo-less setup via --executable-path"
