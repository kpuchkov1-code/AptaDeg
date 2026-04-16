#!/bin/sh
set -e
URL="https://github.com/CBDD/rDock/releases/download/v24.04.204-legacy/rdock-legacy-24.04.204_ubuntu-22.04_g%2B%2B_x86_64.tar.gz"
DEST="/root/rdock.tar.gz"
curl -L -o "$DEST" "$URL"
echo "size: $(ls -lh $DEST)"
tar tzf "$DEST" | head -5
mkdir -p /root/rdock_extracted
tar xzf "$DEST" -C /root/rdock_extracted
find /root/rdock_extracted -name "rbdock" -exec cp {} /usr/local/bin/ \;
find /root/rdock_extracted -name "rbcavity" -exec cp {} /usr/local/bin/ \;
find /root/rdock_extracted -name "rblist" -exec cp {} /usr/local/bin/ \;
chmod 755 /usr/local/bin/rbdock /usr/local/bin/rbcavity /usr/local/bin/rblist
echo "rbdock: $(which rbdock)"
echo "rbcavity: $(which rbcavity)"
/usr/local/bin/rbdock 2>&1 | head -2 || true
