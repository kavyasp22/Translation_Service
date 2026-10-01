FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

EXPOSE 9045

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "9045"]
