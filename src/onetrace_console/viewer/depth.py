"""The viewer's own rule for how deeply nested a JSON value may be.

Until this rule, "nested too deeply" meant "the interpreter ran out of recursion first": each reader
caught `RecursionError` from `json.loads` or from the page's indented `json.dumps`. Where that
happens is not the viewer's to decide, and it moved. Parsing then indenting `{"a": ...}` nested n
deep, the first n that raises:

    Linux,   Python 3.12.10   json.loads fails at n = 9995   indented json.dumps fails at n = 991
    Linux,   Python 3.13.5    json.loads fails at n = 9996   indented json.dumps fails at n = 9996
    Windows, Python 3.12.10   json.loads fails at n = 2995   indented json.dumps fails at n = 991

(as `python -m onetrace_console.viewer.depth` measures them: the Linux gates at one commit, and a
Windows machine's run of the same commit with its junit file). Windows'
`json.loads` stops sooner, on a smaller C stack; that is what failed at 8b384b5.

**The binding figure is the indented dump at 991, on 3.12 on both OSes:** 256 + 700 = 956 fits below
it with 35 levels to spare. **Never raise MAX_JSON_DEPTH or CALLER_FRAMES
without remeasuring on all three** -- and the premise test below fails on any interpreter where the
sum stops fitting.

A table measured on one OS cannot speak for another, so the premise is not
taken from it: `tests`' `test_the_depth_limit_is_below_this_interpreter_s_own_limits` runs
`python -m onetrace_console.viewer.depth` on whatever interpreter runs the suite, and requires
`MAX_JSON_DEPTH + CALLER_FRAMES` to be at or below both of its measured depths.

3.13's C encoder takes `indent`, so a record 1500 deep that 3.12 refused was shown on 3.13
(CI run 152, `gates (3.13)`). The same record must get the same answer on every interpreter.

**The limit is 256 levels:** a dict or list at the top counts 1, and each container inside it one
more; a scalar adds nothing. Why 256:
- it is below the shallowest interpreter failure in the supported range (3.12's encoder, 991 levels
  measured from a shallow call) with room for some 700 frames of whatever is calling, so this rule,
  not the interpreter, decides every refusal;
- it is far above any real record: the deepest JSON this repository holds is 6 levels.

`json_depth` walks the value with an explicit stack, never by recursion, so measuring the depth
cannot itself run out of recursion.
"""
from __future__ import annotations

MAX_JSON_DEPTH = 256

#: The room the limit leaves for the frames of whatever is calling: a page is rendered deep inside a
#: server or a test runner, and the interpreter's failure point drops by one level per frame in use.
CALLER_FRAMES = 700


def json_depth(value) -> int:
    """How deeply `value` nests: 0 for a scalar, 1 for a flat dict or list, and so on."""
    deepest = 0
    stack = [(value, 1)]
    while stack:
        item, level = stack.pop()
        if isinstance(item, dict):
            children = item.values()
        elif isinstance(item, list):
            children = item
        else:
            continue
        deepest = max(deepest, level)
        stack.extend((child, level + 1) for child in children)
    return deepest


def too_deep(value) -> bool:
    """True when `value` nests deeper than `MAX_JSON_DEPTH` and must be refused."""
    return json_depth(value) > MAX_JSON_DEPTH


def first_failing_depths(ceiling: int = 200_000) -> dict:
    """This interpreter's first nesting depth that raises `RecursionError`, by binary search, for
    `json.loads` and for `json.loads` followed by the page's indented `json.dumps` (None: nothing
    failed up to `ceiling`). Measured from a shallow call: run it as
    `python -m onetrace_console.viewer.depth`."""
    import json

    def fails(op, n: int) -> bool:
        text = '{"a":' * n + "1" + "}" * n
        try:
            op(text)
        except RecursionError:
            return True
        return False

    def first(op) -> int | None:
        if not fails(op, ceiling):
            return None
        lo, hi = 1, ceiling
        while lo < hi:
            mid = (lo + hi) // 2
            if fails(op, mid):
                hi = mid
            else:
                lo = mid + 1
        return lo

    return {"json.loads": first(json.loads),
            "json.loads+indented json.dumps": first(
                lambda t: json.dumps(json.loads(t), ensure_ascii=True, indent=1).encode("utf-8"))}


if __name__ == "__main__":
    import json
    import platform
    import sys
    print(json.dumps({"python": sys.version.split()[0], "os": platform.system(),
                      "first_failing_depth": first_failing_depths(),
                      "MAX_JSON_DEPTH": MAX_JSON_DEPTH, "CALLER_FRAMES": CALLER_FRAMES}))
