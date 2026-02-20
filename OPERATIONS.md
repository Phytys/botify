# Botify Operations & Deployment

This document describes how to deploy Botify on the same VPS as Echo and MuRP (resonancehub.app).

---

## Server Layout

```
VPS: 46.62.247.144 (ubuntu-8gb-hel1-1)
│
├── /var/www/                          # Static web roots (nginx)
│   ├── landing/                       # resonancehub.app/
│   ├── murp-client/                   # resonancehub.app/murp/
│   └── echo/                          # echo.resonancehub.app
│
├── /opt/murp/mrp-prototype/           # MuRP monorepo
│   ├── ann/                           # Node → port 3001 (murp-ann.service)
│   └── emb/                           # Python → port 3002 (murp-emb.service)
│
├── /opt/botify/                       # Botify app (this repo)
│   └── .venv/                         # Python virtualenv
│
├── /var/lib/botify/                   # Botify SQLite DB (persistent)
│
└── /etc/nginx/sites-enabled/
    ├── default
    ├── murp                           # resonancehub + echo
    └── botify                         # botify.resonancehub.app
```

### Port Allocation

| Port | Service      |
|------|--------------|
| 80, 443 | nginx     |
| 3001 | MuRP ANN  |
| 3002 | MuRP EMB  |
| 8000 | Botify    |

---

## One-Time Setup (on VPS)

### 1. Create directories

```bash
sudo mkdir -p /opt/botify
sudo mkdir -p /var/lib/botify
sudo chown murp:murp /opt/botify /var/lib/botify
```

### 2. Generate and store secret

```bash
BOTIFY_SECRET=$(openssl rand -hex 32)
echo "BOTIFY_SECRET=$BOTIFY_SECRET" | sudo tee /etc/botify.env
sudo chmod 600 /etc/botify.env
sudo chown root:root /etc/botify.env
```

### 3. Create systemd service

```bash
sudo tee /etc/systemd/system/botify.service << 'EOF'
[Unit]
Description=Botify preference-lab API
After=network.target

[Service]
User=murp
Group=murp
WorkingDirectory=/opt/botify
EnvironmentFile=-/etc/botify.env
Environment=BOTIFY_DATABASE_URL=sqlite:////var/lib/botify/botify.db
Environment=BOTIFY_PUBLIC_BASE_URL=https://botify.resonancehub.app
ExecStart=/opt/botify/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable botify
```

### 4. Nginx config

Create `/etc/nginx/sites-available/botify`:

```nginx
# Botify subdomain: botify.resonancehub.app
server {
    server_name botify.resonancehub.app;

    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    listen 80;
}
```

Enable and add TLS:

```bash
sudo ln -s /etc/nginx/sites-available/botify /etc/nginx/sites-enabled/
sudo nginx -t
sudo certbot --nginx -d botify.resonancehub.app
sudo systemctl reload nginx
```

### 5. DNS

Add A record: `botify.resonancehub.app  A  46.62.247.144`

---

## Deployment (from local botify repo)

### First-time: install dependencies on VPS

```bash
ssh -i ~/.ssh/murp_hetzner murp@46.62.247.144
cd /opt/botify
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
exit
```

### Regular deploy

```bash
# From local botify repo
rsync -avz --delete \
  -e "ssh -i ~/.ssh/murp_hetzner" \
  --exclude venv \
  --exclude __pycache__ \
  --exclude data \
  --exclude .git \
  . murp@46.62.247.144:/opt/botify/

# Update deps (if requirements.txt changed)
ssh -i ~/.ssh/murp_hetzner murp@46.62.247.144 'cd /opt/botify && .venv/bin/pip install -q -r requirements.txt'

# Restart service
ssh -i ~/.ssh/murp_hetzner root@46.62.247.144 'systemctl restart botify'
```

### Deploy script (optional)

Save as `deploy.sh` in the botify repo:

```bash
#!/bin/bash
set -e
KEY="${BOTIFY_SSH_KEY:-$HOME/.ssh/murp_hetzner}"
HOST="murp@46.62.247.144"

rsync -avz --delete \
  -e "ssh -i $KEY" \
  --exclude venv --exclude __pycache__ --exclude data --exclude .git \
  . $HOST:/opt/botify/

ssh -i "$KEY" $HOST 'cd /opt/botify && .venv/bin/pip install -q -r requirements.txt'
ssh -i "$KEY" root@46.62.247.144 'systemctl restart botify'
echo "Deployed."
```

---

## Service Commands

```bash
# Status
ssh -i ~/.ssh/murp_hetzner root@46.62.247.144 'systemctl status botify'

# Logs
ssh -i ~/.ssh/murp_hetzner root@46.62.247.144 'journalctl -u botify -f'

# Restart
ssh -i ~/.ssh/murp_hetzner root@46.62.247.144 'systemctl restart botify'
```

---

## Security Summary

| Aspect       | Implementation                                      |
|-------------|------------------------------------------------------|
| Process     | Runs as `murp`, bound to 127.0.0.1 only             |
| Secrets     | `BOTIFY_SECRET` in `/etc/botify.env` (root-only)     |
| Data        | DB in `/var/lib/botify/` owned by murp               |
| Isolation   | Own port, nginx block; no shared APIs with MuRP/Echo |
| TLS         | Certbot-managed cert for botify.resonancehub.app     |

---

## URLs

| App     | URL                           |
|---------|-------------------------------|
| UI      | https://botify.resonancehub.app |
| API docs| https://botify.resonancehub.app/docs |
| Health  | https://botify.resonancehub.app/api/health |
