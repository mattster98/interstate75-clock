#!/bin/bash
# Build Pimoroni Interstate 75 W (RP2350) MicroPython firmware with pico-sdk 2.1.1
# which contains the CYW43 DMA fix (pico-sdk PR #2209) that prevents HUB75 display
# from corrupting the WiFi driver on RP2350.
#
# Strategy: use pimoroni's micropython fork branch pico2_w_2025_09_19 (pico-sdk 2.1.1,
# fix included) combined with the i75w_rp2350 board definition from pimoroni/interstate75.
#
# Output: ~/i75-firmware/i75w_rp2350-custom.uf2

set -euo pipefail

BUILD_ROOT="$HOME/i75-firmware"
BOARD="i75w_rp2350"

# --- Version pins (match pimoroni-pico-rp2350 v1.26.1) ---
MP_REPO="https://github.com/pimoroni/micropython"
MP_BRANCH="pico2_w_2025_09_19"
PIMORONI_PICO_REPO="https://github.com/pimoroni/pimoroni-pico"
PIMORONI_PICO_COMMIT="431d8ad455371075ed247b10ded769d12136c7aa"
I75_REPO="https://github.com/pimoroni/interstate75"
TOOLCHAIN_VER="14.2.rel1"
TOOLCHAIN_TARBALL="arm-gnu-toolchain-${TOOLCHAIN_VER}-x86_64-arm-none-eabi.tar.xz"
TOOLCHAIN_URL="https://developer.arm.com/-/media/Files/downloads/gnu/${TOOLCHAIN_VER}/binrel/${TOOLCHAIN_TARBALL}"

TOOLCHAIN_DIR="$BUILD_ROOT/toolchain"
MICROPYTHON_DIR="$BUILD_ROOT/micropython"
PIMORONI_PICO_DIR="$BUILD_ROOT/pimoroni-pico"
I75_DIR="$BUILD_ROOT/interstate75"
TOOLS_DIR="$BUILD_ROOT/tools"
BUILD_DIR="$BUILD_ROOT/build-$BOARD"

echo "======================================================"
echo " Interstate 75 W (RP2350) firmware build"
echo " Build root: $BUILD_ROOT"
echo "======================================================"
mkdir -p "$BUILD_ROOT"

# ── 1. System packages ─────────────────────────────────────────────────
echo ""
echo "=== [1/8] Checking system packages ==="
for pkg in cmake ninja-build ccache libusb-1.0-0-dev; do
    dpkg -s "$pkg" 2>/dev/null | grep -q "Status: install ok" || \
        { echo "Missing package: $pkg — run: sudo apt-get install -y cmake ninja-build ccache libusb-1.0-0-dev build-essential python3-pip"; exit 1; }
done
echo "All required packages present."

# ── 2. ARM toolchain ───────────────────────────────────────────────────
echo ""
echo "=== [2/8] ARM GNU toolchain ${TOOLCHAIN_VER} ==="
if [ -f "$TOOLCHAIN_DIR/bin/arm-none-eabi-gcc" ]; then
    echo "Already present, skipping download."
else
    echo "Downloading (~170 MB)..."
    wget -q --show-progress -O "$BUILD_ROOT/$TOOLCHAIN_TARBALL" "$TOOLCHAIN_URL"
    echo "Extracting..."
    mkdir -p "$TOOLCHAIN_DIR"
    tar xf "$BUILD_ROOT/$TOOLCHAIN_TARBALL" -C "$TOOLCHAIN_DIR" --strip-components=1
    rm "$BUILD_ROOT/$TOOLCHAIN_TARBALL"
fi
export PATH="$TOOLCHAIN_DIR/bin:$PATH"
echo "Toolchain: $(arm-none-eabi-gcc --version | head -1)"

# ── 3. Python deps ─────────────────────────────────────────────────────
echo ""
echo "=== [3/8] Python packages ==="
pip3 install --quiet littlefs-python==0.12.0

# ── 4. Clone repos ─────────────────────────────────────────────────────
echo ""
echo "=== [4/8] Cloning repositories ==="

if [ ! -d "$MICROPYTHON_DIR" ]; then
    echo "Cloning pimoroni/micropython @ $MP_BRANCH ..."
    git clone --depth=1 --branch "$MP_BRANCH" "$MP_REPO" "$MICROPYTHON_DIR"
else
    echo "micropython: already cloned."
fi

