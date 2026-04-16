#!/bin/sh
set -e
cd /tmp
tar xzf /tmp/rdock.tar.gz
# find and install the bins
find /tmp -maxdepth 2 -name "rbdock" -exec cp {} /usr/local/bin/ \;
find /tmp -maxdepth 2 -name "rbcavity" -exec cp {} /usr/local/bin/ \;
find /tmp -maxdepth 2 -name "rblist" -exec cp {} /usr/local/bin/ \;
chmod 755 /usr/local/bin/rbdock /usr/local/bin/rbcavity /usr/local/bin/rblist
echo "rbdock: $(which rbdock 2>/dev/null || echo NOT FOUND)"
echo "rbcavity: $(which rbcavity 2>/dev/null || echo NOT FOUND)"
# Test execution
/usr/local/bin/rbdock 2>&1 | head -3 || true
