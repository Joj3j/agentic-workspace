Your job is to create a merge request (MR) for any new changes in the current repo.

**Terminal (mandatory):** All git commands (branch, add, commit, push) must run in the **existing IDE terminal** only. Do **not** run any git command in a sandbox or isolated shell. If your only available shell is sandboxed, do **not** run git there—instead, output one copy-pastable block of git commands for the user to run in their IDE terminal (include `cd` to repo, then branch/add/commit/push as needed). Do not create a new terminal.

1. **Branch:** If there is no feature branch yet, create one from `master` (or the repo's default branch). Use a short, descriptive name (e.g. `fix/config-loading`, `feat/add-metrics`). If git username is known, use branch pattern `<username>/<branchname>`. Run in IDE terminal only.
2. **Commit:** Ensure all intended changes are committed before creating the MR. If there are uncommitted changes, ask the user to confirm what to commit or do it per their instructions. Use only `git add <paths> && git commit -m "message"`—do **not** use `--trailer` or `Co-authored-by`. Example: `git add test/scripts/test.md && git commit -m "docs: update test scripts doc"`. Run in IDE terminal only.
3. **Push:** Run in the **IDE terminal** only: first-time push `git push --set-upstream origin <branch>`, otherwise `git push`. If you cannot run in the IDE terminal, output the exact push command(s) for the user to run there.
4. **MR:** Create the merge request in the repo's Git hosting UI (or run the host's CLI if available). Describe the change clearly in the MR title and description.
5. **Open / Publish:** Use the MR link to publish the MR or open it in a browser to publish. Use an existing terminal or log in as the user as needed. Assign the MR to the git username.
6. **Update MR:** Set the MR title/header to a short summary of the change. Set the MR description to the full contents (changelist, what changed, and why).

Work in the repo that is in scope; do not assume a specific remote or host—use the repo’s current git config and conventions.
