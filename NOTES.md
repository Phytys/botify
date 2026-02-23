# Those notes relate to serving Botify Arena on same VPS as wher I have "Echo" and "MuRP" installed.

NOTE: Those notes are written by the agent that works in the other repo where the other apps are served from.
----------------



Yes, you can run Botify Arena on the same VPS and keep it isolated. Here’s how.

---

## 1. Is it possible?

Yes. This is the same pattern you already use for Echo with `echo.resonancehub.app`: a separate nginx server block per subdomain.

**Domain note:** Your current setup uses `resonancehub.app`. If you want `botify.resonancehub.com`, add a DNS A record for the subdomain. For `botify.resonancehub.app`, add `botify` as a subdomain of your existing `.app` domain.

---

## 2. Isolation options

| Isolation level | How it works |
|-----------------|--------------|
| **URL/routing** | Separate subdomain (`botify.resonancehub.app`) and server block. No shared paths with MuRP or Echo. |
| **File system** | Own web root, e.g. `/var/www/botify/`. Botify Arena assets stay separate from MuRP/Echo. |
| **Process** | Own systemd units (e.g. `botify.service`) if it runs backend services. |
| **User** | Optional: dedicated `botify` user for its processes. |
| **No shared APIs** | Botify Arena does not need `/ann/` or `/emb/` unless you explicitly allow it. |

---

## 3. What to add on the VPS

### DNS

```
botify.resonancehub.app  A  <VPS_IP>
```

(or `botify.resonancehub.com` if using .com)

### nginx config

Add a new server block similar to Echo’s:

```nginx
# =============================================================================
# Botify Arena subdomain: botify.resonancehub.app (or .com)
# =============================================================================
server {
    listen 80;
    server_name botify.resonancehub.app;   # or botify.resonancehub.com

    add_header X-Content-Type-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;

    root /var/www/botify;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    location ~ /\. { deny all; }
}
```

### Directory

```bash
sudo mkdir -p /var/www/botify
sudo chown murp:murp /var/www/botify   # or a dedicated botify user
```

### TLS (recommended)

```bash
sudo certbot --nginx -d botify.resonancehub.app
```

---

## 4. Deployment flow for Botify Arena

Since Botify Arena lives in another repo, deploy it independently:

```bash
# From your botify repo
npm run build   # or your build command
rsync -avz --delete -e "ssh -i ~/.ssh/murp_hetzner" \
  dist/ root@46.62.247.144:/var/www/botify/
```

You can add a small deploy script in the Botify Arena repo that runs this.

---

## 5. If Botify Arena has its own backend

If Botify Arena needs an API server:

- Run it as its own systemd unit (e.g. `botify-api.service`) on a different port (e.g. 3003).
- Proxy that port only for the Botify Arena subdomain:

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:3003/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

This keeps Botify Arena’s API on its own subdomain and port, separate from ANN and EMB.

---

## 6. Isolation summary

| Resource | MuRP | Echo | Botify Arena |
|----------|------|------|--------|
| URL | resonancehub.app/murp/ | echo.resonancehub.app | botify.resonancehub.app |
| Static files | /var/www/murp-client | /var/www/echo | /var/www/botify |
| Backend (if any) | ANN, EMB (shared) | None | Own port / unit |
| Codebase | mrp-prototype | mrp-prototype | botify repo |

Botify Arena will share the same VPS (CPU, RAM, network). If you later need stronger isolation (e.g. separate app limits or blast radius), you can move Botify Arena into a Docker container or a different VPS, but for many apps this setup is sufficient.