# Project workflow

This repository is the canonical source for Fajny Print Studio.

- Repository: https://github.com/pidiman/stitky; default branch: main.
- Make future project changes in this repository, preserving its existing Git history and unrelated work.
- After completing requested changes, run relevant checks, review the diff, commit the intended files and push to GitHub. The user has authorized this ongoing workflow; do not ask again for routine commits and pushes. Do not force-push or discard unrelated changes.
- If Git authentication is unavailable, use the connected GitHub tools when possible, synchronize the local history afterward, and report any remaining failure clearly. Never claim a push succeeded without verifying the remote result.
- This repository is public. Keep production configuration in ignored local environment/configuration files. Never commit credentials, databases, logs, production acceptance records, private infrastructure addresses or real device identifiers. Preserve example configuration in tracked files.
- Do not deploy, flash hardware or print physical labels solely as part of saving changes to GitHub.
