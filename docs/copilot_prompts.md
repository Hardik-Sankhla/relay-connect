# relay-connect — Copilot Prompts

Copy these into GitHub Copilot Chat or your VS Code Copilot to explore,
test, and extend relay-connect.

---

## Understanding the codebase

```
@workspace explain the overall architecture of relay-connect.
How do the server, agent, and client communicate?
```

```
@workspace What is a SessionCert and how does the relay use it to
authenticate sessions without storing passwords?
```

```
@workspace Walk me through what happens when I run `relay deploy ./dist prod-1`.
Trace the code path from CLI command to file landing on the remote server.
```

```
@workspace How does the relay agent connect to the relay server?
Why does it dial outbound instead of listening for connections?
```

---

## Running and testing

```
Start the relay server, then an agent, then connect with the client.
Show me the exact commands.
```

```
Run the integration tests and show me what each test is checking.
```

```
@workspace How do I test relay-connect against my Termux phone?
My phone's IP is 192.168.1.50 and the relay will run on my laptop.
```

```
@workspace Write a pytest test that:
1. Starts a relay server
2. Connects an agent named "staging"
3. Deploys a directory with 3 files
4. Verifies the files arrived by running `ls` on the agent
```

---

## Extending the project

```
@workspace Add rate limiting to the relay server so no single client_id
can make more than 10 exec requests per minute. Show the code changes.
```

```
@workspace Add a --allowed-paths flag to relay-agent that restricts
which directories files can be deployed to.
```

```
@workspace Implement a `relay cp` command that copies a file FROM the
remote server back to the local machine (reverse of deploy).
```

```
@workspace Add WebSocket Secure (WSS) support to the relay server
so it can use TLS directly without a proxy.
```

```
@workspace Implement OAuth2 token verification in the relay server's
authentication flow, replacing the shared token approach.
```

---

## Debugging

```
@workspace The integration test test_exec_echo is failing with a
TunnelError. What are the most likely causes and how do I debug it?
```

```
@workspace How do I tail the relay audit log and what does each
event type mean?
```

```
@workspace relay-agent is connecting to the relay but the relay
doesn't show it in `relay list`. How do I debug this?
```

---

## Termux-specific

```
@workspace How do I install relay-agent on Termux so it starts
automatically when my phone boots?
```

```
@workspace Write a relay exec command that installs a Python package
on Termux using pkg install.
```

```
@workspace My Termux agent keeps disconnecting after 60 seconds.
How do I configure keep-alive / reconnect settings?
```

---

## Production hardening

```
@workspace What are all the security hardening steps I should take
before deploying relay-connect to production?
```

```
@workspace Show me how to set up nginx as a TLS reverse proxy in
front of the relay server on Ubuntu.
```

```
@workspace How should I store the RELAY_TOKEN securely in a
GitHub Actions workflow so I can deploy from CI?
```

---

## CI/CD integration

```
@workspace Write a GitHub Actions workflow that:
1. Builds my Python app
2. Uses relay-connect to deploy ./dist to "prod-1"
3. Runs a health check after deploy
```

```
@workspace Add relay-connect deployment to an existing Dockerfile
so the container can push to production on startup.
```
