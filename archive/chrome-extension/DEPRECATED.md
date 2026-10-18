# Archived: FaultRay Cloud Setup Assistant (Chrome extension)

Imported with its history from `mattyopon/faultray-chrome-extension`
(main @ e8b9eca) when the FaultRay repositories were consolidated. It is kept
for reference only and is **not maintained**:

- It does not work against faultray.com. It opens `/auth/signin` (404; sign-in
  lives at `/login`) and posts long-lived AWS access keys to
  `POST /api/cloud-credentials`, which was never implemented. The app's AWS
  discovery accepts a cross-account role ARN instead and rejects long-lived
  keys (`apps/web/api/engine.py`, APIVULN-01).
- No Chrome Web Store listing for it was found.
- Nothing here is built, linted or tested in CI, it is excluded from the PyPI
  sdist and the Docker build context, and no Dependabot version-update entry
  covers it. If Dependabot alerts are enabled for this repository they still
  scan its package-lock.json; dismiss those alerts or delete the lockfile.

Its README declares the MIT license; the rest of this repository is Apache-2.0.
If the setup assistant is revived, rebuild it around the role-ARN flow and
move it out of `archive/` together with a CI workflow.
