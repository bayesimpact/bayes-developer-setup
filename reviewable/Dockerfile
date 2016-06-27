FROM node:4-onbuild

COPY ./package.json .
RUN npm install

CMD ["npm", "run", "test"]
