FROM lascap/aruba-test

# Install git.
RUN apt-get update -qq && apt-get install -qqy git

# "Install" git-submit.
ADD bin/git-submit /usr/bin/
