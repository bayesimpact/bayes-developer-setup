FROM node:11

CMD ["npm", "run", "test"]

WORKDIR /usr/src/app

COPY ./package.json .
RUN npm install

COPY .eslintrc.json lgtm_plus_resolved_discussions.js ./
COPY test/lgtm_plus_resolved_discussions_spec.js test/

RUN npm run test
RUN npm run lint
