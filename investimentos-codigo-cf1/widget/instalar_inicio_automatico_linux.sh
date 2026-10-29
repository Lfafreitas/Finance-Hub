#!/usr/bin/env sh
# Abre o widget junto com a sessão (padrão XDG: GNOME, KDE, XFCE...).
# Para desfazer: rm ~/.config/autostart/carteira-widget.desktop
AQUI="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/carteira-widget.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Carteira (widget)
Exec=sh "$AQUI/iniciar_widget.sh"
X-GNOME-Autostart-enabled=true
DESKTOP
echo "Pronto: o widget vai abrir junto com a sessão."
