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
