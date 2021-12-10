FROM python:3.9

# Install git and ruby.
RUN apt-get update -qq && apt-get install -qqy git ruby-full

RUN mkdir /test
WORKDIR /test
CMD ["cucumber"]

RUN gem install contracts -v 0.16.1; gem install cucumber -v=2.3.2; gem install aruba -v=0.14.0

# "Install" hooks.
ADD hooks /usr/share/hooks
COPY git-hooks-test /test
RUN cucumber
