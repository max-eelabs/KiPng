# Contributing to KiPng

## Sign off and sign every commit

By signing off a commit, you certify that you have the right to submit the
contribution under the applicable open-source license and agree to keep a
public record of your contribution and sign-off. Read the full [Developer
Certificate of Origin 1.1](https://developercertificate.org/) before signing.

Every commit in a pull request must include a DCO sign-off and a cryptographic
signature. Set your commit identity with `git config user.name` and
`git config user.email`, then configure a signing key. Use `git commit -s -S`.
The `-s` flag adds your name and email to the commit message. The `-S` flag
signs the commit with your configured key. [Git commit options](https://git-scm.com/docs/git-commit#_options)

```text
Signed-off-by: Your Name <you@example.com>
```

If your latest commit is missing either, run `git commit --amend --no-edit -s -S`
before pushing.

## Work on a feature branch

All changes to `main` go through reviewed pull requests. Start from the latest
`main` in the KiPng repository and use a short, descriptive branch name such
as `feature/transparent-background-preset`.

```sh
git fetch origin main
git switch -c feature/transparent-background-preset origin/main
# Make and stage your changes.
git commit -s -S -m "Add a transparent background preset"
git push -u origin feature/transparent-background-preset
```

If you work from a fork, fetch and branch from the upstream KiPng repository's
`main`, then push the branch to your fork.

Open a pull request targeting KiPng's `main` with a short, action-oriented
title. Describe what changed and how you verified it. Follow the project
conventions and run the checks in [AGENTS.md](AGENTS.md). Merge after review
and the required checks pass.

For release and snapshot branch names, tag creation, publishing, and KiCad
Plugin and Content Manager submission, see the [release guide](RELEASE.MD).
