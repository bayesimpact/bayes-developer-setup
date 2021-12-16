FROM python:3.9

# Add bazel to apt.
RUN apt install apt-transport-https curl gnupg; \
    curl -fsSL https://bazel.build/bazel-release.pub.gpg | gpg --dearmor > /etc/apt/trusted.gpg.d/bazel.gpg; \
    echo "deb [arch=amd64] https://storage.googleapis.com/bazel-apt stable jdk1.8" | \
        tee /etc/apt/sources.list.d/bazel.list;

# Install bazel, git and ruby.
RUN apt-get update -qq && apt-get install -qqy bazel git ruby-full

RUN mkdir /test
WORKDIR /test
CMD ["cucumber"]

RUN gem install contracts -v 0.16.1; gem install cucumber -v=2.3.2; gem install aruba -v=0.14.0

# "Install" hooks.
ADD hooks /usr/share/hooks
COPY git-hooks-test /test
ARG SKIP_TEST=
RUN test -n "$SKIP_TEST" && echo "Skipping tests" || cucumber
