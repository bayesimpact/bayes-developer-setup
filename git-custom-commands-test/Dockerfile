FROM lascap/aruba-test

# Install git.
RUN apt-get update -qq && apt-get install -qqy git

# "Install" git-submit.
ADD bin /usr/bin
COPY git-custom-commands-test /test
RUN cucumber
