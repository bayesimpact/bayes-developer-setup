#!/usr/bin/env bash
#
# A script to install git add-ons.

readonly SHELLRC="${HOME}/.${SHELL#/bin/}rc"
readonly NAME='bayes-developer-setup'
readonly DIR="${HOME}/.${NAME}"

echo "(Re)-creating ${DIR}"
mkdir -p "${DIR}"
cd "${DIR}"

# Track changes.
change=false

# Propose useful Github addons.

# git-completion.
# Check if complete tools have already been installed for git.
if echo $(complete | grep " git$"); then
  echo 'Looks like completion tools are arleady installed for git!'
else
  read -p "Would you like to add git-completion? " -n 1 -r
  echo # Add a blank line.
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo '# Git tools.' >> $SHELLRC
    change=true
    curl https://raw.githubusercontent.com/git/git/master/contrib/completion/git-completion.bash > $DIR/bin/.git-completion.sh
    echo 'source $DIR/bin/.git-completion.sh' >> $SHELLRC
    readonly PS1_COMMAND='\[\033[0;94m\]\W $(__git_ps1 " (%s)")$ \[\033[0m\]'
    echo export PS1=\'$PS1_COMMAND\' >> $SHELLRC
  fi
fi

# git-prompt.
# TODO - Add a way to check if already installed.
read -p "Would you like to add git-prompt, a useful git tools showing which branch you are on? " -n 1 -r
echo # Add a blank line.
if [[ $REPLY =~ ^[Yy]$ ]]; then
  if [[ "$change" != true ]]; then
    echo '# Git tools.' >> $SHELLRC
    change=true
  fi
  curl https://raw.githubusercontent.com/git/git/master/contrib/completion/git-prompt.sh > $DIR/bin/.git-prompt.sh
  echo "source $DIR/bin/.git-prompt.sh" >> $SHELLRC
fi

# If changes were made, source shell script.
if [[ "$change" == true ]]; then
  source $SHELLRC
fi
