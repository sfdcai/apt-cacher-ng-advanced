# Apt-Cacher NG Advanced Dashboard & Installer

A professional, high-performance local network caching proxy setup for package managers (APT, APK, DNF/YUM), bundled with a modern, real-time glassmorphism management dashboard.

---

## 🚀 Key Features

- **One-Command Installation**: Sets up `apt-cacher-ng`, python virtual environment, all dependencies, and the dashboard service.
- **Vibrant Real-Time Dashboard**: Monitor cache efficiency, bandwidth savings, hit/miss ratios, active clients, and requested repositories.
- **Administrative Control Panel**: Run cleanups, expire old files, scan for/remove damaged packages, or restart the proxy service directly from the UI.
- **Universal Client Guides**: Built-in instructions copyable with a single click for Debian/Ubuntu (APT), Alpine Linux (APK), and CentOS/Rocky Linux (DNF/YUM).
- **Dynamic Hostname Detection**: Setup instructions dynamically render the hosting server's IP address.

---

## 💻 Installation

Install and configure both the caching server and the dashboard on any Debian/Ubuntu host with a single line:

```bash
curl -sSL https://raw.githubusercontent.com/sfdcai/apt-cacher-ng-advanced/main/install.sh | bash
```

Once completed, the dashboard will be available at `http://<your-server-ip>:8080/`.

---

## 🔒 How it Handles HTTPS Repositories

A common question is how `apt-cacher-ng` behaves when clients request repositories using HTTPS (e.g. `https://deb.debian.org`). By default, `apt-cacher-ng` is an HTTP caching proxy. Because HTTPS traffic is encrypted end-to-end, the proxy cannot examine or cache the files.

Here are the three ways to handle HTTPS repositories:

### Option A: SSL/TLS Tunnel Pass-Through (Default & No Caching)
By default, `apt-cacher-ng` blocks SSL connection requests (`CONNECT` method) to prevent unauthorized proxy tunneling. You can enable pass-through so that clients can fetch HTTPS packages successfully, though **they will not be cached**.

To enable HTTPS pass-through, create or edit `/etc/apt-cacher-ng/conf.d/https.conf` and add:
```text
PassThroughPattern: .*
```
*(Or restrict it to secure port 443 with: `PassThroughPattern: ^[^:]+:[443]$`)*.
After editing, restart the services using the dashboard or run:
```bash
systemctl restart apt-cacher-ng
```

### Option B: Client-to-Proxy HTTP / Proxy-to-Upstream HTTPS (Recommended for Caching)
This is the cleanest and most secure method to cache packages from secure repositories.
1. **Security Context**: Debian/Ubuntu package verification is based on cryptographic GPG signatures (`Release.gpg` keys). Package integrity is validated by the client itself after download. Because of this, it is entirely secure to download packages from the local proxy over HTTP, as any tempered packages are immediately caught and rejected by the client.
2. **Setup**: Keep the client pointing to the proxy over HTTP (e.g., `Acquire::http::Proxy "http://<cache-ip>:3142";`), but configure `apt-cacher-ng` to download from the remote repository using HTTPS.
3. **Configuration**: Edit `/etc/apt-cacher-ng/acng.conf` to map remote repositories to HTTPS upstream URLs. For example, map the Debian repository to its HTTPS counterpart:
   ```text
   Remap-debrep: file:deb_mirrors.gz /debian ; https://deb.debian.org/debian
   ```

### Option C: SSL MITM Decryption (Complex & Discouraged)
It is technically possible to configure `apt-cacher-ng` to act as a Man-In-The-Middle (MITM) proxy by generating a custom CA certificate, installing it on all client machines, and configuring `apt-cacher-ng` to decrypt client HTTPS requests and re-encrypt them. 
This is generally **not recommended** because it compromises local network security architecture, breaks TLS trust chains, and requires maintaining certificates on all client nodes.

---

## 🛠️ Client Configuration Guides

To route your client servers through the cache, run the appropriate command below:

### 1. Debian / Ubuntu / Proxmox VE (APT)
Create a proxy configuration file:
```bash
echo 'Acquire::http::Proxy "http://<your-cache-ip>:3142";' > /etc/apt/apt.conf.d/00aptproxy
```

### 2. Alpine Linux (APK)
Use `http_proxy` for temporary or permanent configurations:
```bash
# Temporary (One-off)
http_proxy=http://<your-cache-ip>:3142 apk update && apk upgrade

# Permanent
echo 'export http_proxy=http://<your-cache-ip>:3142' >> /etc/profile
source /etc/profile
```

### 3. Rocky Linux / AlmaLinux / CentOS (DNF/YUM)
Add the proxy rule to the package manager configuration:
```bash
echo 'proxy=http://<your-cache-ip>:3142' >> /etc/dnf/dnf.conf
```
