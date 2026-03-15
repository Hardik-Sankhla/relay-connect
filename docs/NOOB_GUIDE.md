# relay-connect — NOOB GUIDE

If you are brand new, follow this and do not skip steps.

---

## What is a relay? (one sentence)
A relay is a middleman that connects your laptop to your phone without opening any ports on the phone.

```
Laptop (you)  ──▶  Relay (middleman)  ◀──  Phone (Termux)
```

---

## 30-second setup (recommended)

### 1) Laptop (Windows/Mac/Linux)
```bash
pip install relay-connect
relay wizard
```

You will see a QR code and a connection string.

### 2) Android phone (Termux)
```bash
pkg install python
pip install git+https://github.com/Hardik-Sankhla/relay-connect.git
relay wizard
```

Scan the QR from your laptop. Done.

---

## What you should see (ASCII screenshots)

### Laptop
```
relay-connect wizard
Detected role: laptop/server
Relay URL: ws://192.168.1.36:8765
Saved C:\Users\YOU\AppData\Roaming\relay\.env
Relay server started in background

[QR CODE HERE]
relay-connect://192.168.1.36:8765?token=...&name=MY-LAPTOP
```

### Phone (Termux)
```
relay-connect wizard (Termux)
Paste the QR string from your laptop:
relay-connect://192.168.1.36:8765?token=...&name=MY-LAPTOP

Termux setup complete
Starting agent now...
Starting relay-agent 'my-phone' → ws://192.168.1.36:8765
```

---

## Troubleshooting (top 5 beginner errors)

1) **Agent not online**
- Fix: run on phone:
  ```bash
  relay-agent --relay ws://LAPTOP_IP:8765 --name my-phone
  ```

2) **Handshake timeout / connection refused**
- Fix: your firewall is blocking port 8765
- On Windows (Admin PowerShell):
  ```powershell
  netsh advfirewall firewall add rule name=relay-connect dir=in action=allow protocol=TCP localport=8765
  ```

3) **Wrong token**
- Fix: tokens must match on both devices. Run `relay wizard` again on laptop.

4) **Phone can’t reach laptop**
- Fix: both devices must be on the same Wi-Fi.
- Check laptop IP with `ipconfig` and use that IP.

5) **`relay` command not found**
- Fix: reinstall and ensure Python scripts are on PATH:
  ```bash
  python -m pip install relay-connect
  ```

---

## "It’s not working" decision tree

```
Is the relay server running?
├─ No → run: relay wizard (on laptop)
└─ Yes
   ├─ Is phone on same Wi‑Fi?
   │  ├─ No → connect to same Wi‑Fi
   │  └─ Yes
   │     ├─ Is firewall open on laptop?
   │     │  ├─ No → open port 8765 (see troubleshooting #2)
   │     │  └─ Yes
   │     │     └─ Run: relay doctor
```

---

## Termux battery optimizations

- Disable battery optimizations for Termux in Android settings
- Install Termux:Boot from F-Droid and allow auto-start
- Use `termux-wake-lock` (wizard does this for you)

Example device note: On Samsung/MIUI, add Termux to "Protected Apps".
