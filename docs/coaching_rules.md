# Coaching rules
Current rules:

- Throttle too aggressive while steering
- Brake and throttle overlap
- Rear tyre surface temperatures high
- Front brake temperatures high
- ERS low
- Fuel negative
- Tyre wear high
- Lap invalidated
- New personal best
- Lap completed but slower than PB

The thresholds are intentionally conservative. Tune them in:

```text
backend/app/coaching/rules.py
```