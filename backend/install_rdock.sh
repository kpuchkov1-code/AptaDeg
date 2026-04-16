#!/bin/sh
URL="https://github.com/CBDD/rDock/releases/download/v24.04.204-legacy/rdock-legacy-24.04.204_ubuntu-22.04_g%2B%2B_x86_64.tar.gz"
curl -L -o /tmp/rdock.tar.gz "$URL"
echo "Downloaded: $(ls -lh /tmp/rdock.tar.gz)"
cd /tmp && tar xf rdock.tar.gz
ls /tmp/rdock*/
# Install binaries
find /tmp/rdock* -name "rbdock" -o -name "rbcavity" -o -name "rblist" | xargs -I{} cp {} /usr/local/bin/
chmod +x /usr/local/bin/rbdock /usr/local/bin/rbcavity 2>/dev/null || true
echo "rbdock: $(which rbdock)"
echo "rbcavity: $(which rbcavity)"
rbdock --version 2>&1 | head -3 || echo "rbdock installed (no --version flag)"
