"""Build web/index.html from web/template.html (standalone page; reads runs/ live from GitHub, falls back to ../)."""
import os
ROOT = os.path.dirname(os.path.abspath(__file__))
body = open(os.path.join(ROOT, "web", "template.html"), encoding="utf-8").read().replace("<!--SITEBAR-->", "").replace('/*FALLBACKS*/["../"]', '["../"]')
open(os.path.join(ROOT, "web", "index.html"), "w", encoding="utf-8").write(
    '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
    '<style>body{margin:0}</style>\n</head>\n<body>\n' + body + "\n</body>\n</html>\n")
print("built web/index.html")

# also make the page work when opened straight from disk (file://)
import sys as _sys
_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from offline_snapshot import inline as _inline
_R = os.path.dirname(os.path.abspath(__file__))
_inline(os.path.join(_R, "web/index.html"), ['runs/history.json', 'runs/latest.json'], "../", os.path.join(_R, ""))
