FROM lascap/aruba-test

# Install git.
RUN apt-get update -qq && apt-get install -qqy git

# "Install" git-submit.
ADD git-submit /usr/bin/
