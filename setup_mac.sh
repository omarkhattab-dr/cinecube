#!/bin/bash
# setup_mac.sh - first time setup on my mac: venv, tests, git, github
#
#   cd /Users/omarkhattab/Documents/VIZA701/cinecube
#   bash setup_mac.sh
#
# steps 1-3 always run. step 4 (github) only if gh is installed and logged in
# (brew install gh; gh auth login). ARASH=<his github username> adds him as collaborator
set -e
cd "$(dirname "$0")"

echo "== 1. python env"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "== 2. tests (first one is the equivalence test)"
python -m pytest -q tests

echo "== 3. git"
if [ ! -d .git ]; then
  git init -b main
  git add -A
  git commit -q -m "first version"
  echo "   git init + first commit done"
else
  echo "   already a git repo"
fi

echo "== 4. GitHub"
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  if ! git remote get-url origin >/dev/null 2>&1; then
    gh repo create cinecube --private --source=. --remote=origin --push
  else
    git push -u origin main
  fi
  if [ -n "$ARASH" ]; then
    OWNER=$(gh api user --jq .login)
    gh api -X PUT "repos/$OWNER/cinecube/collaborators/$ARASH" -f permission=push >/dev/null && echo "   invited $ARASH"
  fi
  echo "   repo: $(gh repo view --json url --jq .url)"
else
  echo "   gh not installed or not logged in. once:"
  echo "     brew install gh && gh auth login"
  echo "   then rerun bash setup_mac.sh  (or make the repo on github.com and run:"
  echo "     git remote add origin git@github.com:<you>/cinecube.git && git push -u origin main)"
fi

echo "== done. next: make smoke, make all, overleaf (see README)"
