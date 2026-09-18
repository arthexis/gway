map $http_upgrade $backend {
    default 127.0.0.1:8888;
    websocket 127.0.0.1:9999;
}

server {
    server_name arthexis.com *.arthexis.com;

    location / {
        proxy_pass http://$backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    listen 443 ssl;
    ssl_certificate /etc/letsencrypt/live/arthexis.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/arthexis.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
}

server {
    listen 80;
    server_name arthexis.com *.arthexis.com;
    return 301 https://$host$request_uri;
}

