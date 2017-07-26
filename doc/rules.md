Introduction
============
The VSM rules format describes signals which may be emitted and under which
conditions.

This format uses YAML as a container format.

Structure
=========
All rules files should begin with the YAML version declaration:

```
%YAML 1.2
---
```

All top-level items must be YAML list items. In the following example, both
top-level items are lists (declared with a leading `-`) of maps:

```
- emit:
    signal: car.backup
    value: true

- condition: phone.call = 'active'
  emit:
    signal: car.stop
    value: true
```

Signals
=======
Signals are essentially variables with int, float, or string values. When a
signal is emitted, its value is updated in the VSM state machine and its name,
signal ID, and value are output by VSM.

Signal names may contain letters, numbers, underscores ("_") and dots("."). Each
dot denotes a generation in the signal name hierarchy. For example, the name
`car.backup` indicates the root name of `car` and base name of `backup`.

Unconditional Emissions
-----------------------
Signals will be emitted unconditionally for a rule file if they are contained
top-level list's map item without a sibling condition statement. For example:

```
%YAML 1.2
---
- emit:
    signal: car.backup
    value: true
```

Delay keyword
-------------
Emissions may be delayed any number of milliseconds by using a `delay` statement
like:

```
# When the front wipers are enabled, ensure headlights are on (a legal
# requirement in some jurisdictions and generally safer).
- parallel:
    # We now monitor the incoming signal stream for specific conditions to be
    # met.
    - condition: wipers.front.on == true

      # Emit a signal to turn on the headlights
      emit:
          # How many msec to wait after condition changes before we emit the
          # signal.
          #
          # The delay in this use case is arbitrary and exaggerated so this
          # configuration file can be used to test the delay feature.
          delay: 2000

          signal: lights.external.headlights
          value: true
```

Conditions
==========
`condition` statements define conditions under which the rest of their siblings
(usually including an `emit` statement) will be evaluated.

For example:

```
- condition: transmission.gear == 'reverse'
  emit:
      signal: car.backup
      value: true
```

In this case, the signal `car.backup` will be emitted (with a value of `true`)
when the value of `transmission.gear` changes from a value other than 'reverse'
to 'reverse'.

Expressions
-----------
Condition expressions support any C-like comparison operators (`<`, `<=`, `==`,
`>=`, `>`, `!=`), arithmetic expressions, parentheses for overriding precedence,
and logic inversion (`!`). Additionally, VSM rules support the binary XOR
operator, `^^`. In that case, `a ^^ b` will evaluate to `true` if exactly one of
`a` or `b` evaluates to `true`.

Parallel Blocks
---------------
Conditions may be contained within a "wrapper" `parallel` block like:

```
- parallel:
    - condition: wipers == true
      emit:
          signal: lights
          value: 'on'

    - condition: transmission.gear == 'reverse'
      emit:
          signal: reverse
          value: true
```

In this structure, both conditions are evaluated independently of one-another.
Since this `parallel` block is at the top level, this snippet is equivalent to:

```
- condition: wipers == true
  emit:
      signal: lights
      value: 'on'

- condition: transmission.gear == 'reverse'
  emit:
      signal: reverse
      value: true
```

However, `parallel` blocks may be used in nested structures to achieve unique
behavior, similarly to parentheses in mathematical and logic expressions may
change their behavior. See "Nested Conditions", below.

`parallel` blocks must only contain lists of `condition` maps and/or other
"wrapper" blocks as direct children.

Sequence Blocks
---------------
Conditions may be contained within a "wrapper" `sequence` block like:

```
- sequence:
    - condition: transmission.gear == 'park'
      emit:
          signal: parked
          value: true

    - condition: ignition == true
      emit:
          signal: ignited
          value: true
```

In this structure, all conditions will only evaluate to true if all previous
conditions have been met. In other words, the second condition will only be
evaluated after the first condition becomes true.

`sequence` blocks must only contain lists of `condition` maps and/or other
"wrapper" blocks as direct children.

Nested conditions
-----------------
Conditions may be nested with a wrapper block (eg, `parallel`, `sequence`) in
between each condition as with:

```
# We now monitor the incoming signal stream for specific conditions to be met.
- condition: transmission.gear == 'reverse'
  # When this monitor's condition (gear in reverse) becomes true, a signal
  # will be emitted to turn the backup light.
  emit:
    signal: lights.external.backup
    value: true

  # wrap the monitored condition in a block; since it's the only entry, any
  # keyword would behave the same as "parallel" here
  parallel:

    # We want to see the backup camera being active within 100 msec of the
    # vehicle being put in reverse.
    #
    # This monitor will be active from 'start' msec after it becomes
    # active, or when the parent condition becomes false.
    - condition: camera.backup.active == true

      # How many msec do we wait after parent condition becomes true
      # (gear = reverse) until we require our condition (backup camera
      # active) to also be true.
      start: 200

      # How many msec after activation do we keep the monitor active?
      # The monitor condition has to remain true for 'stop' milliseconds
      # after the monitor is started. If those criteria are not fulfilled,
      # an error will be logged
      stop: 1000
```

In this structure, the first `condition` is refered to as a "monitored
condition" because its becoming true triggers the setup of timers within the VSM
state machine as described below in "Start and Stop keywords".

Subconditions do not require an `emit` statement. This can be useful when the
error logging for monitored conditions (see below) is desired but signal
emission is unnecessary.

The subconditions will only be evaluated when all of their ancestors' conditions
have been met.

Start and Stop keywords
-----------------------
Nested conditions may specify `start` and `stop` times. These require that the
subcondition be met within `start` milliseconds of its parent condition becoming
true and that the subcondition stay true until at least `stop` milliseconds
after the parent condition became true. If either condition is violated, an
error is logged.

If the parent condition becomes false in under `start` milliseconds from the
point it became true, the monitor is cancelled.

See "Nested conditions" for an example.

Examples
========
For more examples, see the sample rules files in `sample_rules` and the test
suite (`tests.py`) which uses them.
