"""Every function an inline script calls has to exist in it.

A syntax check passes happily on a script that calls a function nobody defined;
the page only breaks when the line runs. That is exactly how the VPN site page
lost its chart helpers - the file parsed, `node --check` was clean, and the
first render threw ReferenceError into a catch block that replaced the page
with "Could not load this site".

This walks the inline scripts instead: collect what each one defines, collect
what it calls, and hold the difference against a list of things the browser
provides.
"""
import re
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parents[1] / 'templates'

# Everything the page can legitimately call without defining it: language
# built-ins, browser APIs, and the two libraries these pages load.
PROVIDED = {
    # language
    'Array', 'Boolean', 'Date', 'Error', 'Function', 'JSON', 'Map', 'Math',
    'Number', 'Object', 'Promise', 'RegExp', 'Set', 'String', 'Symbol',
    'decodeURIComponent', 'encodeURIComponent', 'isFinite', 'isNaN',
    'parseFloat', 'parseInt', 'require',
    # browser
    'alert', 'clearInterval', 'clearTimeout', 'confirm', 'console', 'document',
    'fetch', 'localStorage', 'location', 'navigator', 'setInterval',
    'setTimeout', 'window', 'CustomEvent', 'Event', 'URLSearchParams',
    # libraries these templates load
    'Chart', 'L',
    # control flow that looks like a call to a regex
    'if', 'for', 'while', 'switch', 'catch', 'return', 'typeof', 'function',
    'new', 'else', 'do', 'in', 'of', 'delete', 'void', 'await', 'yield',
    # keywords, and the CSS var() that survives in a colour string - neither can
    # ever be a call to something this script was supposed to define
    'var', 'let', 'const',
}

DEFINITION = re.compile(r'\bfunction\s+([A-Za-z_$][\w$]*)\s*\(')
ASSIGNED = re.compile(r'\b(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=')
PARAMS = re.compile(r'\bfunction\s*[A-Za-z_$\w]*\s*\(([^)]*)\)')
# A call on a bare name: not a property access, not a definition.
CALL = re.compile(r'(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(')


def inline_script(template):
    match = re.search(r'<script>\n(.*?)</script>', template, re.S)
    return match.group(1) if match else ''


def _code_only(script):
    """Return the script with comments, strings and regex literals blanked out.

    These pages build HTML and CSS in strings, so `rgba(`, `var(` and
    `linear-gradient(` all read as calls to a regex that does not know the
    difference. A commented-out call is not a call either.

    This walks the text once rather than running a regex per quote character.
    Stripping `'...'` and then `"..."` is not merely imprecise, it is wrong: the
    apostrophe in a double-quoted "it's" pairs with some later apostrophe and
    swallows every line in between. On this page that left five call sites
    standing out of several hundred, and a checker that sees nothing reports
    nothing.
    """
    out = []
    i, n = 0, len(script)
    prev = ''
    while i < n:
        ch = script[i]
        if ch == '/' and i + 1 < n and script[i + 1] == '/':
            i = script.find('\n', i)
            if i == -1:
                break
        elif ch == '/' and i + 1 < n and script[i + 1] == '*':
            end = script.find('*/', i + 2)
            i = n if end == -1 else end + 2
            out.append(' ')
        elif ch in '\'"`':
            quote, i = ch, i + 1
            while i < n:
                if script[i] == '\\':
                    i += 2
                    continue
                if script[i] == quote:
                    i += 1
                    break
                i += 1
            out.append("''")
            prev = "'"
            continue
        elif ch == '/' and prev in '(,=:[!&|?{};' :
            # A slash in operand position opens a regex literal, and its body
            # may carry quote characters of its own.
            i += 1
            while i < n:
                if script[i] == '\\':
                    i += 2
                    continue
                if script[i] == '\n' or script[i] == '/':
                    i += 1
                    break
                i += 1
            while i < n and script[i] in 'gimsuy':
                i += 1
            out.append(' RE ')
            prev = 'E'
            continue
        else:
            out.append(ch)
            if not ch.isspace():
                prev = ch
            i += 1
            continue
        prev = ' '
    return ''.join(out)


def unresolved(script):
    # Definitions are read from the raw text and calls from the stripped text:
    # over-counting a definition only ever makes this check more permissive,
    # while a missed definition would raise a false alarm.
    defined_raw = set(DEFINITION.findall(script)) | set(ASSIGNED.findall(script))
    script = _code_only(script)
    defined = set(defined_raw)
    for group in PARAMS.findall(script):
        defined |= {p.strip() for p in group.split(',') if p.strip()}
    # Names introduced by for/catch bindings and object keys are noisy but
    # harmless - a call site is what matters.
    called = set(CALL.findall(script))
    return sorted(called - defined - PROVIDED)


def test_the_checker_notices_a_missing_function():
    """Without this, a checker that silently passes proves nothing."""
    broken = 'function a() { return helperThatVanished(1); }'
    assert unresolved(broken) == ['helperThatVanished']
    whole = 'function a() { return b(1); }\nfunction b(n) { return n; }'
    assert unresolved(whole) == []


def test_the_checker_still_sees_code_past_an_awkward_string():
    """The failure mode that made the first version of this check useless.

    An apostrophe inside a double-quoted string, and a regex literal carrying
    both quote characters, each swallowed the rest of the file when strings
    were stripped one quote character at a time - so the checker went quiet
    rather than wrong, which is worse.
    """
    script = (
        'var esc = function (v) { return String(v).replace(/[&<>"\']/g, "x"); };\n'
        'var note = "it\'s fine";\n'
        'var css = \'linear-gradient(to top, rgba(0,0,0,.1))\';\n'
        'function a() { return missingHelper(1); }\n'
    )
    missing = unresolved(script)
    assert 'missingHelper' in missing, 'the checker lost sight of the code after the strings'
    # ...and the CSS functions inside those strings are not mistaken for calls.
    assert 'rgba' not in missing and 'linear-gradient' not in missing


@pytest.mark.parametrize('name', ['vpn_health.html', 'vpn_site.html'])
def test_every_function_the_page_calls_is_defined(name):
    script = inline_script((TEMPLATES / name).read_text(encoding='utf-8'))
    assert script, '%s has no inline script to check' % name

    missing = unresolved(script)
    assert not missing, '%s calls functions nothing defines: %s' % (name, ', '.join(missing))
