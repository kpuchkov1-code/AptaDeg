import urllib.request, json
r = json.loads(urllib.request.urlopen('https://api.github.com/repos/CBDD/rDock/releases/latest').read())
print('tag:', r['tag_name'])
print('tarball:', r['tarball_url'])
for a in r.get('assets', []):
    print('asset:', a['browser_download_url'])
