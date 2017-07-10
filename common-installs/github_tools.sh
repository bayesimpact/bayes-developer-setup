#!/usr/bin/env bash
#
# A script to install git add-ons.

readonly SHELLRC="${HOME}/.${SHELL#/bin/}rc"

# Propose useful github addons.
read -p "Would you like to add git-completion and git-prompt, two useful git tools? " -n 1 -r
echo # Add a blank line.
if [[ $REPLY =~ ^[Yy]$ ]]; then
  if grep -F "git-completion" $SHELLRC; then
    echo 'Looks like these tools are arleady installed !'
  else
    curl https://raw.githubusercontent.com/git/git/master/contrib/completion/git-completion.bash > $SHELLRC
    curl https://raw.githubusercontent.com/git/git/master/contrib/completion/git-prompt.sh > $SHELLRC
    echo '# Git tools.' >> $SHELLRC
    echo 'source ~/.git-completion.sh' >> $SHELLRC
    echo 'source ~/.git-prompt.sh' >> $SHELLRC
    echo "export PS1='\[\033[0;94m\]\W $(__git_ps1 " (%s)")$ \[\033[0m\]'" >> $SHELLRC
    source $SHELLRC
  fi
fi