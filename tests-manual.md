Test Delay
----------
Run `vsm` with the `delay.yaml` rule file:

```
./vsm --signal-number-file signal_number_maps/samples.vsi sample_rules/delay.yaml
```

and provide the input:

```
wipers.front.on = True
```

Expected output:

```
> (time),wipers.front.on,(signal ID),'True'
```

(2 second delay)

```
< (time),lights.external.headlights,(signal ID),'True'
```

Test Replay Rates (Normal)
--------------------------
Run `vsm` with the `simple0.yaml` rule file and replay log file:

```
./vsm --signal-number-file signal_number_maps/samples.vsi --replay-log-file
sample_logs/simple0-slow.log --replay-rate 100 sample_rules/simple0.yaml
```

Expected output:

(2-second delay)

```
> 2000,phone.call,(signal ID),'active'
```

(2-second delay)

```
< 4000,car.stop,(signal ID),'True'
```

The times (the first number field of the last two lines) may vary slightly (eg,
may be 2002ms instead of 2000ms) due to processing time but should not differ
significantly.

Test Replay Rates (Slow)
------------------------
Follow steps for "Test Replay Rates (Normal)" but change replay rate to "50" (to
replay at 50% of the original speed).

All delays and timestamp output should double.

Test Replay Rates (Fast)
------------------------
Follow steps for "Test Replay Rates (Normal)" but change replay rate to "200"
(to replay at 200% of the original speed).

All delays and timestamp output should be reduced to half.
