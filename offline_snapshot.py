"""Inline a data snapshot into a built page so it also works when opened straight from disk.

Browsers block fetch() for pages opened from file://. This wraps fetch: if a request fails and its URL
matches one of the bundled paths, the bundled copy is served instead. Online, the live data still wins.
"""
import json
import os
import re

JS = """<script>(function(){var S=%s;var f=window.fetch.bind(window);
function k(u){u=String(u&&u.url||u).split('?')[0];for(var p in S){if(u===p||u.slice(-(p.length+1))==='/'+p)return p;}return null;}
window.fetch=function(u,o){var key=k(u);return f(u,o).then(function(r){if(r.ok||!key)return r;return new Response(S[key]);},function(e){if(!key)throw e;return new Response(S[key]);});};})();</script>"""


def inline(page, files, prefix, root):
    """files: paths relative to `root`; each is keyed as prefix + that path (what the page requests)."""
    snap = {prefix + f: open(os.path.join(root, f), encoding="utf-8").read() for f in files}
    h = open(page, encoding="utf-8").read()
    h = re.sub(r"<script>\(function\(\)\{var S=.*?</script>\n?", "", h, flags=re.S)
    tag = JS % json.dumps(snap, ensure_ascii=False).replace("</", "<\\/")
    i = h.index("</head>") if "</head>" in h else h.index("<body>")
    open(page, "w", encoding="utf-8").write(h[:i] + tag + "\n" + h[i:])
    print(f"inlined {len(snap)} data files for offline use")
