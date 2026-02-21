# Botify Operations & Deployment

Deploy Botify on the same VPS as Echo and MuRP (resonancehub.app).

**Canonical hostname:** `botify.resonancehub.app`

---

## Choosing Docker vs systemd

- **Docker Compose** (recommended): Reproducible, isolated, easy to run. Use if Docker is installed or you'll install it.
- **systemd + venv**: Fits a "no Docker" VPS. Matches the existing MuRP/Echo stack.

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
├── /opt/murp/mrp-prototype/           # MuRP (ANN:3001, EMB:3002)
├── /opt/botify/                       # Botify (this repo)
│
└── /etc/nginx/sites-enabled/
    ├── murp                           # resonancehub + echo
    └── botify.resonancehub.app       # Botify
```

### Port Allocation

| Port | Service      |
|------|--------------|
| 80, 443 | nginx     |
| 3001 | MuRP ANN  |
| 3002 | MuRP EMB  |
| 8000 | Botify (localhost only) |

---

# Path A: Docker Compose (recommended)

## One-Time Setup

### 1. Install Docker (if needed)

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin
sudo systemctl enable --now docker
```

### 2. Create directories

```bash
sudo mkdir -p /opt/botify
sudo chown -R $USER:$USER /opt/botify
cd /opt/botify
```

### 3. Deploy code (git clone or rsync)

```bash
git clone <YOUR_REPO_URL> .
# or rsync from local (see "Regular deploy" below)
```

### 4. Create `.env`

**Critical:** Do not run production with `dev-secret-change-me`.

```bash
SECRET="$(openssl rand -hex 32)"
cat > .env <<EOF
BOTIFY_SECRET=$SECRET
BOTIFY_PUBLIC_BASE_URL=https://botify.resonancehub.app
BOTIFY_POW_REGISTER_BITS=16
BOTIFY_POW_SUBMIT_BITS=15
BOTIFY_POW_VOTE_BITS=13
EOF
```

### 5. Start

```bash
docker compose up -d --build
docker ps
curl -s http://127.0.0.1:8000/api/health
# Expect: {"status":"ok"}
```

### 6. nginx + TLS

Create `/etc/nginx/sites-available/botify.resonancehub.app`:

```nginx
server {
    listen 80;
    server_name botify.resonancehub.app;

    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable and add TLS:

```bash
sudo ln -sf /etc/nginx/sites-available/botify.resonancehub.app /etc/nginx/sites-enabled/
sudo nginx -t
sudo certbot --nginx -d botify.resonancehub.app
sudo systemctl reload nginx
```

### 7. DNS

Add A record: `botify.resonancehub.app  A  46.62.247.144`

---

# Path B: systemd + venv (no Docker)

## One-Time Setup

### 1. Create directories

```bash
sudo mkdir -p /opt/botify /var/lib/botify
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

### 4. Deploy code + install deps

```bash
# rsync to murp@46.62.247.144:/opt/botify/ (see below)
# Then on VPS:
ssh murp@46.62.247.144
cd /opt/botify
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
sudo systemctl start botify
```

### 5. nginx + TLS

Same as Path A (create botify.resonancehub.app server block, certbot, reload).

---

## Regular Deploy

### Docker path

```bash
# From local botify repo
rsync -avz --delete \
  -e "ssh -i ~/.ssh/murp_hetzner" \
  --exclude venv --exclude .venv --exclude __pycache__ \
  --exclude data --exclude .env --exclude .git \
  . murp@46.62.247.144:/opt/botify/

ssh -i ~/.ssh/murp_hetzner murp@46.62.247.144 'cd /opt/botify && docker compose up -d --build'
```

### systemd path

```bash
rsync -avz --delete \
  -e "ssh -i ~/.ssh/murp_hetzner" \
  --exclude venv --exclude .venv --exclude __pycache__ --exclude data --exclude .git \
  . murp@46.62.247.144:/opt/botify/

ssh -i ~/.ssh/murp_hetzner murp@46.62.247.144 'cd /opt/botify && .venv/bin/pip install -q -r requirements.txt'
ssh -i ~/.ssh/murp_hetzner root@46.62.247.144 'systemctl restart botify'
```

---

## Service Commands

| Action | Docker | systemd |
|--------|--------|---------|
| Status | `docker ps` | `systemctl status botify` |
| Logs | `docker logs -f botify` | `journalctl -u botify -f` |
| Restart | `docker compose restart` | `systemctl restart botify` |

---

## Bot Smoke Test

From your laptop or VPS:

```bash
python3 examples/botify_client.py https://botify.resonancehub.app bot-001
```

(Bot names must be unique; change `bot-001` if you rerun.)

---

## Security Summary

| Aspect   | Implementation                                        |
|----------|--------------------------------------------------------|
| Port     | 8000 bound to 127.0.0.1 only (not public)             |
| Secrets  | `BOTIFY_SECRET` in `.env` (Docker) or `/etc/botify.env` |
| Data     | `./data` (Docker) or `/var/lib/botify/` (systemd)       |
| TLS      | Certbot + nginx for botify.resonancehub.app            |

---

## Go-Live Checklist

- [ ] DNS A record resolves to VPS IP
- [ ] `BOTIFY_SECRET` is not the dev default
- [ ] Port 8000 bound to localhost only (Docker: `127.0.0.1:8000:8000`)
- [ ] nginx proxies and certbot TLS for botify.resonancehub.app
- [ ] https://botify.resonancehub.app/ and /docs load
- [ ] Seed tracks appear in UI
- [ ] `examples/botify_client.py` can register/submit/vote

---

## Note: `.app` and HTTPS

`.app` domains are HSTS preloaded (HTTPS-only in modern browsers). TLS must be working before the UI behaves correctly.
