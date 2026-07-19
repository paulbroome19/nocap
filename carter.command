#!/usr/bin/env bash
#
# carter.command — double-clickable launcher for Carter (macOS Finder → Terminal).
#
# Copy this file to your Desktop (or anywhere) and double-click it to start
# Carter. It just points at the repo and runs run-carter.sh; edit CARTER_REPO
# below if you move the repository.
#
CARTER_REPO="/Users/paulbroome/Desktop/Dev/NOCAP"

if [ ! -x "${CARTER_REPO}/run-carter.sh" ]; then
  echo "Carter isn't where this launcher expects it:"
  echo "  ${CARTER_REPO}/run-carter.sh"
  echo
  echo "Edit CARTER_REPO at the top of this .command file to point at your"
  echo "Carter repository, then try again."
  echo
  read -r -n 1 -s -p "Press any key to close this window."
  exit 1
fi

cd "$CARTER_REPO" || exit 1
"./run-carter.sh"

echo
echo "Carter has stopped."
read -r -n 1 -s -p "Press any key to close this window."
