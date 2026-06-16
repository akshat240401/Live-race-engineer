# F1 25 / 2026 Season Pack UDP setup

## Same PC setup
Use this if the game and this project run on the same laptop/PC.

```text
UDP Telemetry: On
UDP Broadcast Mode: Off
UDP IP Address: 127.0.0.1
UDP Port: 20777
UDP Send Rate: 20 Hz or 30 Hz
UDP Format: 2025 or 2026 Season Pack
```

## Console setup
Use this if F1 runs on PS5/Xbox and the project runs on your laptop.

1. Connect console and laptop to the same network.
2. Find laptop IP:

```powershell
ipconfig
```

3. Use the IPv4 address, for example `192.168.1.42`.
4. In the game:

```text
UDP Telemetry: On
UDP Broadcast Mode: Off or On depending on your network
UDP IP Address: 192.168.1.42
UDP Port: 20777
UDP Send Rate: 20 Hz or 30 Hz
```

## Firewall
If no data appears, Windows Firewall is usually the problem. Allow Python through firewall or create an inbound UDP rule for port `20777`.