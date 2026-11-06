# Publishing the Forever player addon

`.github/workflows/publish-forever.yml` verifies the addon, builds the player-only ZIP and uploads an Alpha to the existing CurseForge project **1783290**. It never includes RBGSCompatibility or the TBC TOC. CurseForge still manages approval and availability.

## One-time setup

1. Generate an author upload token using the API Tokens link in [CurseForge's Upload API guide](https://support.curseforge.com/support/solutions/articles/9000197321-curseforge-upload-api). The token's account must be able to upload to rbgs.io.
2. In [the repository's Actions secrets](https://github.com/gallardoS/addon.rbgs.io/settings/secrets/actions), add a repository secret named **CF_API_KEY** containing that token. Do not put it in code, a variable, the changelog or chat.
3. Commit the release workflow, package/release scripts, their tests, CHANGELOG.md, the product version/TOC metadata and the releases ignore rule; push to main. Probe changes can remain a separate commit. No GitHub write token, tag or automatic version commit is required.
4. Check **Actions → Publish Forever addon**. The generated ZIP, changelog and release metadata are downloadable as an artifact even if publication fails. Successful publication reports the CurseForge file ID in the run summary. Check the project's Files page for approval status.

## Normal behavior

- Pushes to main affecting `rbgs.io/**`, release tooling/workflow, CHANGELOG.md or LICENSE run verification, packaging and publication. Debugger-only or README-only changes do not publish.
- Pull requests verify and build without publishing or accessing the token.
- Manual **Run workflow** builds by default. Select main and enable **publish** to upload manually.
- Versions use the TOC's numeric base plus `-alpha.<run_number>.<run_attempt>`; e.g. `0.2.1-alpha.73.1`. Reruns produce a new version. The packaged TOC and capture addonVersion match; source files are not rewritten or committed by CI.
- The target game version is 1.60.1, restricted to CurseForge's Forever game-version type 88568. The uploader resolves the exact numeric game-version ID from the live author API and fails if it is missing/ambiguous; it never substitutes TBC or another patch. Update the explicit target in prepare_release.py and review the TOC interface check when game compatibility changes.
- CHANGELOG.md provides the maintained release notes, with generated version and source SHA prepended. Keep its content current as product functionality changes.
- Upload POSTs are not automatically retried: after a lost reply, check Files before rerunning to avoid duplicate publication. Missing/invalid tokens fail visibly after the ZIP artifact has been saved.

Local packaging only: `python tools/package_forever.py`. Local release-tool tests: `python -m unittest discover -s tools -p test_release.py`. Never use a real upload token in tests.
