# Release artifacts

## Rule: release zip must contain only git-tracked files

To keep releases deterministic and avoid diff-noise, the release artifact **must** be built from the git index, not from a working directory snapshot.

Use:

```bash
bash scripts/build_zip_from_git.sh
```

This script generates a zip using `git ls-files`, so untracked Python artifacts like `__pycache__/` and `*.pyc` can never leak into a release.

## Do not do this

- Do not `zip -r` the folder.
- Do not package from an extracted directory (it has no `.git` index).

## Python artifact hygiene

Even though the release build uses git-tracked files, keep the working tree clean:

```bash
find . -type d -name '__pycache__' -prune -exec rm -rf {} +
find . -type f -name '*.pyc' -delete
```

## When you don't have a git checkout

If you are running from a directory that is not a git repo (e.g., a copied tree), first clean Python artifacts, then use a git checkout for the actual release build.

```bash
bash scripts/clean_python_artifacts.sh
```
