# Profile design & automation

This repository is the public GitHub profile for **Tanver Islam Tonmoy**. The README is a small product portfolio, not a hosted JavaScript website.

## Files

```text
README.md                         GitHub-compatible content and navigation
assets/hero.svg                   Original animated desktop composition
assets/hero-mobile.svg            Readable mobile composition
assets/vaultzero.svg              Original project illustration
assets/math-academy.svg           Original project illustration
assets/petshop.svg                Original project illustration
profile-3d-contrib/
  profile-night-rainbow.svg        Generated public contribution city; included now
scripts/render_contributions.py   Standard-library Python renderer
.github/workflows/
  profile-3d.yml                   Scheduled/manual generation and publishing
  check-profile.yml               Read-only PR/push checks
tests/                            Offline unit and profile-integrity tests
```

The SVG project illustrations are **not product screenshots**. Their labels and shapes introduce the work; the README links to the implementation. Availability, user counts, performance benchmarks and an independent security audit are not invented.

## Rendering on GitHub

- README content uses supported Markdown/HTML, ordinary links and local images. It does not depend on README scripts, inline CSS, canvas, remote badge APIs or stats services.
- Custom CSS animation is inside the standalone SVG images, not in the README. GitHub/browser rendering and image caching can vary. The assets remain readable when animation is unavailable.
- `<picture>` selects the mobile hero at a viewport up to 640px. The default `<img>` is still a complete desktop fallback.
- All animated images include `prefers-reduced-motion: reduce`. No information relies on an animation completing.
- GitHub's native heading anchors power the navigation. Tables use GitHub's standard rendering, including its small-screen scroll behavior.
- Keep `tonmoycoder/tonmoycoder` **public** if you want the special profile README and its relative images to be visible to public visitors.

## The 3D contribution city

The city is a custom renderer in this repository, **not** a third-party contribution action or copied SVG. It uses only Python's standard library (Python 3.10 or later).

```bash
# Refresh from the unauthenticated, publicly visible GitHub calendar.
python3 scripts/render_contributions.py --username tonmoycoder

# Run all checks; no network or third-party packages required.
python3 -m unittest discover -s tests -v

# Optional: reproduce a render offline from saved public calendar HTML.
python3 scripts/render_contributions.py --input /path/to/calendar.html
```

### Data and visual meaning

The renderer fetches `https://github.com/users/tonmoycoder/contributions` without an Authorization header. It does not query private repositories or retrieve their content. The calendar can include anonymized counts that the account owner has chosen to make publicly visible; the renderer only sees the same public calendar fragment.

- Every building is a real calendar day, including zero-activity days.
- Height is **logarithmically scaled** by that day's contribution count relative to the busiest day in the current calendar.
- Color follows GitHub's public `data-level` value.
- Window-light animation is decorative; heights and counts are never randomized or animated into fake activity.
- The summary and date range are taken from the fetched data, not from a hardcoded count or a claimed live connection.
- Output is deterministic. Identical input produces identical SVG and no new commit.

The public HTML format is not a versioned API. If GitHub changes its markup, rate-limits a request, returns an error, or omits counts/dates, generation **fails instead of fabricating a calendar**. A validated result is written atomically; the last good committed image remains visible. See a failed run in Actions and update the parser if necessary.

## Token and permission model

**No personal access token is needed, generated or stored. Do not paste one into this repository.**

```yaml
GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

That is a reference to GitHub's automatic per-job token, not its literal value. GitHub creates the repository-scoped token for the job and expires it when the job finishes (or its maximum lifetime is reached). A visitor reading the workflow cannot read the token's value from this expression. Authorized code running inside a job can still use its permissions, so the workflow is deliberately narrow:

- The publishing workflow runs only on **schedule** or **manual dispatch**, never on a pull request or push.
- It requests only `contents: write`, at the publishing job. No broad PAT, organization permission, package permission or identity-token permission is requested.
- The only external action is GitHub's official `actions/checkout`, pinned to full SHA `3d3c42e5aac5ba805825da76410c181273ba90b1`. This was verified against upstream **v7.0.1**, not guessed from a tag label.
- Checkout does not persist credentials. The renderer receives no publishing-token environment variable and performs an unauthenticated request.
- The publishing token is passed to `gh`'s credential helper only in the Git commit/push step; it is not put in a remote URL, printed, or saved to Git config.
- Only `profile-3d-contrib/profile-night-rainbow.svg` is staged. There is no force push. A concurrent non-fast-forward change fails safely instead of overwriting another edit.
- PR/push validation is a **separate, read-only workflow**. It receives no publishing-token environment variable and never commits.

Scheduled refresh is approximately **00:25 Asia/Dhaka** (`18:25 UTC` on the previous day). GitHub schedules can be delayed, run only from the default branch, and can be disabled after prolonged public-repository inactivity.

## Making it live

1. Review and merge the profile changes into the repository's **default branch**. A README on a working branch is not the live special profile README yet.
2. In **Actions → Render 3D contribution city**, choose **Run workflow** for the default branch to verify the first hosted refresh. A good initial SVG is already committed, so there is no broken image while waiting.
3. The workflow publishes back to the branch that is actually running it. No separate output branch or personal token is needed.
4. If an organization/repository policy forbids Actions writes, inspect the failed run and ask the repository owner to permit this workflow's explicit `contents: write` request. Do not create a broad PAT to bypass the policy. A blanket change to all workflows' default permissions is not required by this design.
5. If branch rules prohibit direct bot commits, do not weaken those rules blindly. Use a review/PR publishing policy or refresh locally and include the resulting SVG in a normal reviewed change.

GitHub can cache images. An existing SVG can remain briefly after a successful commit; a profile refresh does not necessarily invalidate every proxy immediately.

Profile pins are a **separate GitHub account setting**, not controlled by this README. Suggested first pins are VaultZero, the pet CMS platform and Math Academy. No repository visibility, pins, credentials or security settings are changed by these files.

## Keeping the content honest

- VaultZero is described as active-development, security-sensitive work—not certified or independently audited software.
- Math Academy links to source and deployment notes rather than asserting unverified current production uptime.
- The pet project is called a catalogue/enquiry platform; a completed payment/order system is not claimed.
- Earlier course projects are labelled as learning work and collapsed below the selected projects.
- The portfolio, resume and social links were carried over from the owner's profile. Their external availability must be checked by the owner; no API key is needed to display them.