echo "Updating MicroPython submodules (pico-sdk, lwip, etc.) ..."
cd "$MICROPYTHON_DIR"
git submodule update --init --depth=1 \
    lib/pico-sdk \
    lib/cyw43-driver \
    lib/lwip \
    lib/mbedtls \
    lib/micropython-lib \
    lib/tinyusb \
    lib/btstack

PICO_SDK_SHA=$(cd lib/pico-sdk && git rev-parse HEAD)
echo "pico-sdk SHA: $PICO_SDK_SHA"
# Should be 9a4113fb (2.1.1) which contains the CYW43 DMA fix
cd "$BUILD_ROOT"

if [ ! -d "$PIMORONI_PICO_DIR" ]; then
    echo "Cloning pimoroni/pimoroni-pico ..."
    git clone "$PIMORONI_PICO_REPO" "$PIMORONI_PICO_DIR"
fi
echo "Checking out pimoroni-pico @ $PIMORONI_PICO_COMMIT ..."
cd "$PIMORONI_PICO_DIR"
git checkout "$PIMORONI_PICO_COMMIT"
git submodule update --init --depth=1
cd "$BUILD_ROOT"

if [ ! -d "$I75_DIR" ]; then
    echo "Cloning pimoroni/interstate75 ..."
    git clone --depth=1 "$I75_REPO" "$I75_DIR"
else
    echo "interstate75: already cloned."
fi

# ── 5. Support tools ───────────────────────────────────────────────────
echo ""
echo "=== [5/8] Fetching support tools ==="
mkdir -p "$TOOLS_DIR"
if [ ! -d "$TOOLS_DIR/py_decl" ]; then
    git clone --depth=1 --branch v0.0.3 https://github.com/gadgetoid/py_decl "$TOOLS_DIR/py_decl"
fi
if [ ! -d "$TOOLS_DIR/dir2uf2" ]; then
    git clone --depth=1 --branch v0.0.9 https://github.com/gadgetoid/dir2uf2 "$TOOLS_DIR/dir2uf2"
fi

# ── 6. Build mpy-cross ────────────────────────────────────────────────
echo ""
echo "=== [6/8] Building mpy-cross ==="
make -C "$MICROPYTHON_DIR/mpy-cross" -j"$(nproc)"

# ── 7. CMake configure ────────────────────────────────────────────────
echo ""
echo "=== [7/8] CMake configure ==="
mkdir -p "$BUILD_DIR"
cmake -S "$MICROPYTHON_DIR/ports/rp2" -B "$BUILD_DIR" \
    -G Ninja \
    -DPICOTOOL_FORCE_FETCH_FROM_GIT=1 \
    -DPICO_BUILD_DOCS=0 \
    -DPICO_NO_COPRO_DIS=1 \
    -DPIMORONI_PICO_PATH="$PIMORONI_PICO_DIR" \
    -DPIMORONI_TOOLS_DIR="$TOOLS_DIR" \
    -DUSER_C_MODULES="$I75_DIR/boards/$BOARD/usermodules.cmake" \
    -DMICROPY_BOARD_DIR="$I75_DIR/boards/$BOARD" \
    -DMICROPY_BOARD="$BOARD" \
    -DCMAKE_C_COMPILER_LAUNCHER=ccache \
    -DCMAKE_CXX_COMPILER_LAUNCHER=ccache

# ── 8. Build ──────────────────────────────────────────────────────────
echo ""
echo "=== [8/8] Compiling (this takes 15-30 minutes on first run) ==="
cmake --build "$BUILD_DIR" -j"$(nproc)"

# ── Done ──────────────────────────────────────────────────────────────
UF2_SRC="$BUILD_DIR/firmware.uf2"
UF2_DEST="$BUILD_ROOT/i75w_rp2350-custom.uf2"

if [ -f "$UF2_SRC" ]; then
    cp "$UF2_SRC" "$UF2_DEST"
    echo ""
    echo "======================================================"
    echo " BUILD SUCCESSFUL"
    echo " Firmware: $UF2_DEST"
    echo " Size:     $(du -h "$UF2_DEST" | cut -f1)"
    echo "======================================================"
    echo ""
    echo "To flash: hold BOOTSEL on the board while powering up,"
    echo "then copy $UF2_DEST to the RPI-RP2 USB drive."
else
    echo ""
    echo "ERROR: firmware.uf2 not found. Check build output above."
    echo "UF2 files in build dir:"
    find "$BUILD_DIR" -name "*.uf2" 2>/dev/null || echo "(none found)"
    exit 1
fi
