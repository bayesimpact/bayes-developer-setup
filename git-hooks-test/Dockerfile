FROM lascap/aruba-test

# Install git.
RUN apt-get update -qq && apt-get install -qqy git

# "Install" hooks.
ADD hooks /usr/bin
COPY git-hooks-test /test
RUN cucumber
