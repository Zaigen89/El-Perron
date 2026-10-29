#!/bin/bash
# Instala el entorno en macOS. Uso: bash scripts/instalar_mac.sh [--diario HH:MM]
# --diario programa la revisión automática todos los días a esa hora (por defecto 08:40).
set -e
cd "$(dirname "$0")/.."
RAIZ="$(pwd)"

if ! command -v python3 >/dev/null; then
  echo "Falta Python 3. Instálalo desde https://www.python.org/downloads/ y vuelve a correr este script."
  exit 1
fi
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
[ -f .env ] || cp .env.example .env
echo "Entorno listo en $RAIZ/.venv"

if [ "$1" = "--diario" ]; then
  HORA="${2:-08:40}"
  H="${HORA%%:*}"; M="${HORA##*:}"
  PLIST="$HOME/Library/LaunchAgents/cl.100modos.licitaciones.plist"
  mkdir -p "$HOME/Library/LaunchAgents" "$RAIZ/salida"
  cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>cl.100modos.licitaciones</string>
  <key>WorkingDirectory</key><string>$RAIZ</string>
  <key>ProgramArguments</key>
  <array>
    <string>$RAIZ/.venv/bin/python</string><string>-m</string><string>licitaciones</string>
    <string>actualizar</string><string>--notificar</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>$((10#$H))</integer><key>Minute</key><integer>$((10#$M))</integer></dict>
  <key>StandardOutPath</key><string>$RAIZ/salida/diario.log</string>
  <key>StandardErrorPath</key><string>$RAIZ/salida/diario.log</string>
</dict>
</plist>
PL
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
  echo "Revisión diaria programada a las $HORA (si el Mac está dormido, corre al despertar)."
  echo "Para quitarla: launchctl unload $PLIST && rm $PLIST"
fi

grep -q "^MP_TICKET=.\+" .env || echo "Falta pegar el ticket de Mercado Público en el archivo .env (MP_TICKET=...)."
