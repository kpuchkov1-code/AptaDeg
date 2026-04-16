#!/bin/sh
set -e
cd /root/rdock_extracted

# Copy lib and binaries
cp lib/libRbt.so /usr/local/lib/
cp bin/rbdock bin/rbcavity bin/rblist bin/rbcalcgrid /usr/local/bin/
chmod 755 /usr/local/bin/rbdock /usr/local/bin/rbcavity /usr/local/bin/rblist
ldconfig

# Copy data to expected location (RBT_ROOT env var or /usr/local/lib)
mkdir -p /usr/local/lib/rDock
cp -r data /usr/local/lib/rDock/
export RBT_ROOT=/usr/local/lib/rDock

echo "rbdock: $(which rbdock)"
echo "rbcavity: $(which rbcavity)"
RBT_ROOT=/usr/local/lib/rDock rbdock --help 2>&1 | head -5 || true
RBT_ROOT=/usr/local/lib/rDock rbcavity --help 2>&1 | head -5 || true
