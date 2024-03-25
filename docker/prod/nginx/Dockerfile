FROM nginxproxy/nginx-proxy

ARG HOST_DOMAIN

COPY vhost.d/default_location.template /etc/nginx/vhost.d/default_location
RUN sed -i "s/{{domain}}/$HOST_DOMAIN/g" /etc/nginx/vhost.d/default_location

COPY custom.conf /etc/nginx/conf.d/custom.conf