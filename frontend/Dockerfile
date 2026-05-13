# ЭТАП 1: Сборка приложения
FROM node:20-alpine AS build

WORKDIR /app

# Копируем файлы зависимостей
COPY package*.json ./

# Устанавливаем зависимости
RUN npm install

# Копируем весь исходный код фронтенда
COPY . .

# Собираем проект в production режиме
RUN npm run build -- --configuration production

# ЭТАП 2: Раздача через Nginx
FROM nginx:stable-alpine

# Копируем билд из первого этапа в папку Nginx
COPY --from=build /app/dist/fusion-angular-tailwind-starter/browser /usr/share/nginx/html

# Копируем наш файл конфигурации Nginx
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Открываем 80 порт
EXPOSE 80

# Запускаем Nginx
CMD ["nginx", "-g", "daemon off;"]
