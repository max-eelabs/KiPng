# KiPng Release Guide

KiPng keeps a development snapshot on `main` between stable releases. A
snapshot uses a project version such as `0.1.0-SNAPSHOT` in [VERSION](VERSION)
and the numeric version `0.1.0` with `status: "development"` in
[metadata.json](metadata.json). A stable release uses `0.1.0` in both files,
`status: "stable"` in the metadata, and the Git tag `v0.1.0`.
[KiCad package metadata format](https://dev-docs.kicad.org/en/addons/index.html#metadata-file-format)

## Pull request naming

All changes to `main` go through reviewed pull requests. Push your changes
to a topic branch, open a PR targeting `main`, and merge it in GitHub after
review and required checks pass. Use these names for release PRs.

| Change | Branch | PR title |
| --- | --- | --- |
| Prepare a stable release | `release/v<version>` | `Prepare KiPng <version> release` |
| Start the next snapshot | `snapshot/<next-version>` | `Start KiPng <next-version> development` |

For other PRs, use a short action-oriented title that describes the change,
such as `Add a transparent background preset`. In a release PR, record the
version and smoke-test results.

## Build a snapshot

Each push to `main` builds the PCM ZIP and updates the same GitHub Packages
reference, `ghcr.io/max-eelabs/kipng-snapshot:latest`. The workflow verifies
the downloaded ZIP and deletes superseded, untagged versions of this package,
including when the project version changes. Git tags are for stable releases.

Download the current ZIP with [ORAS](https://oras.land/).

```sh
oras pull ghcr.io/max-eelabs/kipng-snapshot:latest
```

Select the resulting `KiPng-<version>-SNAPSHOT.zip` directly in
**Plugin and Content Manager → Install from File** on Windows, Linux, or macOS.
After the first publication, set the package visibility to **Public** in
GitHub package settings to enable anonymous downloads.

To rebuild manually, open **Actions → Build KiPng snapshot → Run workflow**.
Choose `main` to refresh the package. Feature branch runs provide their
install-ready ZIP under **Artifacts** for testing.

On Windows, run `.\install.cmd` from the checkout root to build a local
snapshot in `dist/`. The Windows runner uses the same packager to assemble
one ZIP for all three platforms.

## Publish a stable release

KiPng's package identifier uses the reverse-DNS namespace for `max-eelabs.com`.
KiCad may ask for confirmation that the maintainer controls the domain.
[KiCad's namespace guidance](https://dev-docs.kicad.org/en/addons/index.html#namespacing-and-naming)

1. Choose the version and branch from the current `origin/main`. Run these
   commands in PowerShell.

   ```powershell
   $version = '0.1.0'
   git fetch origin main
   git switch -c "release/v$version" origin/main
   ```

2. Set [VERSION](VERSION) and `versions[0].version` in [metadata.json](metadata.json)
   to the chosen number. Set `versions[0].status` to `"stable"` in the metadata.
   Build with `.\install.cmd`.
   Install the same ZIP through PCM in KiCad 10.0 on Windows, Linux, and
   macOS. Open a board and use **3D Preview** to export a PNG on each platform.

3. Commit the release preparation and push the release branch.

   ```powershell
   git add VERSION metadata.json
   git commit -m "Prepare KiPng $version release"
   git push -u origin "release/v$version"
   ```

   Open **Prepare KiPng 0.1.0 release** against `main` and merge it after
   review and required checks pass. In **Actions**, wait for **KiPng CI** on
   `main` to succeed for the commit created by merging that PR. Copy its full
   SHA from the successful run.

4. Create an annotated tag on that SHA and push the tag ref. Confirm that
   `VERSION` and the metadata contain the chosen number and the metadata
   status is `"stable"`.

   ```powershell
   $releaseCommit = '<full SHA from the successful CI run on main>'
   git fetch origin main
   git merge-base --is-ancestor $releaseCommit origin/main
   if ($LASTEXITCODE -ne 0) { throw 'The release commit must be on origin/main.' }
   git show "${releaseCommit}:VERSION"
   git show "${releaseCommit}:metadata.json"
   ```

   ```powershell
   git tag -a "v$version" $releaseCommit -m "KiPng $version"
   if ($LASTEXITCODE -ne 0) { throw 'Could not create the release tag.' }
   git push origin "refs/tags/v$version"
   ```

5. Pushing the tag starts **KiPng release**, which creates the GitHub
   Release, attaches the assets, and publishes it. Wait for the workflow to
   pass before submitting to PCM. The [GitHub release](https://github.com/max-eelabs/KiPng/releases)
   contains `KiPng-<version>.zip`, `checksums.txt`, and `pcm-metadata.json`.
   Select the versioned ZIP asset directly in PCM's **Install from File** dialog.
   The workflow verifies the ZIP's SHA-256 by downloading it from the public
   URL recorded in `pcm-metadata.json`. The URL has this form.

   ```text
   https://github.com/max-eelabs/KiPng/releases/download/v0.1.0/KiPng-0.1.0.zip
   ```

   If uploading fails and leaves an incomplete draft, delete that draft while
   keeping the Git tag, then rerun the failed workflow job. Keep published
   tags and ZIPs intact. Ship corrections under a new patch version. [GitHub CLI release creation](https://cli.github.com/manual/gh_release_create)

## Submit to KiCad's official repository

1. Fork [KiCad's Package Metadata repository](https://gitlab.com/kicad/addons/metadata)
   and create a branch. For the first submission, copy the release's
   `pcm-metadata.json` to `packages/com.max-eelabs.kipng.preview/metadata.json`. Copy
   [the listing icon](resources/icon.png) from the tagged checkout alongside
   it as `icon.png`. The directory name must match the package identifier.
2. For an update, add the generated version entry to the existing package
   metadata and keep the earlier entries and their release URLs. Each entry
   carries `download_url`, `download_sha256`, `download_size`, and
   `install_size` for its tagged ZIP. These fields belong in the official
   repository listing. The ZIP keeps its own single-version metadata. The
   listing uses KiCad's v1-compatible `GPL-3.0` label. The ZIP and source
   identify KiPng's license as `GPL-3.0-or-later`. [KiCad v1 schema](https://gitlab.com/kicad/addons/metadata/-/blob/main/schema-v1.json)
3. Push the branch to your GitLab fork. When validation passes, add the
   temporary PCM repository URL from the GitLab build log in KiCad. Select
   KiPng in that repository and check **Download** and **Install**. Then open
   the merge request against KiCad's metadata repository. [KiCad submission workflow](https://gitlab.com/kicad/addons/metadata/-/blob/main/README.md#recommended-workflow)
4. Once the listing appears in the official PCM repository, verify
   **Download** on the package's **Repository** tab entry.

## Start the next snapshot

After the stable release workflow succeeds, branch from the current
`origin/main`.

```powershell
$nextVersion = '0.1.1'
git fetch origin main
git switch -c "snapshot/$nextVersion" origin/main
```

Set `VERSION` to the next version with the `-SNAPSHOT` suffix. In
`metadata.json`, set `versions[0].version` to the next numeric version and
`versions[0].status` to `"development"`.

```powershell
git add VERSION metadata.json
git commit -m "Start KiPng $nextVersion development"
git push -u origin "snapshot/$nextVersion"
```

Open **Start KiPng 0.1.1 development** against `main` and merge it after
review and required checks pass.
