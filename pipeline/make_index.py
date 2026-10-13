"""Wrap site/app.html into a full site/index.html for GitHub Pages (adds phone home-screen metas)."""
from pathlib import Path
site = Path(__file__).resolve().parents[1] / "site"
head = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Macro Desk">
<meta name="theme-color" content="#0e1216">
<meta name="robots" content="noindex, nofollow">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="icon" href="icon-192.png">
<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}[hidden]{display:none!important}</style>
</head>
<body>
"""
(site / "index.html").write_text(head + (site / "app.html").read_text() + "\n</body>\n</html>\n")
print("wrote site/index.html")
