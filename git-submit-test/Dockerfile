FROM ruby:2.2.3

RUN apt-get update -qq && apt-get install -qqy git

RUN mkdir /test
WORKDIR /test

RUN gem install cucumber -v=2.3.2
RUN gem install aruba -v=0.14.0

ADD git-submit /usr/bin/

CMD ["cucumber"]
